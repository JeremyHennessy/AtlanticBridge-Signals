from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from .sources.cordis import EU27_ISO2
from .sources.gleif import GLEIFSearchResult, search_legal_name

SCHEMA = """
CREATE TABLE IF NOT EXISTS gleif_resolution_queries (
    query_id TEXT PRIMARY KEY,
    source_system TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_country TEXT NOT NULL,
    source_vat_number TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    golden_copy_publish_date TEXT NOT NULL,
    query_url TEXT NOT NULL,
    total_results INTEGER NOT NULL,
    returned_candidate_count INTEGER NOT NULL,
    returned_leis_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_gleif_query_source
ON gleif_resolution_queries(source_system, source_entity_id);

CREATE TABLE IF NOT EXISTS gleif_candidates (
    source_system TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_country TEXT NOT NULL,
    source_vat_number TEXT NOT NULL,
    lei TEXT NOT NULL,
    legal_name TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    entity_status TEXT NOT NULL,
    entity_category TEXT NOT NULL,
    registered_as TEXT NOT NULL,
    registration_authority_id TEXT NOT NULL,
    legal_address_city TEXT NOT NULL,
    legal_address_country TEXT NOT NULL,
    headquarters_city TEXT NOT NULL,
    headquarters_country TEXT NOT NULL,
    api_rank INTEGER NOT NULL,
    name_similarity REAL NOT NULL,
    exact_normalized_name INTEGER NOT NULL CHECK (exact_normalized_name IN (0, 1)),
    jurisdiction_match INTEGER NOT NULL CHECK (jurisdiction_match IN (0, 1)),
    match_class TEXT NOT NULL,
    golden_copy_publish_date TEXT NOT NULL,
    query_url TEXT NOT NULL,
    relationship_links_json TEXT NOT NULL,
    record_json TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    PRIMARY KEY (source_system, source_entity_id, source_country, lei)
);

CREATE INDEX IF NOT EXISTS idx_gleif_candidates_lei
ON gleif_candidates(lei);

CREATE INDEX IF NOT EXISTS idx_gleif_candidates_match
ON gleif_candidates(match_class);

CREATE TABLE IF NOT EXISTS gleif_resolution_status (
    source_system TEXT NOT NULL,
    source_entity_id TEXT NOT NULL,
    source_country TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN (
            'UNRESOLVED',
            'NO_RESULTS',
            'REVIEW_READY',
            'AMBIGUOUS',
            'CONFIRMED',
            'REJECTED'
        )
    ),
    confirmed_lei TEXT NOT NULL DEFAULT '',
    decision_basis TEXT NOT NULL DEFAULT '',
    decided_at TEXT NOT NULL DEFAULT '',
    last_queried_at TEXT NOT NULL,
    PRIMARY KEY (source_system, source_entity_id, source_country)
);
"""


@dataclass(frozen=True, slots=True)
class ResolutionTarget:
    source_system: str
    source_entity_id: str
    source_name: str
    source_country: str
    source_vat_number: str


def ensure_gleif_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def cordis_resolution_targets(
    conn: sqlite3.Connection,
    *,
    limit: int,
    offset: int = 0,
) -> list[ResolutionTarget]:
    if limit < 1:
        raise ValueError("limit must be at least 1")
    if offset < 0:
        raise ValueError("offset must be non-negative")

    placeholders = ",".join("?" for _ in EU27_ISO2)
    params = [*sorted(EU27_ISO2), limit, offset]

    rows = conn.execute(
        f"""
        WITH canada_projects AS (
            SELECT DISTINCT project_id
            FROM cordis_participations
            WHERE country = 'CA'
        ),
        eu_rows AS (
            SELECT p.*
            FROM cordis_participations p
            JOIN canada_projects c ON c.project_id = p.project_id
            WHERE p.country IN ({placeholders})
              AND p.organisation_id <> ''
              AND p.name <> ''
        ),
        name_counts AS (
            SELECT
                organisation_id,
                country,
                name,
                COUNT(*) AS name_count,
                ROW_NUMBER() OVER (
                    PARTITION BY organisation_id, country
                    ORDER BY COUNT(*) DESC, name ASC
                ) AS rn
            FROM eu_rows
            GROUP BY organisation_id, country, name
        ),
        vats AS (
            SELECT
                organisation_id,
                country,
                MAX(NULLIF(vat_number, '')) AS vat_number
            FROM eu_rows
            GROUP BY organisation_id, country
        )
        SELECT
            n.organisation_id,
            n.name,
            n.country,
            COALESCE(v.vat_number, '') AS vat_number
        FROM name_counts n
        LEFT JOIN vats v
          ON v.organisation_id = n.organisation_id
         AND v.country = n.country
        WHERE n.rn = 1
        ORDER BY n.country, n.name, n.organisation_id
        LIMIT ? OFFSET ?
        """,
        params,
    ).fetchall()

    return [
        ResolutionTarget(
            source_system="CORDIS",
            source_entity_id=row["organisation_id"],
            source_name=row["name"],
            source_country=row["country"],
            source_vat_number=row["vat_number"],
        )
        for row in rows
    ]


def _query_id(target: ResolutionTarget, result: GLEIFSearchResult, observed_at: str) -> str:
    material = "\x1f".join(
        [
            target.source_system,
            target.source_entity_id,
            target.source_country,
            result.query_url,
            result.golden_copy_publish_date,
            observed_at,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def persist_search_result(
    conn: sqlite3.Connection,
    target: ResolutionTarget,
    result: GLEIFSearchResult,
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_gleif_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    candidate_leis = [candidate.lei for candidate in result.candidates if candidate.lei]

    conn.execute(
        """
        INSERT OR IGNORE INTO gleif_resolution_queries (
            query_id,
            source_system,
            source_entity_id,
            source_name,
            source_country,
            source_vat_number,
            observed_at,
            golden_copy_publish_date,
            query_url,
            total_results,
            returned_candidate_count,
            returned_leis_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _query_id(target, result, observed_at),
            target.source_system,
            target.source_entity_id,
            target.source_name,
            target.source_country,
            target.source_vat_number,
            observed_at,
            result.golden_copy_publish_date,
            result.query_url,
            result.total_results,
            len(result.candidates),
            json.dumps(candidate_leis, separators=(",", ":")),
        ),
    )

    for candidate in result.candidates:
        if not candidate.lei:
            continue
        conn.execute(
            """
            INSERT INTO gleif_candidates (
                source_system,
                source_entity_id,
                source_name,
                source_country,
                source_vat_number,
                lei,
                legal_name,
                jurisdiction,
                entity_status,
                entity_category,
                registered_as,
                registration_authority_id,
                legal_address_city,
                legal_address_country,
                headquarters_city,
                headquarters_country,
                api_rank,
                name_similarity,
                exact_normalized_name,
                jurisdiction_match,
                match_class,
                golden_copy_publish_date,
                query_url,
                relationship_links_json,
                record_json,
                first_observed_at,
                last_observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_system, source_entity_id, source_country, lei) DO UPDATE SET
                source_name = excluded.source_name,
                source_vat_number = excluded.source_vat_number,
                legal_name = excluded.legal_name,
                jurisdiction = excluded.jurisdiction,
                entity_status = excluded.entity_status,
                entity_category = excluded.entity_category,
                registered_as = excluded.registered_as,
                registration_authority_id = excluded.registration_authority_id,
                legal_address_city = excluded.legal_address_city,
                legal_address_country = excluded.legal_address_country,
                headquarters_city = excluded.headquarters_city,
                headquarters_country = excluded.headquarters_country,
                api_rank = excluded.api_rank,
                name_similarity = excluded.name_similarity,
                exact_normalized_name = excluded.exact_normalized_name,
                jurisdiction_match = excluded.jurisdiction_match,
                match_class = excluded.match_class,
                golden_copy_publish_date = excluded.golden_copy_publish_date,
                query_url = excluded.query_url,
                relationship_links_json = excluded.relationship_links_json,
                record_json = excluded.record_json,
                last_observed_at = excluded.last_observed_at
            """,
            (
                target.source_system,
                target.source_entity_id,
                target.source_name,
                target.source_country,
                target.source_vat_number,
                candidate.lei,
                candidate.legal_name,
                candidate.jurisdiction,
                candidate.entity_status,
                candidate.entity_category,
                candidate.registered_as,
                candidate.registration_authority_id,
                candidate.legal_address_city,
                candidate.legal_address_country,
                candidate.headquarters_city,
                candidate.headquarters_country,
                candidate.rank,
                candidate.name_similarity,
                int(candidate.exact_normalized_name),
                int(candidate.jurisdiction_match),
                candidate.match_class,
                result.golden_copy_publish_date,
                result.query_url,
                candidate.relationship_links_json,
                candidate.record_json,
                observed_at,
                observed_at,
            ),
        )

    exact_country = [
        candidate
        for candidate in result.candidates
        if candidate.match_class == "EXACT_NAME_COUNTRY"
    ]
    if not result.candidates:
        status = "NO_RESULTS"
    elif len(exact_country) == 1:
        status = "REVIEW_READY"
    elif len(exact_country) > 1:
        status = "AMBIGUOUS"
    else:
        status = "UNRESOLVED"

    existing = conn.execute(
        """
        SELECT status
        FROM gleif_resolution_status
        WHERE source_system = ?
          AND source_entity_id = ?
          AND source_country = ?
        """,
        (target.source_system, target.source_entity_id, target.source_country),
    ).fetchone()

    # A human-confirmed/rejected decision is immutable under refresh unless
    # explicitly changed by a separate decision workflow.
    if existing is None or existing["status"] not in {"CONFIRMED", "REJECTED"}:
        conn.execute(
            """
            INSERT INTO gleif_resolution_status (
                source_system,
                source_entity_id,
                source_country,
                status,
                last_queried_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_system, source_entity_id, source_country) DO UPDATE SET
                status = excluded.status,
                last_queried_at = excluded.last_queried_at
            """,
            (
                target.source_system,
                target.source_entity_id,
                target.source_country,
                status,
                observed_at,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE gleif_resolution_status
            SET last_queried_at = ?
            WHERE source_system = ?
              AND source_entity_id = ?
              AND source_country = ?
            """,
            (
                observed_at,
                target.source_system,
                target.source_entity_id,
                target.source_country,
            ),
        )
        status = existing["status"]

    conn.commit()
    return {
        "status": status,
        "candidate_count": len(result.candidates),
        "exact_name_country_candidates": len(exact_country),
    }


def resolve_cordis_targets(
    conn: sqlite3.Connection,
    *,
    limit: int,
    offset: int = 0,
    page_size: int = 5,
    delay_seconds: float = 0.1,
) -> dict[str, object]:
    ensure_gleif_schema(conn)
    targets = cordis_resolution_targets(conn, limit=limit, offset=offset)
    status_counts: dict[str, int] = {}
    total_candidates = 0
    golden_copy_publish_dates: set[str] = set()

    for index, target in enumerate(targets):
        result = search_legal_name(
            target.source_name,
            source_country=target.source_country,
            page_size=page_size,
        )
        persisted = persist_search_result(conn, target, result)
        total_candidates += int(persisted["candidate_count"])
        status = str(persisted["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        if result.golden_copy_publish_date:
            golden_copy_publish_dates.add(result.golden_copy_publish_date)

        if delay_seconds > 0 and index < len(targets) - 1:
            time.sleep(delay_seconds)

    return {
        "targets_queried": len(targets),
        "candidate_rows_returned": total_candidates,
        "status_counts": dict(sorted(status_counts.items())),
        "golden_copy_publish_dates": sorted(golden_copy_publish_dates),
        "limit": limit,
        "offset": offset,
        "page_size": page_size,
    }


def gleif_resolution_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_gleif_schema(conn)

    status_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT status, COUNT(*) AS entities
            FROM gleif_resolution_status
            GROUP BY status
            ORDER BY status
            """
        )
    ]
    match_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT match_class, COUNT(*) AS candidates
            FROM gleif_candidates
            GROUP BY match_class
            ORDER BY match_class
            """
        )
    ]
    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM gleif_resolution_queries) AS queries,
            (SELECT COUNT(*) FROM gleif_candidates) AS candidates,
            (SELECT COUNT(DISTINCT lei) FROM gleif_candidates) AS unique_leis,
            (SELECT COUNT(*) FROM gleif_resolution_status) AS source_entities
        """
    ).fetchone()

    return {
        "queries": totals["queries"] or 0,
        "candidate_rows": totals["candidates"] or 0,
        "unique_leis": totals["unique_leis"] or 0,
        "source_entities": totals["source_entities"] or 0,
        "status_counts": status_counts,
        "match_class_counts": match_counts,
    }
