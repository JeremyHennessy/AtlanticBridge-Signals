from __future__ import annotations

import collections
import json
import re
import time

from atlanticbridge.constants import EU27
from atlanticbridge.sources.gleif import normalize_entity_name, search_legal_name
from atlanticbridge.sources.investment_canada import crawl_investment_canada_history

EU_ISO2 = {
    "Austria": "AT", "Belgium": "BE", "Bulgaria": "BG", "Croatia": "HR",
    "Cyprus": "CY", "Czechia": "CZ", "Denmark": "DK", "Estonia": "EE",
    "Finland": "FI", "France": "FR", "Germany": "DE", "Greece": "GR",
    "Hungary": "HU", "Ireland": "IE", "Italy": "IT", "Latvia": "LV",
    "Lithuania": "LT", "Luxembourg": "LU", "Malta": "MT", "Netherlands": "NL",
    "Poland": "PL", "Portugal": "PT", "Romania": "RO", "Slovakia": "SK",
    "Slovenia": "SI", "Spain": "ES", "Sweden": "SE",
}

START = "2019-01"
END = "2025-12"
SAMPLE_PER_YEAR = 3


def business_names(record) -> list[str]:
    try:
        rows = json.loads(record.canadian_businesses_json)
    except json.JSONDecodeError:
        return []
    return [
        " ".join((row.get("name") or "").split()).strip()
        for row in rows
        if isinstance(row, dict) and (row.get("name") or "").strip()
    ]


def status_for(result) -> tuple[str, int]:
    exact_country = [
        candidate
        for candidate in result.candidates
        if candidate.match_class == "EXACT_NAME_COUNTRY"
    ]
    if not result.candidates:
        return "NO_RESULTS", 0
    if len(exact_country) == 1:
        return "REVIEW_READY", 1
    if len(exact_country) > 1:
        return "AMBIGUOUS", len(exact_country)
    return "UNRESOLVED", 0


crawl = crawl_investment_canada_history(workers=4)

cohort = [
    record
    for record in crawl.records
    if record.is_eu27
    and record.is_new_business
    and START <= record.certification_month <= END
]

by_year = collections.Counter(record.certification_month[:4] for record in cohort)
by_country = collections.Counter(record.country_of_ultimate_control for record in cohort)

same_business_name = 0
empty_structured_name = 0
names_with_canada_token = 0
for record in cohort:
    if not record.investor_name:
        empty_structured_name += 1
    investor_norm = normalize_entity_name(record.investor_name)
    if any(
        investor_norm
        and investor_norm == normalize_entity_name(name)
        for name in business_names(record)
    ):
        same_business_name += 1
    if re.search(r"\bcanada\b", record.investor_name, flags=re.IGNORECASE):
        names_with_canada_token += 1

# Deterministic recent sample: at most 3 entrants per outcome year, favoring
# different countries before repeating a country.
sample = []
for year in sorted(by_year, reverse=True):
    candidates = sorted(
        [r for r in cohort if r.certification_month.startswith(year)],
        key=lambda r: (
            r.country_of_ultimate_control,
            normalize_entity_name(r.investor_name),
            r.investor_node_id,
        ),
    )
    chosen = []
    seen_countries = set()
    for record in candidates:
        if record.country_of_ultimate_control in seen_countries:
            continue
        chosen.append(record)
        seen_countries.add(record.country_of_ultimate_control)
        if len(chosen) >= SAMPLE_PER_YEAR:
            break
    if len(chosen) < SAMPLE_PER_YEAR:
        for record in candidates:
            if record in chosen:
                continue
            chosen.append(record)
            if len(chosen) >= SAMPLE_PER_YEAR:
                break
    sample.extend(chosen)

resolution_rows = []
status_counts = collections.Counter()
match_class_counts = collections.Counter()

for index, record in enumerate(sample):
    source_country = EU_ISO2[record.country_of_ultimate_control]
    result = search_legal_name(
        record.investor_name,
        source_country=source_country,
        page_size=5,
    )
    status, exact_count = status_for(result)
    status_counts[status] += 1
    for candidate in result.candidates:
        match_class_counts[candidate.match_class] += 1

    top = result.candidates[0] if result.candidates else None
    resolution_rows.append(
        {
            "certification_month": record.certification_month,
            "country": record.country_of_ultimate_control,
            "source_country_iso2": source_country,
            "investor_name": record.investor_name,
            "investor_locality": record.investor_locality,
            "investor_node_id": record.investor_node_id,
            "canadian_business_names": business_names(record),
            "status": status,
            "total_gleif_results": result.total_results,
            "returned_candidates": len(result.candidates),
            "exact_name_country_candidates": exact_count,
            "top_candidate": (
                {
                    "lei": top.lei,
                    "legal_name": top.legal_name,
                    "jurisdiction": top.jurisdiction,
                    "match_class": top.match_class,
                    "name_similarity": top.name_similarity,
                    "entity_status": top.entity_status,
                }
                if top
                else None
            ),
            "golden_copy_publish_date": result.golden_copy_publish_date,
        }
    )
    if index < len(sample) - 1:
        time.sleep(0.1)

print(
    json.dumps(
        {
            "window": {"start": START, "end": END},
            "history_unique_records": crawl.unique_records,
            "cohort_records": len(cohort),
            "cohort_unique_investor_nodes": len({r.investor_node_id for r in cohort}),
            "cohort_by_year": dict(sorted(by_year.items())),
            "cohort_by_country": dict(
                sorted(by_country.items(), key=lambda item: (-item[1], item[0]))
            ),
            "structured_name_missing": empty_structured_name,
            "investor_name_equals_canadian_business_name": same_business_name,
            "investor_name_contains_canada_token": names_with_canada_token,
            "sample_size": len(sample),
            "sample_by_year": dict(
                sorted(collections.Counter(r.certification_month[:4] for r in sample).items())
            ),
            "sample_by_country": dict(
                sorted(
                    collections.Counter(r.country_of_ultimate_control for r in sample).items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            "gleif_status_counts": dict(sorted(status_counts.items())),
            "gleif_match_class_counts": dict(sorted(match_class_counts.items())),
            "resolution_rows": resolution_rows,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
