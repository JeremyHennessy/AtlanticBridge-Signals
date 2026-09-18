from __future__ import annotations

import collections
import statistics
import tempfile
from datetime import date
from pathlib import Path

import json

from atlanticbridge.sources.cordis import (
    HORIZON_ARCHIVE_URL,
    download_horizon_archive,
    iter_participations,
    iter_projects,
)
from atlanticbridge.sources.gleif import normalize_entity_name
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


def month_start(value: str) -> date:
    year, month = value.split("-", 1)
    return date(int(year), int(month), 1)


def iso_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


crawl = crawl_investment_canada_history(workers=4)
cohort = [
    record
    for record in crawl.records
    if record.is_eu27
    and record.is_new_business
    and START <= record.certification_month <= END
]

cohort_by_key = collections.defaultdict(list)
for record in cohort:
    key = (
        EU_ISO2[record.country_of_ultimate_control],
        normalize_entity_name(record.investor_name),
    )
    if key[1]:
        cohort_by_key[key].append(record)

with tempfile.TemporaryDirectory(prefix="atlanticbridge-cordis-feasibility-") as temp_dir:
    archive_path = Path(temp_dir) / "cordis-HORIZONprojects-csv.zip"
    download = download_horizon_archive(
        archive_path,
        source_url=HORIZON_ARCHIVE_URL,
    )

    projects = {project.project_id: project for project in iter_projects(download.path)}
    participations = list(iter_participations(download.path))

canada_projects = {
    row.project_id
    for row in participations
    if row.country == "CA"
}

cordis_index = collections.defaultdict(list)
for row in participations:
    key = (row.country, normalize_entity_name(row.name))
    if key in cohort_by_key:
        cordis_index[key].append(row)

matched_outcomes = set()
shared_canada_outcomes = set()
pre_entry_outcomes = set()
outcome_details = []
lead_days = []
matched_project_ids = set()

for key, records in cohort_by_key.items():
    rows = cordis_index.get(key, [])
    if not rows:
        continue

    for record in records:
        matched_outcomes.add(record.record_id)
        shared_rows = [
            row
            for row in rows
            if row.project_id in canada_projects
        ]
        if shared_rows:
            shared_canada_outcomes.add(record.record_id)

        pre_entry = []
        for row in shared_rows:
            project = projects.get(row.project_id)
            if project is None:
                continue
            project_start = iso_date(project.start_date)
            if project_start is None:
                continue
            outcome_date = month_start(record.certification_month)
            if project_start < outcome_date:
                days = (outcome_date - project_start).days
                pre_entry.append((row, project, days))
                lead_days.append(days)
                matched_project_ids.add(row.project_id)

        if pre_entry:
            pre_entry_outcomes.add(record.record_id)
            first = min(pre_entry, key=lambda item: item[2])
            earliest = max(pre_entry, key=lambda item: item[2])
            outcome_details.append(
                {
                    "certification_month": record.certification_month,
                    "country": record.country_of_ultimate_control,
                    "investor_name": record.investor_name,
                    "investor_node_id": record.investor_node_id,
                    "pre_entry_shared_project_count": len(
                        {row.project_id for row, _, _ in pre_entry}
                    ),
                    "nearest_pre_entry_project": {
                        "project_id": first[0].project_id,
                        "acronym": first[1].acronym,
                        "start_date": first[1].start_date,
                        "lead_days": first[2],
                    },
                    "earliest_pre_entry_project": {
                        "project_id": earliest[0].project_id,
                        "acronym": earliest[1].acronym,
                        "start_date": earliest[1].start_date,
                        "lead_days": earliest[2],
                    },
                }
            )

by_year = collections.Counter(record.certification_month[:4] for record in cohort)
pre_by_year = collections.Counter(
    next(
        record.certification_month[:4]
        for record in cohort
        if record.record_id == record_id
    )
    for record_id in pre_entry_outcomes
)
pre_by_country = collections.Counter(
    next(
        record.country_of_ultimate_control
        for record in cohort
        if record.record_id == record_id
    )
    for record_id in pre_entry_outcomes
)

result = {
    "window": {"start": START, "end": END},
    "cohort_records": len(cohort),
    "cohort_by_year": dict(sorted(by_year.items())),
    "cordis_source_bytes": download.byte_count,
    "cordis_source_sha256": download.sha256,
    "cordis_projects": len(projects),
    "cordis_participations": len(participations),
    "cordis_projects_with_canadian_participant": len(canada_projects),
    "exact_name_country_outcomes": len(matched_outcomes),
    "exact_name_country_shared_canada_project_outcomes": len(shared_canada_outcomes),
    "pre_entry_shared_canada_project_outcomes": len(pre_entry_outcomes),
    "pre_entry_share_of_cohort_percent": round(
        100 * len(pre_entry_outcomes) / len(cohort),
        2,
    ) if cohort else 0,
    "pre_entry_by_year": dict(sorted(pre_by_year.items())),
    "pre_entry_by_country": dict(
        sorted(pre_by_country.items(), key=lambda item: (-item[1], item[0]))
    ),
    "matched_pre_entry_project_ids": len(matched_project_ids),
    "lead_time_days": {
        "count": len(lead_days),
        "median": statistics.median(lead_days) if lead_days else None,
        "p25": (
            statistics.quantiles(lead_days, n=4, method="inclusive")[0]
            if len(lead_days) >= 2
            else None
        ),
        "p75": (
            statistics.quantiles(lead_days, n=4, method="inclusive")[2]
            if len(lead_days) >= 2
            else None
        ),
    },
    "outcomes_with_pre_entry_signal": sorted(
        outcome_details,
        key=lambda row: (
            row["certification_month"],
            row["country"],
            row["investor_name"],
        ),
    ),
}

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
