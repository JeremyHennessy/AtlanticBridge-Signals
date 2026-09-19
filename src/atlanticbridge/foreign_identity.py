from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone

from .sources.gleif import (
    GLEIFCandidate,
    fetch_api_resource,
    fetch_lei_record,
    normalize_entity_name,
    search_legal_name,
)

EU_COUNTRY_TO_ISO2 = {
    "Austria": "AT",
    "Belgium": "BE",
    "Bulgaria": "BG",
    "Croatia": "HR",
    "Cyprus": "CY",
    "Czechia": "CZ",
    "Denmark": "DK",
    "Estonia": "EE",
    "Finland": "FI",
    "France": "FR",
    "Germany": "DE",
    "Greece": "GR",
    "Hungary": "HU",
    "Ireland": "IE",
    "Italy": "IT",
    "Latvia": "LV",
    "Lithuania": "LT",
    "Luxembourg": "LU",
    "Malta": "MT",
    "Netherlands": "NL",
    "Poland": "PL",
    "Portugal": "PT",
    "Romania": "RO",
    "Slovakia": "SK",
    "Slovenia": "SI",
    "Spain": "ES",
    "Sweden": "SE",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS foreign_identity_runs (
    run_id TEXT PRIMARY KEY,
    entry_identity_run_id TEXT NOT NULL,
    target_records INTEGER NOT NULL,
    queried_investors INTEGER NOT NULL,
    page_size INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS foreign_identity_resolutions (
    run_id TEXT NOT NULL,
    outcome_record_id TEXT NOT NULL,
    certification_month TEXT NOT NULL,
    ultimate_control_country TEXT NOT NULL,
    ultimate_control_country_iso2 TEXT NOT NULL,
    investor_name TEXT NOT NULL,
    investor_locality TEXT NOT NULL,
    investor_role_status TEXT NOT NULL,
    canadian_entry_corporation_number TEXT NOT NULL,
    resolution_status TEXT NOT NULL CHECK (
        resolution_status IN (
            'CANADIAN_VEHICLE_PARENT_UNRESOLVED',
            'CONFIRMED_FOREIGN_NAMED_ENTITY',
            'CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED',
            'REVIEW_READY_EXACT_NAME',
            'AMBIGUOUS_EXACT',
            'UNRESOLVED',
            'NO_RESULTS',
            'QUERY_ERROR'
        )
    ),
    query_url TEXT NOT NULL,
    golden_copy_publish_date TEXT NOT NULL,
    total_gleif_results INTEGER NOT NULL,
    returned_candidate_count INTEGER NOT NULL,
    exact_name_candidate_count INTEGER NOT NULL,
    locality_match_candidate_count INTEGER NOT NULL,
    confirmed_lei TEXT NOT NULL,
    confirmed_legal_name TEXT NOT NULL,
    confirmed_jurisdiction TEXT NOT NULL,
    confirmed_registered_as TEXT NOT NULL,
    confirmed_registration_authority_id TEXT NOT NULL,
    confirmed_legal_city TEXT NOT NULL,
    confirmed_headquarters_city TEXT NOT NULL,
    control_country_matches_jurisdiction INTEGER NOT NULL CHECK (
        control_country_matches_jurisdiction IN (0, 1)
    ),
    candidate_snapshot_json TEXT NOT NULL,
    direct_parent_status TEXT NOT NULL,
    direct_parent_lei TEXT NOT NULL,
    direct_parent_legal_name TEXT NOT NULL,
    direct_parent_relationship_type TEXT NOT NULL,
    direct_parent_exception_reason TEXT NOT NULL,
    direct_parent_evidence_url TEXT NOT NULL,
    direct_parent_raw_json TEXT NOT NULL,
    ultimate_parent_status TEXT NOT NULL,
    ultimate_parent_lei TEXT NOT NULL,
    ultimate_parent_legal_name TEXT NOT NULL,
    ultimate_parent_relationship_type TEXT NOT NULL,
    ultimate_parent_exception_reason TEXT NOT NULL,
    ultimate_parent_evidence_url TEXT NOT NULL,
    ultimate_parent_raw_json TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, outcome_record_id),
    FOREIGN KEY (run_id) REFERENCES foreign_identity_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_foreign_identity_status
ON foreign_identity_resolutions(run_id, resolution_status);

CREATE INDEX IF NOT EXISTS idx_foreign_identity_lei
ON foreign_identity_resolutions(confirmed_lei);

CREATE INDEX IF NOT EXISTS idx_foreign_identity_parent
ON foreign_identity_resolutions(ultimate_parent_lei);
"""


def ensure_foreign_identity_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _location_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(
        char for char in normalized.casefold()
        if char.isalnum()
    )


def _locality_matches(candidate: GLEIFCandidate, investor_locality: str) -> bool:
    source = _location_key(investor_locality)
    if not source:
        return False
    return source in {
        _location_key(candidate.legal_address_city),
        _location_key(candidate.headquarters_city),
    }


def classify_candidates(
    candidates: tuple[GLEIFCandidate, ...],
    investor_locality: str,
) -> tuple[str, GLEIFCandidate | None, int, int]:
    exact = [
        candidate
        for candidate in candidates
        if candidate.exact_normalized_name
    ]
    locality = [
        candidate
        for candidate in exact
        if _locality_matches(candidate, investor_locality)
    ]

    if len(locality) == 1:
        return "CONFIRMED_NAMED_ENTITY", locality[0], len(exact), 1
    if len(locality) > 1:
        return "AMBIGUOUS_EXACT", None, len(exact), len(locality)
    if len(exact) == 1:
        return "REVIEW_READY_EXACT_NAME", exact[0], 1, 0
    if len(exact) > 1:
        return "AMBIGUOUS_EXACT", None, len(exact), 0
    if not candidates:
        return "NO_RESULTS", None, 0, 0
    return "UNRESOLVED", None, 0, 0


def _resolved_named_status(
    status: str,
    selected: GLEIFCandidate | None,
) -> str:
    if status != "CONFIRMED_NAMED_ENTITY" or selected is None:
        return status

    jurisdiction = selected.jurisdiction.upper()
    legal_country = selected.legal_address_country.upper()
    headquarters_country = selected.headquarters_country.upper()
    if (
        jurisdiction == "CA"
        or jurisdiction.startswith("CA-")
        or legal_country == "CA"
        or headquarters_country == "CA"
    ):
        return "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED"
    return "CONFIRMED_FOREIGN_NAMED_ENTITY"


def _candidate_snapshot(candidates: tuple[GLEIFCandidate, ...]) -> str:
    rows = [
        {
            "rank": candidate.rank,
            "lei": candidate.lei,
            "legal_name": candidate.legal_name,
            "jurisdiction": candidate.jurisdiction,
            "entity_status": candidate.entity_status,
            "registered_as": candidate.registered_as,
            "registration_authority_id": candidate.registration_authority_id,
            "legal_address_city": candidate.legal_address_city,
            "legal_address_country": candidate.legal_address_country,
            "headquarters_city": candidate.headquarters_city,
            "headquarters_country": candidate.headquarters_country,
            "name_similarity": candidate.name_similarity,
            "exact_normalized_name": candidate.exact_normalized_name,
            "match_class": candidate.match_class,
        }
        for candidate in candidates
    ]
    return json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _payload_data(payload: dict):
    data = payload.get("data")
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _legal_name_from_lei_payload(payload: dict) -> str:
    data = _payload_data(payload)
    attributes = data.get("attributes") or {}
    entity = attributes.get("entity") or {}
    legal_name = entity.get("legalName") or {}
    return _clean(legal_name.get("name"))


def _relationship_object(payload: dict) -> dict:
    data = _payload_data(payload)
    attributes = data.get("attributes") or {}
    relationship = attributes.get("relationship") or {}
    return relationship if isinstance(relationship, dict) else {}


def _parent_evidence(candidate: GLEIFCandidate, kind: str) -> dict[str, str]:
    if kind not in {"direct-parent", "ultimate-parent"}:
        raise ValueError(f"Unsupported GLEIF parent kind: {kind}")

    try:
        relationships = json.loads(candidate.relationship_links_json)
    except json.JSONDecodeError:
        relationships = {}

    relation = relationships.get(kind) or {}
    links = relation.get("links") or {}

    related_url = _clean(links.get("related"))
    exception_url = _clean(links.get("reporting-exception"))

    if related_url:
        payload = fetch_api_resource(related_url)
        relationship = _relationship_object(payload)
        end_node = relationship.get("endNode") or {}
        parent_lei = _clean(end_node.get("id"))
        relationship_type = _clean(relationship.get("type"))
        parent_name = ""
        parent_record_json = "{}"
        if parent_lei:
            parent_payload = fetch_lei_record(parent_lei)
            parent_name = _legal_name_from_lei_payload(parent_payload)
            parent_record_json = json.dumps(
                parent_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        raw = json.dumps(
            {
                "relationship": payload,
                "parent_record": json.loads(parent_record_json),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "status": "PARENT_LEI" if parent_lei else "RELATED_WITHOUT_PARENT_LEI",
            "lei": parent_lei,
            "legal_name": parent_name,
            "relationship_type": relationship_type,
            "exception_reason": "",
            "evidence_url": related_url,
            "raw_json": raw,
        }

    if exception_url:
        payload = fetch_api_resource(exception_url)
        data = _payload_data(payload)
        attributes = data.get("attributes") or {}
        return {
            "status": "REPORTING_EXCEPTION",
            "lei": "",
            "legal_name": "",
            "relationship_type": _clean(attributes.get("category")),
            "exception_reason": _clean(attributes.get("reason")),
            "evidence_url": exception_url,
            "raw_json": json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        }

    return {
        "status": "NO_RELATIONSHIP_LINK",
        "lei": "",
        "legal_name": "",
        "relationship_type": "",
        "exception_reason": "",
        "evidence_url": "",
        "raw_json": "{}",
    }


def _latest_entry_identity_run(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT run_id
        FROM entry_identity_runs
        ORDER BY observed_at DESC
        LIMIT 1
        """
    ).fetchone()


def _entry_targets(conn: sqlite3.Connection, entry_run_id: str):
    return conn.execute(
        """
        SELECT
            outcome_record_id,
            certification_month,
            ultimate_control_country,
            investor_name,
            investor_locality,
            investor_role_status,
            selected_corporation_number
        FROM entry_identity_matches
        WHERE run_id = ?
          AND detail_status = 'FEDERAL_ENTITY_CONFIRMED'
          AND gold_selected = 1
        ORDER BY gold_rank, outcome_record_id
        """,
        (entry_run_id,),
    ).fetchall()


def _run_id(entry_run_id: str, observed_at: str) -> str:
    return hashlib.sha256(
        f"{entry_run_id}\x1f{observed_at}".encode("utf-8")
    ).hexdigest()


def resolve_foreign_identities(
    conn: sqlite3.Connection,
    *,
    page_size: int = 20,
    delay_seconds: float = 0.1,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_foreign_identity_schema(conn)
    entry_run = _latest_entry_identity_run(conn)
    if entry_run is None:
        raise ValueError(
            "Foreign identity resolution requires a completed entry-identity run"
        )
    entry_run_id = entry_run["run_id"]
    targets = _entry_targets(conn, entry_run_id)
    if not targets:
        raise ValueError("Entry-identity run has no detail-confirmed gold records")

    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    run_id = _run_id(entry_run_id, observed_at)
    queried = 0
    rows: list[dict[str, object]] = []

    for index, target in enumerate(targets):
        role = target["investor_role_status"]
        country = target["ultimate_control_country"]
        country_iso2 = EU_COUNTRY_TO_ISO2.get(country, "")

        base = {
            "outcome_record_id": target["outcome_record_id"],
            "certification_month": target["certification_month"],
            "ultimate_control_country": country,
            "ultimate_control_country_iso2": country_iso2,
            "investor_name": target["investor_name"],
            "investor_locality": target["investor_locality"],
            "investor_role_status": role,
            "canadian_entry_corporation_number":
                target["selected_corporation_number"],
            "resolution_status": "CANADIAN_VEHICLE_PARENT_UNRESOLVED",
            "query_url": "",
            "golden_copy_publish_date": "",
            "total_gleif_results": 0,
            "returned_candidate_count": 0,
            "exact_name_candidate_count": 0,
            "locality_match_candidate_count": 0,
            "confirmed_lei": "",
            "confirmed_legal_name": "",
            "confirmed_jurisdiction": "",
            "confirmed_registered_as": "",
            "confirmed_registration_authority_id": "",
            "confirmed_legal_city": "",
            "confirmed_headquarters_city": "",
            "control_country_matches_jurisdiction": False,
            "candidate_snapshot_json": "[]",
            "direct_parent": {
                "status": "NOT_QUERIED",
                "lei": "",
                "legal_name": "",
                "relationship_type": "",
                "exception_reason": "",
                "evidence_url": "",
                "raw_json": "{}",
            },
            "ultimate_parent": {
                "status": "NOT_QUERIED",
                "lei": "",
                "legal_name": "",
                "relationship_type": "",
                "exception_reason": "",
                "evidence_url": "",
                "raw_json": "{}",
            },
        }

        if role == "DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION":
            queried += 1
            try:
                result = search_legal_name(
                    target["investor_name"],
                    source_country="",
                    page_size=page_size,
                )
                status, selected, exact_count, locality_count = classify_candidates(
                    result.candidates,
                    target["investor_locality"],
                )
                status = _resolved_named_status(status, selected)
                confirmed_statuses = {
                    "CONFIRMED_FOREIGN_NAMED_ENTITY",
                    "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED",
                }
                base.update(
                    {
                        "resolution_status": status,
                        "query_url": result.query_url,
                        "golden_copy_publish_date":
                            result.golden_copy_publish_date,
                        "total_gleif_results": result.total_results,
                        "returned_candidate_count": len(result.candidates),
                        "exact_name_candidate_count": exact_count,
                        "locality_match_candidate_count": locality_count,
                        "candidate_snapshot_json":
                            _candidate_snapshot(result.candidates),
                    }
                )

                if selected is not None:
                    base.update(
                        {
                            "confirmed_lei": (
                                selected.lei
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_legal_name": (
                                selected.legal_name
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_jurisdiction": (
                                selected.jurisdiction
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_registered_as": (
                                selected.registered_as
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_registration_authority_id": (
                                selected.registration_authority_id
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_legal_city": (
                                selected.legal_address_city
                                if status in confirmed_statuses
                                else ""
                            ),
                            "confirmed_headquarters_city": (
                                selected.headquarters_city
                                if status in confirmed_statuses
                                else ""
                            ),
                            "control_country_matches_jurisdiction": (
                                status in confirmed_statuses
                                and bool(country_iso2)
                                and selected.jurisdiction.upper() == country_iso2
                            ),
                        }
                    )
                    if status in confirmed_statuses:
                        base["direct_parent"] = _parent_evidence(
                            selected,
                            "direct-parent",
                        )
                        base["ultimate_parent"] = _parent_evidence(
                            selected,
                            "ultimate-parent",
                        )
            except Exception:
                base["resolution_status"] = "QUERY_ERROR"

            if delay_seconds > 0 and index < len(targets) - 1:
                time.sleep(delay_seconds)

        rows.append(base)

    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO foreign_identity_runs (
                run_id,
                entry_identity_run_id,
                target_records,
                queried_investors,
                page_size,
                observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                entry_run_id,
                len(targets),
                queried,
                page_size,
                observed_at,
            ),
        )

        for row in rows:
            direct = row["direct_parent"]
            ultimate = row["ultimate_parent"]
            conn.execute(
                """
                INSERT INTO foreign_identity_resolutions (
                    run_id, outcome_record_id, certification_month,
                    ultimate_control_country, ultimate_control_country_iso2,
                    investor_name, investor_locality, investor_role_status,
                    canadian_entry_corporation_number, resolution_status,
                    query_url, golden_copy_publish_date, total_gleif_results,
                    returned_candidate_count, exact_name_candidate_count,
                    locality_match_candidate_count, confirmed_lei,
                    confirmed_legal_name, confirmed_jurisdiction,
                    confirmed_registered_as,
                    confirmed_registration_authority_id,
                    confirmed_legal_city, confirmed_headquarters_city,
                    control_country_matches_jurisdiction,
                    candidate_snapshot_json,
                    direct_parent_status, direct_parent_lei,
                    direct_parent_legal_name,
                    direct_parent_relationship_type,
                    direct_parent_exception_reason,
                    direct_parent_evidence_url, direct_parent_raw_json,
                    ultimate_parent_status, ultimate_parent_lei,
                    ultimate_parent_legal_name,
                    ultimate_parent_relationship_type,
                    ultimate_parent_exception_reason,
                    ultimate_parent_evidence_url, ultimate_parent_raw_json,
                    observed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    row["outcome_record_id"],
                    row["certification_month"],
                    row["ultimate_control_country"],
                    row["ultimate_control_country_iso2"],
                    row["investor_name"],
                    row["investor_locality"],
                    row["investor_role_status"],
                    row["canadian_entry_corporation_number"],
                    row["resolution_status"],
                    row["query_url"],
                    row["golden_copy_publish_date"],
                    row["total_gleif_results"],
                    row["returned_candidate_count"],
                    row["exact_name_candidate_count"],
                    row["locality_match_candidate_count"],
                    row["confirmed_lei"],
                    row["confirmed_legal_name"],
                    row["confirmed_jurisdiction"],
                    row["confirmed_registered_as"],
                    row["confirmed_registration_authority_id"],
                    row["confirmed_legal_city"],
                    row["confirmed_headquarters_city"],
                    int(row["control_country_matches_jurisdiction"]),
                    row["candidate_snapshot_json"],
                    direct["status"],
                    direct["lei"],
                    direct["legal_name"],
                    direct["relationship_type"],
                    direct["exception_reason"],
                    direct["evidence_url"],
                    direct["raw_json"],
                    ultimate["status"],
                    ultimate["lei"],
                    ultimate["legal_name"],
                    ultimate["relationship_type"],
                    ultimate["exception_reason"],
                    ultimate["evidence_url"],
                    ultimate["raw_json"],
                    observed_at,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    statuses = Counter(row["resolution_status"] for row in rows)
    direct_statuses = Counter(
        row["direct_parent"]["status"]
        for row in rows
        if row["resolution_status"] in {
            "CONFIRMED_FOREIGN_NAMED_ENTITY",
            "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED",
        }
    )
    ultimate_statuses = Counter(
        row["ultimate_parent"]["status"]
        for row in rows
        if row["resolution_status"] in {
            "CONFIRMED_FOREIGN_NAMED_ENTITY",
            "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED",
        }
    )

    return {
        "run_id": run_id,
        "entry_identity_run_id": entry_run_id,
        "target_records": len(targets),
        "queried_investors": queried,
        "status_counts": dict(sorted(statuses.items())),
        "confirmed_foreign_named_entities":
            statuses["CONFIRMED_FOREIGN_NAMED_ENTITY"],
        "confirmed_canadian_named_investor_parent_unresolved":
            statuses["CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED"],
        "confirmed_named_entities_total": (
            statuses["CONFIRMED_FOREIGN_NAMED_ENTITY"]
            + statuses[
                "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED"
            ]
        ),
        "review_ready_exact_names": statuses["REVIEW_READY_EXACT_NAME"],
        "canadian_vehicle_parent_unresolved":
            statuses["CANADIAN_VEHICLE_PARENT_UNRESOLVED"],
        "direct_parent_status_counts": dict(sorted(direct_statuses.items())),
        "ultimate_parent_status_counts": dict(sorted(ultimate_statuses.items())),
        "confirmed_entities": [
            {
                "outcome_record_id": row["outcome_record_id"],
                "resolution_status": row["resolution_status"],
                "investor_name": row["investor_name"],
                "investor_locality": row["investor_locality"],
                "ultimate_control_country":
                    row["ultimate_control_country"],
                "lei": row["confirmed_lei"],
                "legal_name": row["confirmed_legal_name"],
                "jurisdiction": row["confirmed_jurisdiction"],
                "control_country_matches_jurisdiction":
                    row["control_country_matches_jurisdiction"],
                "direct_parent_status":
                    row["direct_parent"]["status"],
                "direct_parent_lei":
                    row["direct_parent"]["lei"],
                "direct_parent_legal_name":
                    row["direct_parent"]["legal_name"],
                "direct_parent_exception_reason":
                    row["direct_parent"]["exception_reason"],
                "ultimate_parent_status":
                    row["ultimate_parent"]["status"],
                "ultimate_parent_lei":
                    row["ultimate_parent"]["lei"],
                "ultimate_parent_legal_name":
                    row["ultimate_parent"]["legal_name"],
                "ultimate_parent_exception_reason":
                    row["ultimate_parent"]["exception_reason"],
            }
            for row in rows
            if row["resolution_status"] in {
                "CONFIRMED_FOREIGN_NAMED_ENTITY",
                "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED",
            }
        ],
    }


def foreign_identity_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_foreign_identity_schema(conn)
    run = conn.execute(
        """
        SELECT *
        FROM foreign_identity_runs
        ORDER BY observed_at DESC
        LIMIT 1
        """
    ).fetchone()
    if run is None:
        return {"run_present": False}

    run_id = run["run_id"]
    status_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT resolution_status, COUNT(*) AS records
            FROM foreign_identity_resolutions
            WHERE run_id = ?
            GROUP BY resolution_status
            ORDER BY resolution_status
            """,
            (run_id,),
        )
    ]
    confirmed = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                outcome_record_id,
                resolution_status,
                investor_name,
                investor_locality,
                ultimate_control_country,
                confirmed_lei,
                confirmed_legal_name,
                confirmed_jurisdiction,
                direct_parent_status,
                direct_parent_lei,
                direct_parent_legal_name,
                direct_parent_exception_reason,
                ultimate_parent_status,
                ultimate_parent_lei,
                ultimate_parent_legal_name,
                ultimate_parent_exception_reason
            FROM foreign_identity_resolutions
            WHERE run_id = ?
              AND resolution_status IN (
                  'CONFIRMED_FOREIGN_NAMED_ENTITY',
                  'CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED'
              )
            ORDER BY certification_month, investor_name
            """,
            (run_id,),
        )
    ]
    return {
        "run_present": True,
        "run_id": run_id,
        "entry_identity_run_id": run["entry_identity_run_id"],
        "target_records": run["target_records"],
        "queried_investors": run["queried_investors"],
        "status_counts": status_counts,
        "confirmed_entities": confirmed,
    }
