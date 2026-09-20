from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path

from .sources.corporations_canada import (
    ACTIVE_BUSINESS_URL,
    INACTIVE_BUSINESS_URL,
    CorporationCanadaRecord,
    DownloadResult,
    detail_corporation_names,
    download_active_business_csv,
    download_inactive_business_csv,
    fetch_corporation_json,
    first_federal_jurisdiction_event,
    iter_active_business_csv,
    iter_inactive_business_csv,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS entry_identity_runs (
    run_id TEXT PRIMARY KEY,
    start_month TEXT NOT NULL,
    end_month TEXT NOT NULL,
    active_source_sha256 TEXT NOT NULL,
    active_source_bytes INTEGER NOT NULL,
    inactive_source_sha256 TEXT NOT NULL,
    inactive_source_bytes INTEGER NOT NULL,
    cohort_records INTEGER NOT NULL,
    detail_limit INTEGER NOT NULL,
    gold_limit INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_identity_matches (
    run_id TEXT NOT NULL,
    outcome_record_id TEXT NOT NULL,
    certification_month TEXT NOT NULL,
    ultimate_control_country TEXT NOT NULL,
    investor_name TEXT NOT NULL,
    investor_locality TEXT NOT NULL,
    source_businesses_json TEXT NOT NULL DEFAULT '[]',
    matched_business_name TEXT NOT NULL,
    match_status TEXT NOT NULL,
    candidate_count INTEGER NOT NULL,
    geo_candidate_count INTEGER NOT NULL,
    selected_corporation_number TEXT NOT NULL,
    selected_business_number TEXT NOT NULL,
    selected_source_state TEXT NOT NULL,
    selected_corporate_name TEXT NOT NULL,
    selected_city TEXT NOT NULL,
    selected_province TEXT NOT NULL,
    city_match INTEGER NOT NULL CHECK (city_match IN (0, 1)),
    province_match INTEGER NOT NULL CHECK (province_match IN (0, 1)),
    detail_status TEXT NOT NULL,
    detail_source_url TEXT NOT NULL,
    detail_name_match INTEGER NOT NULL CHECK (detail_name_match IN (0, 1)),
    detail_raw_hash TEXT NOT NULL,
    detail_raw_json TEXT NOT NULL,
    federal_event_type TEXT NOT NULL,
    federal_event_date TEXT NOT NULL,
    timing_status TEXT NOT NULL,
    lead_days_to_outcome_month_start INTEGER,
    investor_role_status TEXT NOT NULL,
    gold_selected INTEGER NOT NULL CHECK (gold_selected IN (0, 1)),
    gold_rank INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (run_id, outcome_record_id),
    FOREIGN KEY (run_id) REFERENCES entry_identity_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entry_identity_status
ON entry_identity_matches(run_id, match_status);

CREATE INDEX IF NOT EXISTS idx_entry_identity_gold
ON entry_identity_matches(run_id, gold_selected, gold_rank);

CREATE INDEX IF NOT EXISTS idx_entry_identity_corp
ON entry_identity_matches(selected_corporation_number);
"""

_PROVINCE_ALIASES = {
    "ab": "alberta",
    "alberta": "alberta",
    "bc": "british columbia",
    "british columbia": "british columbia",
    "mb": "manitoba",
    "manitoba": "manitoba",
    "nb": "new brunswick",
    "new brunswick": "new brunswick",
    "nl": "newfoundland and labrador",
    "newfoundland and labrador": "newfoundland and labrador",
    "ns": "nova scotia",
    "nova scotia": "nova scotia",
    "nt": "northwest territories",
    "northwest territories": "northwest territories",
    "nu": "nunavut",
    "nunavut": "nunavut",
    "on": "ontario",
    "ontario": "ontario",
    "pe": "prince edward island",
    "pei": "prince edward island",
    "prince edward island": "prince edward island",
    "qc": "quebec",
    "quebec": "quebec",
    "québec": "quebec",
    "sk": "saskatchewan",
    "saskatchewan": "saskatchewan",
    "yt": "yukon",
    "yukon": "yukon",
}


_ENTRY_IDENTITY_MIGRATION_COLUMNS = {
    "source_businesses_json": "TEXT NOT NULL DEFAULT '[]'",
}


def ensure_entry_identity_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(entry_identity_matches)")
    }
    for column, declaration in _ENTRY_IDENTITY_MIGRATION_COLUMNS.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE entry_identity_matches "
                f"ADD COLUMN {column} {declaration}"
            )
    conn.commit()


def normalize_legal_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


def _province_match(source: str, target: str) -> bool:
    source_key = _PROVINCE_ALIASES.get(_clean(source).casefold(), "")
    target_key = _PROVINCE_ALIASES.get(_clean(target).casefold(), "")
    return bool(source_key) and source_key == target_key


def _city_match(source: str, target: str) -> bool:
    return (
        bool(_clean(source))
        and bool(_clean(target))
        and normalize_legal_name(source) == normalize_legal_name(target)
    )


def _businesses(raw_json: str) -> list[dict]:
    try:
        rows = json.loads(raw_json)
    except json.JSONDecodeError:
        return []
    return [row for row in rows if isinstance(row, dict)]


def _cohort(conn: sqlite3.Connection, start_month: str, end_month: str):
    return conn.execute(
        """
        SELECT
            record_id,
            certification_month,
            country_of_ultimate_control,
            investor_name,
            investor_locality,
            canadian_businesses_json
        FROM investment_canada_notifications
        WHERE is_eu27 = 1
          AND is_new_business = 1
          AND certification_month BETWEEN ? AND ?
        ORDER BY certification_month, record_id
        """,
        (start_month, end_month),
    ).fetchall()


def _target_names(cohort_rows) -> set[str]:
    result: set[str] = set()
    for row in cohort_rows:
        for business in _businesses(row["canadian_businesses_json"]):
            key = normalize_legal_name(_clean(business.get("name")))
            if key:
                result.add(key)
    return result


def _scan_target_corporations(
    active_path: Path,
    inactive_path: Path,
    target_names: set[str],
):
    index: dict[str, dict[str, CorporationCanadaRecord]] = defaultdict(dict)
    total_scanned = 0

    sources = (
        iter_active_business_csv(active_path, source_url=ACTIVE_BUSINESS_URL),
        iter_inactive_business_csv(inactive_path, source_url=INACTIVE_BUSINESS_URL),
    )
    for records in sources:
        for record in records:
            total_scanned += 1
            matched_keys = {
                key
                for key in (
                    normalize_legal_name(record.corporate_name_form_1),
                    normalize_legal_name(record.corporate_name_form_2),
                )
                if key and key in target_names
            }
            for key in matched_keys:
                existing = index[key].get(record.corporation_number)
                if existing is not None and existing.record_hash != record.record_hash:
                    raise ValueError(
                        "Conflicting Corporations Canada records for "
                        f"{record.corporation_number}"
                    )
                index[key][record.corporation_number] = record

    return index, total_scanned


def _bulk_match(row, index):
    candidates: dict[str, dict] = {}
    for business in _businesses(row["canadian_businesses_json"]):
        business_name = _clean(business.get("name"))
        key = normalize_legal_name(business_name)
        if not key:
            continue
        for corp in index.get(key, {}).values():
            item = {
                "record": corp,
                "matched_business_name": business_name,
                "investment_locality": _clean(business.get("locality")),
                "investment_admin_area": _clean(
                    business.get("administrative_area")
                ),
                "province_match": _province_match(
                    _clean(business.get("administrative_area")),
                    corp.province_territory,
                ),
                "city_match": _city_match(
                    _clean(business.get("locality")),
                    corp.city_town,
                ),
            }
            candidates[corp.corporation_number] = item

    rows = list(candidates.values())
    geo = [
        item
        for item in rows
        if item["province_match"] or item["city_match"]
    ]

    if not rows:
        return "NO_FEDERAL_EXACT_MATCH", None, 0, 0
    if len(rows) == 1:
        return (
            "UNIQUE_EXACT_GEO" if geo else "UNIQUE_EXACT_NAME_ONLY",
            rows[0],
            1,
            len(geo),
        )
    if len(geo) == 1:
        return "MULTI_EXACT_ONE_GEO", geo[0], len(rows), 1
    return "AMBIGUOUS_EXACT", None, len(rows), len(geo)


def _quality(match_status: str) -> int:
    return {
        "UNIQUE_EXACT_GEO": 0,
        "MULTI_EXACT_ONE_GEO": 1,
        "UNIQUE_EXACT_NAME_ONLY": 2,
    }.get(match_status, 99)


def _balanced_candidates(rows: list[dict], limit: int) -> list[dict]:
    eligible = [
        row for row in rows
        if row["selected"] is not None
    ]
    eligible.sort(
        key=lambda row: (
            _quality(row["match_status"]),
            row["certification_month"],
            row["country"],
            row["outcome_record_id"],
        )
    )

    groups: dict[tuple[int, str, str], list[dict]] = defaultdict(list)
    for row in eligible:
        groups[
            (
                _quality(row["match_status"]),
                row["certification_month"][:4],
                row["country"],
            )
        ].append(row)

    ordered_keys = sorted(groups)
    selected: list[dict] = []
    while ordered_keys and len(selected) < limit:
        remaining = []
        for key in ordered_keys:
            bucket = groups[key]
            if bucket and len(selected) < limit:
                selected.append(bucket.pop(0))
            if bucket:
                remaining.append(key)
        ordered_keys = remaining
    return selected


def _role_status(row: dict, detail_names: tuple[str, ...]) -> str:
    investor = normalize_legal_name(row["investor_name"])
    business_names = {
        normalize_legal_name(_clean(item.get("name")))
        for item in _businesses(row["canadian_businesses_json"])
        if _clean(item.get("name"))
    }
    detail_normalized = {
        normalize_legal_name(name)
        for name in detail_names
    }
    if investor and (investor in business_names or investor in detail_normalized):
        return "CANADIAN_VEHICLE_CONFIRMED"
    if re.search(r"\bcanada\b", row["investor_name"], flags=re.IGNORECASE):
        return "CANADIAN_VEHICLE_LIKELY"
    return "DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION"


def _lead_timing(certification_month: str, event_date: str):
    if not event_date:
        return "UNKNOWN", None
    outcome_date = date.fromisoformat(certification_month + "-01")
    source_date = date.fromisoformat(event_date)
    lead_days = (outcome_date - source_date).days
    if source_date < outcome_date:
        return "BEFORE_NOTIFICATION_MONTH", lead_days
    if source_date.year == outcome_date.year and source_date.month == outcome_date.month:
        return "SAME_MONTH", lead_days
    return "AFTER_OUTCOME_MONTH_START", lead_days


def _run_id(
    start_month: str,
    end_month: str,
    active_sha: str,
    inactive_sha: str,
) -> str:
    material = "\x1f".join(
        [start_month, end_month, active_sha, inactive_sha]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def run_entry_identity_resolution(
    conn: sqlite3.Connection,
    *,
    workdir: str | Path,
    start_month: str = "2019-01",
    end_month: str = "2025-12",
    gold_limit: int = 100,
    detail_limit: int = 140,
    detail_delay_seconds: float = 0.05,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_entry_identity_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    cohort_rows = _cohort(conn, start_month, end_month)
    if not cohort_rows:
        raise ValueError(
            "No EU new-business Investment Canada outcomes found in requested window"
        )

    active = download_active_business_csv(workdir / "active-cbca.csv")
    inactive = download_inactive_business_csv(workdir / "inactive-cbca.csv")

    names = _target_names(cohort_rows)
    index, scanned = _scan_target_corporations(
        active.path,
        inactive.path,
        names,
    )

    rows: list[dict] = []
    for outcome in cohort_rows:
        status, selected, candidate_count, geo_count = _bulk_match(
            outcome,
            index,
        )
        selected_record = selected["record"] if selected else None
        rows.append(
            {
                "outcome_record_id": outcome["record_id"],
                "certification_month": outcome["certification_month"],
                "country": outcome["country_of_ultimate_control"],
                "investor_name": outcome["investor_name"],
                "investor_locality": outcome["investor_locality"],
                "canadian_businesses_json": outcome["canadian_businesses_json"],
                "match_status": status,
                "candidate_count": candidate_count,
                "geo_candidate_count": geo_count,
                "selected": selected,
                "selected_record": selected_record,
                "detail_status": "NOT_ATTEMPTED",
                "detail_source_url": "",
                "detail_name_match": False,
                "detail_raw_hash": "",
                "detail_raw_json": "{}",
                "federal_event_type": "",
                "federal_event_date": "",
                "timing_status": "UNKNOWN",
                "lead_days": None,
                "investor_role_status": "UNRESOLVED",
                "gold_selected": False,
                "gold_rank": 0,
            }
        )

    detail_candidates = _balanced_candidates(rows, detail_limit)
    for index_number, row in enumerate(detail_candidates):
        selected = row["selected"]
        assert selected is not None
        record = selected["record"]
        try:
            url, payload = fetch_corporation_json(record.corporation_number)
            raw_json = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            names_in_detail = detail_corporation_names(payload)
            matched_norm = normalize_legal_name(
                selected["matched_business_name"]
            )
            name_match = matched_norm in {
                normalize_legal_name(name)
                for name in names_in_detail
            }
            event_type, event_date = first_federal_jurisdiction_event(payload)
            timing_status, lead_days = _lead_timing(
                row["certification_month"],
                event_date,
            )
            row.update(
                {
                    "detail_status": (
                        "FEDERAL_ENTITY_CONFIRMED"
                        if name_match
                        else "DETAIL_NAME_MISMATCH"
                    ),
                    "detail_source_url": url,
                    "detail_name_match": name_match,
                    "detail_raw_hash": hashlib.sha256(
                        raw_json.encode("utf-8")
                    ).hexdigest(),
                    "detail_raw_json": raw_json,
                    "federal_event_type": event_type,
                    "federal_event_date": event_date,
                    "timing_status": timing_status,
                    "lead_days": lead_days,
                    "investor_role_status": _role_status(
                        row,
                        names_in_detail,
                    ),
                }
            )
        except Exception as exc:
            row["detail_status"] = f"DETAIL_ERROR:{type(exc).__name__}"

        if detail_delay_seconds > 0 and index_number < len(detail_candidates) - 1:
            time.sleep(detail_delay_seconds)

    confirmed = [
        row for row in rows
        if row["detail_status"] == "FEDERAL_ENTITY_CONFIRMED"
    ]
    gold_rows = _balanced_candidates(confirmed, gold_limit)
    for rank, row in enumerate(gold_rows, start=1):
        row["gold_selected"] = True
        row["gold_rank"] = rank

    run_id = _run_id(
        start_month,
        end_month,
        active.sha256,
        inactive.sha256,
    )

    conn.execute("BEGIN")
    try:
        conn.execute(
            "DELETE FROM entry_identity_matches WHERE run_id = ?",
            (run_id,),
        )
        conn.execute(
            "DELETE FROM entry_identity_runs WHERE run_id = ?",
            (run_id,),
        )
        conn.execute(
            """
            INSERT INTO entry_identity_runs (
                run_id, start_month, end_month,
                active_source_sha256, active_source_bytes,
                inactive_source_sha256, inactive_source_bytes,
                cohort_records, detail_limit, gold_limit, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                start_month,
                end_month,
                active.sha256,
                active.byte_count,
                inactive.sha256,
                inactive.byte_count,
                len(cohort_rows),
                detail_limit,
                gold_limit,
                observed_at,
            ),
        )

        for row in rows:
            selected = row["selected"]
            record = row["selected_record"]
            conn.execute(
                """
                INSERT INTO entry_identity_matches (
                    run_id, outcome_record_id, certification_month,
                    ultimate_control_country, investor_name, investor_locality,
                    source_businesses_json, matched_business_name,
                    match_status, candidate_count,
                    geo_candidate_count, selected_corporation_number,
                    selected_business_number, selected_source_state,
                    selected_corporate_name, selected_city, selected_province,
                    city_match, province_match, detail_status,
                    detail_source_url, detail_name_match, detail_raw_hash,
                    detail_raw_json, federal_event_type, federal_event_date,
                    timing_status, lead_days_to_outcome_month_start,
                    investor_role_status, gold_selected, gold_rank, observed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    row["outcome_record_id"],
                    row["certification_month"],
                    row["country"],
                    row["investor_name"],
                    row["investor_locality"],
                    row["canadian_businesses_json"],
                    selected["matched_business_name"] if selected else "",
                    row["match_status"],
                    row["candidate_count"],
                    row["geo_candidate_count"],
                    record.corporation_number if record else "",
                    record.business_number if record else "",
                    record.source_state if record else "",
                    (
                        record.corporate_name_form_1
                        or record.corporate_name_form_2
                        if record
                        else ""
                    ),
                    record.city_town if record else "",
                    record.province_territory if record else "",
                    int(bool(selected and selected["city_match"])),
                    int(bool(selected and selected["province_match"])),
                    row["detail_status"],
                    row["detail_source_url"],
                    int(row["detail_name_match"]),
                    row["detail_raw_hash"],
                    row["detail_raw_json"],
                    row["federal_event_type"],
                    row["federal_event_date"],
                    row["timing_status"],
                    row["lead_days"],
                    row["investor_role_status"],
                    int(row["gold_selected"]),
                    row["gold_rank"],
                    observed_at,
                ),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    match_counts = Counter(row["match_status"] for row in rows)
    detail_counts = Counter(row["detail_status"] for row in rows)
    role_counts = Counter(row["investor_role_status"] for row in confirmed)
    timing_counts = Counter(row["timing_status"] for row in confirmed)
    leads = [
        row["lead_days"]
        for row in confirmed
        if row["timing_status"] == "BEFORE_NOTIFICATION_MONTH"
        and row["lead_days"] is not None
    ]

    return {
        "run_id": run_id,
        "window": {"start": start_month, "end": end_month},
        "cohort_records": len(cohort_rows),
        "target_business_names": len(names),
        "federal_records_scanned": scanned,
        "active_source_sha256": active.sha256,
        "active_source_bytes": active.byte_count,
        "inactive_source_sha256": inactive.sha256,
        "inactive_source_bytes": inactive.byte_count,
        "match_status_counts": dict(sorted(match_counts.items())),
        "detail_status_counts": dict(sorted(detail_counts.items())),
        "confirmed_entry_entities": len(confirmed),
        "confirmed_share_percent": round(
            100 * len(confirmed) / len(cohort_rows),
            2,
        ),
        "gold_selected": len(gold_rows),
        "gold_target": gold_limit,
        "unresolved_by_province": _unresolved_by_province(conn, run_id),
        "investor_role_counts": dict(sorted(role_counts.items())),
        "timing_status_counts": dict(sorted(timing_counts.items())),
        "notification_lead_days": {
            "count": len(leads),
            "median": statistics.median(leads) if leads else None,
            "p25": (
                statistics.quantiles(leads, n=4, method="inclusive")[0]
                if len(leads) >= 2
                else None
            ),
            "p75": (
                statistics.quantiles(leads, n=4, method="inclusive")[2]
                if len(leads) >= 2
                else None
            ),
        },
        "gold_sample": [
            {
                "rank": row["gold_rank"],
                "outcome_record_id": row["outcome_record_id"],
                "certification_month": row["certification_month"],
                "country": row["country"],
                "investor_name": row["investor_name"],
                "matched_business_name": row["selected"]["matched_business_name"],
                "corporation_number": row["selected_record"].corporation_number,
                "source_state": row["selected_record"].source_state,
                "federal_event_type": row["federal_event_type"],
                "federal_event_date": row["federal_event_date"],
                "timing_status": row["timing_status"],
                "lead_days": row["lead_days"],
                "investor_role_status": row["investor_role_status"],
                "detail_source_url": row["detail_source_url"],
            }
            for row in gold_rows[:20]
        ],
    }




def _unresolved_by_province(conn: sqlite3.Connection, run_id: str) -> list[dict[str, object]]:
    counts: Counter[str] = Counter()
    rows = conn.execute(
        """
        SELECT outcome_record_id, source_businesses_json
        FROM entry_identity_matches
        WHERE run_id = ?
          AND detail_status <> 'FEDERAL_ENTITY_CONFIRMED'
        """,
        (run_id,),
    )
    for row in rows:
        provinces = {
            _clean(item.get("administrative_area")) or "UNKNOWN"
            for item in _businesses(row["source_businesses_json"])
        }
        if not provinces:
            provinces = {"UNKNOWN"}
        for province in provinces:
            counts[province] += 1
    return [
        {"province": province, "outcomes": count}
        for province, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]

def entry_identity_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_entry_identity_schema(conn)
    run = conn.execute(
        """
        SELECT *
        FROM entry_identity_runs
        ORDER BY observed_at DESC
        LIMIT 1
        """
    ).fetchone()
    if run is None:
        return {"run_present": False}

    run_id = run["run_id"]
    match_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT match_status, COUNT(*) AS records
            FROM entry_identity_matches
            WHERE run_id = ?
            GROUP BY match_status
            ORDER BY match_status
            """,
            (run_id,),
        )
    ]
    detail_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT detail_status, COUNT(*) AS records
            FROM entry_identity_matches
            WHERE run_id = ?
            GROUP BY detail_status
            ORDER BY detail_status
            """,
            (run_id,),
        )
    ]
    timing_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT timing_status, COUNT(*) AS records
            FROM entry_identity_matches
            WHERE run_id = ?
              AND detail_status = 'FEDERAL_ENTITY_CONFIRMED'
            GROUP BY timing_status
            ORDER BY timing_status
            """,
            (run_id,),
        )
    ]
    gold = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                gold_rank,
                outcome_record_id,
                certification_month,
                ultimate_control_country,
                investor_name,
                matched_business_name,
                selected_corporation_number,
                selected_source_state,
                federal_event_type,
                federal_event_date,
                timing_status,
                lead_days_to_outcome_month_start,
                investor_role_status,
                detail_source_url
            FROM entry_identity_matches
            WHERE run_id = ?
              AND gold_selected = 1
            ORDER BY gold_rank
            """,
            (run_id,),
        )
    ]
    confirmed = conn.execute(
        """
        SELECT COUNT(*)
        FROM entry_identity_matches
        WHERE run_id = ?
          AND detail_status = 'FEDERAL_ENTITY_CONFIRMED'
        """,
        (run_id,),
    ).fetchone()[0]

    return {
        "run_present": True,
        "run_id": run_id,
        "window": {
            "start": run["start_month"],
            "end": run["end_month"],
        },
        "cohort_records": run["cohort_records"],
        "confirmed_entry_entities": confirmed,
        "gold_selected": len(gold),
        "match_status_counts": match_counts,
        "detail_status_counts": detail_counts,
        "timing_status_counts": timing_counts,
        "unresolved_by_province": _unresolved_by_province(conn, run_id),
        "gold_cohort": gold,
    }
