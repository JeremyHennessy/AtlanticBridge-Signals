from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone

from .sources.cipo import (
    CIPOOwnerSearchResult,
    CIPOSession,
    CIPOTrademarkDetail,
    SOURCE_NAME,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cipo_owner_search_runs (
    search_run_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    owner_query TEXT NOT NULL,
    normalized_owner_query TEXT NOT NULL,
    request_payload_json TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    response_hash TEXT NOT NULL,
    num_found INTEGER NOT NULL,
    num_returned INTEGER NOT NULL,
    detail_requested INTEGER NOT NULL DEFAULT 0,
    detail_succeeded INTEGER NOT NULL DEFAULT 0,
    detail_failed INTEGER NOT NULL DEFAULT 0,
    detail_enrichment_complete INTEGER NOT NULL DEFAULT 0
        CHECK (detail_enrichment_complete IN (0, 1)),
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cipo_owner_query
ON cipo_owner_search_runs(normalized_owner_query);

CREATE TABLE IF NOT EXISTS cipo_search_records (
    record_id TEXT PRIMARY KEY,
    application_number TEXT NOT NULL,
    international_registration_numbers_json TEXT NOT NULL,
    mark_name TEXT NOT NULL,
    nice_codes_json TEXT NOT NULL,
    status_code TEXT NOT NULL,
    status_description TEXT NOT NULL,
    mark_type TEXT NOT NULL,
    st13_application_number TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cipo_app_no
ON cipo_search_records(application_number);

CREATE INDEX IF NOT EXISTS idx_cipo_mark_name
ON cipo_search_records(mark_name);

CREATE TABLE IF NOT EXISTS cipo_search_run_records (
    search_run_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_rank INTEGER NOT NULL,
    PRIMARY KEY (search_run_id, record_id),
    FOREIGN KEY (search_run_id)
        REFERENCES cipo_owner_search_runs(search_run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (record_id)
        REFERENCES cipo_search_records(record_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cipo_trademark_details (
    record_id TEXT PRIMARY KEY,
    application_number TEXT NOT NULL,
    registration_number TEXT NOT NULL,
    international_registration_number TEXT NOT NULL,
    mark_name TEXT NOT NULL,
    mark_type TEXT NOT NULL,
    category TEXT NOT NULL,
    cipo_status TEXT NOT NULL,
    filed_date TEXT NOT NULL,
    registered_date TEXT NOT NULL,
    international_registration_date TEXT NOT NULL,
    registration_expiry_date TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    owner_name TEXT NOT NULL,
    owner_lines_json TEXT NOT NULL,
    priority_claims_json TEXT NOT NULL,
    action_history_json TEXT NOT NULL,
    detail_url TEXT NOT NULL,
    detail_html_hash TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cipo_filed_date
ON cipo_trademark_details(filed_date);

CREATE INDEX IF NOT EXISTS idx_cipo_detail_owner
ON cipo_trademark_details(owner_name);

CREATE TABLE IF NOT EXISTS cipo_owner_detail_matches (
    search_run_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    owner_query TEXT NOT NULL,
    detail_owner_name TEXT NOT NULL,
    match_status TEXT NOT NULL CHECK (
        match_status IN (
            'EXACT_DETAIL_OWNER',
            'DETAIL_OWNER_MISMATCH',
            'DETAIL_OWNER_MISSING'
        )
    ),
    observed_at TEXT NOT NULL,
    PRIMARY KEY (search_run_id, record_id),
    FOREIGN KEY (search_run_id)
        REFERENCES cipo_owner_search_runs(search_run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (record_id)
        REFERENCES cipo_trademark_details(record_id)
        ON DELETE CASCADE
);
"""


def ensure_cipo_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _search_run_id(result: CIPOOwnerSearchResult) -> str:
    request_hash = hashlib.sha256(
        result.request_payload_json.encode("utf-8")
    ).hexdigest()
    material = "\x1f".join([request_hash, result.response_hash])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def persist_owner_search(
    conn: sqlite3.Connection,
    result: CIPOOwnerSearchResult,
    *,
    observed_at: str | None = None,
) -> str:
    ensure_cipo_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    search_run_id = _search_run_id(result)
    request_hash = hashlib.sha256(
        result.request_payload_json.encode("utf-8")
    ).hexdigest()

    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO cipo_owner_search_runs (
                search_run_id,
                source_name,
                owner_query,
                normalized_owner_query,
                request_payload_json,
                request_hash,
                response_hash,
                num_found,
                num_returned,
                first_observed_at,
                last_observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(search_run_id) DO UPDATE SET
                num_found = excluded.num_found,
                num_returned = excluded.num_returned,
                last_observed_at = excluded.last_observed_at
            """,
            (
                search_run_id,
                SOURCE_NAME,
                result.owner_query,
                result.normalized_owner_query,
                result.request_payload_json,
                request_hash,
                result.response_hash,
                result.num_found,
                result.num_returned,
                observed_at,
                observed_at,
            ),
        )

        conn.execute(
            "DELETE FROM cipo_search_run_records WHERE search_run_id = ?",
            (search_run_id,),
        )

        for rank, record in enumerate(result.records, start=1):
            conn.execute(
                """
                INSERT INTO cipo_search_records (
                    record_id,
                    application_number,
                    international_registration_numbers_json,
                    mark_name,
                    nice_codes_json,
                    status_code,
                    status_description,
                    mark_type,
                    st13_application_number,
                    raw_hash,
                    raw_json,
                    first_observed_at,
                    last_observed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(record_id) DO UPDATE SET
                    application_number = excluded.application_number,
                    international_registration_numbers_json =
                        excluded.international_registration_numbers_json,
                    mark_name = excluded.mark_name,
                    nice_codes_json = excluded.nice_codes_json,
                    status_code = excluded.status_code,
                    status_description = excluded.status_description,
                    mark_type = excluded.mark_type,
                    st13_application_number = excluded.st13_application_number,
                    raw_hash = excluded.raw_hash,
                    raw_json = excluded.raw_json,
                    last_observed_at = excluded.last_observed_at
                """,
                (
                    record.record_id,
                    record.application_number,
                    json.dumps(
                        list(record.international_registration_numbers),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    record.mark_name,
                    json.dumps(
                        list(record.nice_codes),
                        separators=(",", ":"),
                    ),
                    record.status_code,
                    record.status_description,
                    record.mark_type,
                    record.st13_application_number,
                    record.raw_hash,
                    record.raw_json,
                    observed_at,
                    observed_at,
                ),
            )
            conn.execute(
                """
                INSERT INTO cipo_search_run_records (
                    search_run_id,
                    record_id,
                    source_rank
                ) VALUES (?, ?, ?)
                """,
                (search_run_id, record.record_id, rank),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return search_run_id


def persist_detail(
    conn: sqlite3.Connection,
    *,
    search_run_id: str,
    owner_query: str,
    detail: CIPOTrademarkDetail,
    observed_at: str | None = None,
) -> str:
    ensure_cipo_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    match_status = detail.match_status(owner_query)

    conn.execute(
        """
        INSERT INTO cipo_trademark_details (
            record_id,
            application_number,
            registration_number,
            international_registration_number,
            mark_name,
            mark_type,
            category,
            cipo_status,
            filed_date,
            registered_date,
            international_registration_date,
            registration_expiry_date,
            owner_label,
            owner_name,
            owner_lines_json,
            priority_claims_json,
            action_history_json,
            detail_url,
            detail_html_hash,
            facts_json,
            first_observed_at,
            last_observed_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT(record_id) DO UPDATE SET
            application_number = excluded.application_number,
            registration_number = excluded.registration_number,
            international_registration_number =
                excluded.international_registration_number,
            mark_name = excluded.mark_name,
            mark_type = excluded.mark_type,
            category = excluded.category,
            cipo_status = excluded.cipo_status,
            filed_date = excluded.filed_date,
            registered_date = excluded.registered_date,
            international_registration_date =
                excluded.international_registration_date,
            registration_expiry_date = excluded.registration_expiry_date,
            owner_label = excluded.owner_label,
            owner_name = excluded.owner_name,
            owner_lines_json = excluded.owner_lines_json,
            priority_claims_json = excluded.priority_claims_json,
            action_history_json = excluded.action_history_json,
            detail_url = excluded.detail_url,
            detail_html_hash = excluded.detail_html_hash,
            facts_json = excluded.facts_json,
            last_observed_at = excluded.last_observed_at
        """,
        (
            detail.record_id,
            detail.application_number,
            detail.registration_number,
            detail.international_registration_number,
            detail.mark_name,
            detail.mark_type,
            detail.category,
            detail.cipo_status,
            detail.filed_date,
            detail.registered_date,
            detail.international_registration_date,
            detail.registration_expiry_date,
            detail.owner_label,
            detail.owner_name,
            json.dumps(
                list(detail.owner_lines),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            json.dumps(
                list(detail.priority_claims),
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            json.dumps(
                list(detail.action_history),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            detail.detail_url,
            detail.detail_html_hash,
            detail.facts_json,
            observed_at,
            observed_at,
        ),
    )
    conn.execute(
        """
        INSERT INTO cipo_owner_detail_matches (
            search_run_id,
            record_id,
            owner_query,
            detail_owner_name,
            match_status,
            observed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(search_run_id, record_id) DO UPDATE SET
            owner_query = excluded.owner_query,
            detail_owner_name = excluded.detail_owner_name,
            match_status = excluded.match_status,
            observed_at = excluded.observed_at
        """,
        (
            search_run_id,
            detail.record_id,
            owner_query,
            detail.owner_name,
            match_status,
            observed_at,
        ),
    )
    conn.commit()
    return match_status


def run_owner_search(
    conn: sqlite3.Connection,
    *,
    owner_name: str,
    detail_limit: int = 10,
    detail_offset: int = 0,
    detail_delay_seconds: float = 0.2,
) -> dict[str, object]:
    if detail_limit < 0:
        raise ValueError("detail_limit must be non-negative")
    if detail_offset < 0:
        raise ValueError("detail_offset must be non-negative")
    if detail_delay_seconds < 0:
        raise ValueError("detail_delay_seconds must be non-negative")

    ensure_cipo_schema(conn)
    session = CIPOSession()
    search = session.search_owner(owner_name)
    search_run_id = persist_owner_search(conn, search)

    selected = search.records[
        detail_offset : detail_offset + detail_limit
    ] if detail_limit else ()

    succeeded = 0
    failed = 0
    match_counts: dict[str, int] = {}
    failures: list[dict[str, str]] = []

    for index, record in enumerate(selected):
        try:
            detail = session.fetch_detail(record.record_id)
            status = persist_detail(
                conn,
                search_run_id=search_run_id,
                owner_query=search.owner_query,
                detail=detail,
            )
            succeeded += 1
            match_counts[status] = match_counts.get(status, 0) + 1
        except Exception as exc:
            failed += 1
            failures.append(
                {
                    "record_id": record.record_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
        if (
            detail_delay_seconds > 0
            and index < len(selected) - 1
        ):
            time.sleep(detail_delay_seconds)

    enriched_ids = conn.execute(
        """
        SELECT COUNT(DISTINCT record_id)
        FROM cipo_owner_detail_matches
        WHERE search_run_id = ?
        """,
        (search_run_id,),
    ).fetchone()[0]
    detail_complete = (
        search.num_found == 0
        or enriched_ids >= search.num_found
    )

    conn.execute(
        """
        UPDATE cipo_owner_search_runs
        SET detail_requested = ?,
            detail_succeeded = ?,
            detail_failed = ?,
            detail_enrichment_complete = ?,
            last_observed_at = ?
        WHERE search_run_id = ?
        """,
        (
            len(selected),
            succeeded,
            failed,
            int(detail_complete),
            datetime.now(timezone.utc).isoformat(),
            search_run_id,
        ),
    )
    conn.commit()

    return {
        "search_run_id": search_run_id,
        "owner_query": search.owner_query,
        "num_found": search.num_found,
        "num_returned": search.num_returned,
        "detail_offset": detail_offset,
        "detail_requested": len(selected),
        "detail_succeeded": succeeded,
        "detail_failed": failed,
        "total_detail_enriched": enriched_ids,
        "detail_enrichment_complete": detail_complete,
        "match_counts": dict(sorted(match_counts.items())),
        "failures": failures,
        "response_hash": search.response_hash,
    }


def cipo_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_cipo_schema(conn)
    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM cipo_owner_search_runs) AS search_runs,
            (SELECT COUNT(*) FROM cipo_search_records) AS search_records,
            (SELECT COUNT(*) FROM cipo_trademark_details) AS details,
            (SELECT COUNT(*) FROM cipo_owner_detail_matches) AS detail_matches,
            (
                SELECT COUNT(*)
                FROM cipo_owner_detail_matches
                WHERE match_status = 'EXACT_DETAIL_OWNER'
            ) AS exact_detail_owner_matches,
            (
                SELECT COUNT(*)
                FROM cipo_owner_search_runs
                WHERE detail_enrichment_complete = 1
            ) AS fully_enriched_search_runs
        """
    ).fetchone()

    states = [
        dict(row)
        for row in conn.execute(
            """
            SELECT match_status, COUNT(*) AS records
            FROM cipo_owner_detail_matches
            GROUP BY match_status
            ORDER BY match_status
            """
        )
    ]

    searches = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                owner_query,
                num_found,
                num_returned,
                detail_requested,
                detail_succeeded,
                detail_failed,
                detail_enrichment_complete,
                first_observed_at,
                last_observed_at
            FROM cipo_owner_search_runs
            ORDER BY last_observed_at DESC, owner_query ASC
            LIMIT 50
            """
        )
    ]

    return {
        "search_runs": totals["search_runs"] or 0,
        "search_records": totals["search_records"] or 0,
        "details": totals["details"] or 0,
        "detail_matches": totals["detail_matches"] or 0,
        "exact_detail_owner_matches": totals["exact_detail_owner_matches"] or 0,
        "fully_enriched_search_runs": totals["fully_enriched_search_runs"] or 0,
        "match_status_counts": states,
        "recent_searches": searches,
    }
