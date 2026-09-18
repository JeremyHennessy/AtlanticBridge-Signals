from __future__ import annotations

import collections
import json
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

from atlanticbridge.sources.gleif import normalize_entity_name
from atlanticbridge.sources.investment_canada import crawl_investment_canada_history
from atlanticbridge.sources.ted import (
    AWARD_FIELDS,
    AWARD_NOTICE_TYPES,
    _post_json,
)

START = "2019-01"
END = "2025-12"
REQUESTED_YEARS = tuple(
    year.strip()
    for year in os.environ.get(
        "ATLANTICBRIDGE_YEARS",
        "2019,2020,2021,2022,2023,2024,2025",
    ).split(",")
    if year.strip()
)
if not REQUESTED_YEARS:
    raise RuntimeError("ATLANTICBRIDGE_YEARS resolved to no years")
WORKERS = 4
PAGE_SIZE = 250


def month_start(value: str) -> date:
    year, month = value.split("-", 1)
    return date(int(year), int(month), 1)


def add_months(value: date, delta: int) -> date:
    month_index = (value.year * 12 + value.month - 1) + delta
    year, month_zero = divmod(month_index, 12)
    return date(year, month_zero + 1, 1)


def ted_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def escape_ted_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def winner_names(payload: dict[str, object]) -> list[str]:
    raw = payload.get("winner-name")
    values: list[str] = []
    if isinstance(raw, dict):
        candidates = raw.values()
    else:
        candidates = [raw]

    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, list):
            for value in candidate:
                if value is not None:
                    values.append(" ".join(str(value).split()).strip())
        else:
            values.append(" ".join(str(candidate).split()).strip())
    return [value for value in values if value]


def publication_day(payload: dict[str, object]) -> date | None:
    raw = str(payload.get("publication-date") or "").strip()
    if len(raw) < 10:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def exact_name_present(payload: dict[str, object], source_name: str) -> bool:
    source_norm = normalize_entity_name(source_name)
    return any(
        normalize_entity_name(name) == source_norm
        for name in winner_names(payload)
    )


def query_outcome(record) -> dict[str, object]:
    outcome_start = month_start(record.certification_month)
    window_start = add_months(outcome_start, -24)
    window_end = outcome_start - timedelta(days=1)
    source_name = record.investor_name.strip()

    query = (
        f"publication-date = ({ted_date(window_start)} <> {ted_date(window_end)}) "
        f"AND notice-type IN ({' '.join(AWARD_NOTICE_TYPES)}) "
        "AND winner-selection-status IN (selec-w) "
        f'AND winner-name = "{escape_ted_string(source_name)}"'
    )

    first_body = {
        "query": query,
        "fields": list(AWARD_FIELDS),
        "page": 1,
        "limit": PAGE_SIZE,
        "scope": "ALL",
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
        "onlyLatestVersions": False,
    }

    page = 1
    total_count: int | None = None
    notices: list[dict[str, object]] = []

    while True:
        body = dict(first_body)
        body["page"] = page
        payload = _post_json(body, timeout=60, attempts=3)
        if payload.get("timedOut") is True:
            raise RuntimeError(
                f"TED query timed out for investor_node_id={record.investor_node_id}"
            )

        page_notices = payload.get("notices") or []
        if not isinstance(page_notices, list):
            raise ValueError("TED notices response is not a list")

        if total_count is None:
            total_count = int(payload.get("totalNoticeCount") or len(page_notices))
            if total_count > 15000:
                raise ValueError(
                    f"TED result count exceeds page-mode cap for {source_name!r}: "
                    f"{total_count}"
                )

        for item in page_notices:
            if not isinstance(item, dict):
                raise ValueError("TED notice result is not an object")
            if not exact_name_present(item, source_name):
                raise ValueError(
                    "TED exact-name query returned a non-exact winner: "
                    f"source={source_name!r} winner_names={winner_names(item)!r}"
                )
            notices.append(item)

        if not page_notices:
            break
        if len(notices) >= total_count:
            break
        if len(page_notices) < PAGE_SIZE:
            break

        page += 1
        if page * PAGE_SIZE > 15000:
            raise ValueError(
                f"TED pagination cap reached for {source_name!r}; split required"
            )

    if total_count is None:
        total_count = len(notices)
    if len(notices) != total_count:
        raise ValueError(
            f"TED incomplete result for {source_name!r}: "
            f"expected={total_count} returned={len(notices)}"
        )

    days_before: list[int] = []
    cpv_values: set[str] = set()
    for notice in notices:
        day = publication_day(notice)
        if day is not None and day < outcome_start:
            days_before.append((outcome_start - day).days)

        raw_cpv = notice.get("classification-cpv")
        if isinstance(raw_cpv, list):
            cpv_values.update(str(value).strip() for value in raw_cpv if str(value).strip())
        elif raw_cpv:
            cpv_values.add(str(raw_cpv).strip())

    nearest = min(days_before) if days_before else None
    earliest = max(days_before) if days_before else None

    return {
        "record_id": record.record_id,
        "investor_node_id": record.investor_node_id,
        "certification_month": record.certification_month,
        "country": record.country_of_ultimate_control,
        "investor_name": source_name,
        "query_start": window_start.isoformat(),
        "query_end": window_end.isoformat(),
        "notice_count": len(notices),
        "nearest_lead_days": nearest,
        "earliest_lead_days": earliest,
        "within_3m": any(days <= 92 for days in days_before),
        "within_6m": any(days <= 184 for days in days_before),
        "within_12m": any(days <= 366 for days in days_before),
        "within_24m": bool(days_before),
        "publication_lead_days": sorted(days_before),
        "cpv_values": sorted(cpv_values),
        # This diagnostic measures raw exact-name procurement coverage only.
        # No TED record is score-eligible until a separate non-military
        # commercial classification layer is validated.
        "score_eligible": False,
    }


crawl = crawl_investment_canada_history(workers=4)
cohort = [
    record
    for record in crawl.records
    if record.is_eu27
    and record.is_new_business
    and START <= record.certification_month <= END
    and record.certification_month[:4] in REQUESTED_YEARS
]

results: list[dict[str, object]] = []
with ThreadPoolExecutor(max_workers=WORKERS) as executor:
    futures = {executor.submit(query_outcome, record): record for record in cohort}
    for future in as_completed(futures):
        results.append(future.result())

results.sort(
    key=lambda row: (
        row["certification_month"],
        row["country"],
        row["investor_name"],
        row["investor_node_id"],
    )
)

counts = {
    "any_exact_ted_award_24m": sum(bool(row["within_24m"]) for row in results),
    "within_12m": sum(bool(row["within_12m"]) for row in results),
    "within_6m": sum(bool(row["within_6m"]) for row in results),
    "within_3m": sum(bool(row["within_3m"]) for row in results),
}

all_notice_leads = [
    int(days)
    for row in results
    for days in row["publication_lead_days"]
]
nearest_leads = [
    int(row["nearest_lead_days"])
    for row in results
    if row["nearest_lead_days"] is not None
]

def quartiles(values: list[int]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "median": None, "p25": None, "p75": None}
    qs = (
        statistics.quantiles(values, n=4, method="inclusive")
        if len(values) >= 2
        else [values[0], values[0], values[0]]
    )
    return {
        "count": len(values),
        "median": statistics.median(values),
        "p25": qs[0],
        "p75": qs[2],
    }

by_year = collections.Counter(row["certification_month"][:4] for row in results)
signal_by_year = collections.Counter(
    row["certification_month"][:4]
    for row in results
    if row["within_24m"]
)
signal_by_country = collections.Counter(
    row["country"]
    for row in results
    if row["within_24m"]
)

output = {
    "window": {"start": START, "end": END},
    "requested_years": list(REQUESTED_YEARS),
    "cohort_records": len(cohort),
    "cohort_by_year": dict(sorted(by_year.items())),
    "query_workers": WORKERS,
    "lookback_months": 24,
    "raw_exact_name_ted_signal_counts": counts,
    "raw_exact_name_ted_signal_share_percent": {
        key: round(100 * value / len(cohort), 2) if cohort else 0
        for key, value in counts.items()
    },
    "signal_by_year": dict(sorted(signal_by_year.items())),
    "signal_by_country": dict(
        sorted(signal_by_country.items(), key=lambda item: (-item[1], item[0]))
    ),
    "nearest_signal_lead_days": quartiles(nearest_leads),
    "all_notice_lead_days": quartiles(all_notice_leads),
    "total_matching_award_notices": sum(int(row["notice_count"]) for row in results),
    "score_eligible_records": sum(bool(row["score_eligible"]) for row in results),
    "scoring_status": (
        "UNWEIGHTED_DIAGNOSTIC_ONLY: exact-name TED coverage measured, "
        "non-military commercial classification and control cohort not yet validated"
    ),
    "outcomes_with_ted_signal": [
        row for row in results if row["within_24m"]
    ],
}

print(json.dumps(output, indent=2, ensure_ascii=False, sort_keys=True))
