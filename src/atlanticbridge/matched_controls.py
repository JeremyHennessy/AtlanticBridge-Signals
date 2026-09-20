from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re
import sqlite3
from pathlib import Path


COUNTRY_TO_ISO2 = {
    "Italy": "IT",
    "Czechia": "CZ",
    "Ireland": "IE",
    "Germany": "DE",
    "Poland": "PL",
    "Sweden": "SE",
    "Denmark": "DK",
}

SECTOR_KEYWORDS = {
    "Antea Canada Inc.": (
        "software", "digital", "data", "platform", "asset", "maintenance",
        "industrial", "engineering",
    ),
    "Linet Canada Inc.": (
        "medical", "health", "hospital", "patient", "care", "clinical",
        "device", "bed",
    ),
    "DIGITARY CANADA INC.": (
        "education", "university", "credential", "digital", "student",
        "learning", "academic", "platform",
    ),
    "HANECS Canada Inc.": (
        "software", "digital", "data", "consulting", "training",
        "technology", "information",
    ),
    "Aiut Inc.": (
        "industrial", "engineering", "automation", "manufacturing",
        "robot", "process", "energy",
    ),
    "Sioo Wood Protection Industry Canada Inc.": (
        "wood", "timber", "construction", "building", "material",
        "coating", "bio-based", "sustainable",
    ),
    "Leadership Pipeline Institute Canada Inc.": (
        "education", "training", "leadership", "management", "consulting",
        "skills", "learning", "coaching",
    ),
}

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def normalize_name(value: str | None) -> str:
    text = " ".join(_TOKEN.findall((value or "").lower()))
    suffixes = {
        "inc", "incorporated", "ltd", "limited", "llc", "plc", "gmbh", "ag",
        "ab", "as", "oy", "spa", "srl", "bv", "nv", "sa", "sas", "scsp",
    }
    tokens = [token for token in text.split() if token not in suffixes]
    return " ".join(tokens)


def _month_start(value: str) -> date:
    year, month = (int(part) for part in value.split("-"))
    return date(year, month, 1)


def _safe_date(value: str | None) -> date | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        if len(text) >= 10:
            return date.fromisoformat(text[:10])
        if len(text) == 7:
            return _month_start(text)
        if len(text) == 4:
            return date(int(text), 1, 1)
    except ValueError:
        return None
    return None


def _ica_name_index(conn: sqlite3.Connection) -> set[str]:
    names: set[str] = set()
    for row in conn.execute(
        """
        SELECT investor_name, investor_text, canadian_business_text
        FROM investment_canada_notifications
        """
    ):
        for value in row:
            normalized = normalize_name(value)
            if normalized:
                names.add(normalized)
    return names


def _positive_name_index(cases_payload: dict, cohort_payload: dict) -> set[str]:
    candidate_ids = {
        row["outcome_record_id"]
        for row in cohort_payload["cases"]
        if row["cohort"] == "TRUE_NEW_ENTRY_CANDIDATE"
    }
    names: set[str] = set()
    for case in cases_payload["cases"]:
        if case["outcome_record_id"] not in candidate_ids:
            continue
        for value in (
            case.get("investor_name"),
            case.get("canadian_business_name"),
        ):
            normalized = normalize_name(value)
            if normalized:
                names.add(normalized)
    return names


@dataclass(frozen=True)
class CandidateControl:
    organisation_id: str
    name: str
    country: str
    city: str
    organization_url: str
    sme: str
    project_count: int
    matched_keywords: tuple[str, ...]
    sector_score: int
    closest_project_year_gap: int
    has_canada_shared_project_before_index: bool
    canada_shared_project_count_before_index: int


def _candidate_controls(
    conn: sqlite3.Connection,
    *,
    country_iso2: str,
    index_month: str,
    keywords: tuple[str, ...],
    excluded_names: set[str],
) -> list[CandidateControl]:
    index_date = _month_start(index_month)
    rows = conn.execute(
        """
        SELECT
            p.organisation_id,
            p.name,
            p.country,
            p.city,
            p.organization_url,
            p.sme,
            p.project_id,
            pr.title,
            pr.objective,
            pr.topics,
            pr.keywords,
            pr.start_date,
            pr.end_date
        FROM cordis_participations p
        JOIN cordis_projects pr ON pr.project_id = p.project_id
        WHERE p.country = ?
          AND p.activity_type = 'PRC'
          AND NULLIF(TRIM(p.name), '') IS NOT NULL
        """,
        (country_iso2,),
    ).fetchall()

    grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        normalized = normalize_name(row["name"])
        if not normalized or normalized in excluded_names:
            continue
        grouped[(row["organisation_id"], row["name"])].append(row)

    result: list[CandidateControl] = []
    keyword_set = tuple(sorted({keyword.lower() for keyword in keywords}))

    for (organisation_id, name), org_rows in grouped.items():
        matched: set[str] = set()
        year_gaps: list[int] = []
        canada_projects_before: set[str] = set()

        for row in org_rows:
            corpus = " ".join(
                str(row[field] or "")
                for field in ("title", "objective", "topics", "keywords")
            ).lower()
            matched.update(keyword for keyword in keyword_set if keyword in corpus)

            start = _safe_date(row["start_date"])
            if start:
                year_gaps.append(abs(start.year - index_date.year))

            # This is a feature measurement, not a selection condition.
            if start and start <= index_date:
                has_canada = conn.execute(
                    """
                    SELECT 1
                    FROM cordis_participations
                    WHERE project_id = ?
                      AND country = 'CA'
                    LIMIT 1
                    """,
                    (row["project_id"],),
                ).fetchone()
                if has_canada:
                    canada_projects_before.add(row["project_id"])

        if not matched:
            continue

        first = org_rows[0]
        result.append(
            CandidateControl(
                organisation_id=organisation_id,
                name=name,
                country=first["country"],
                city=first["city"],
                organization_url=first["organization_url"],
                sme=first["sme"],
                project_count=len({row["project_id"] for row in org_rows}),
                matched_keywords=tuple(sorted(matched)),
                sector_score=len(matched),
                closest_project_year_gap=min(year_gaps) if year_gaps else 99,
                has_canada_shared_project_before_index=bool(canada_projects_before),
                canada_shared_project_count_before_index=len(canada_projects_before),
            )
        )

    result.sort(
        key=lambda item: (
            -item.sector_score,
            item.closest_project_year_gap,
            -item.project_count,
            item.name.casefold(),
            item.organisation_id,
        )
    )
    return result


def build_matched_controls(
    conn: sqlite3.Connection,
    *,
    cases_payload: dict,
    cohort_payload: dict,
    controls_per_case: int = 3,
) -> dict:
    if controls_per_case < 1:
        raise ValueError("controls_per_case must be positive")

    cases_by_id = {
        case["outcome_record_id"]: case for case in cases_payload["cases"]
    }
    candidate_rows = [
        row
        for row in cohort_payload["cases"]
        if row["cohort"] == "TRUE_NEW_ENTRY_CANDIDATE"
    ]

    ica_names = _ica_name_index(conn)
    excluded_names = set(ica_names)
    excluded_names.update(_positive_name_index(cases_payload, cohort_payload))

    matches: list[dict] = []
    used_controls: set[str] = set()

    for candidate in candidate_rows:
        case = cases_by_id[candidate["outcome_record_id"]]
        business_name = case["canadian_business_name"]
        country = case["ultimate_control_country"]
        iso2 = COUNTRY_TO_ISO2.get(country)
        keywords = SECTOR_KEYWORDS.get(business_name)
        if not iso2 or not keywords:
            raise ValueError(f"missing control matching specification for {business_name}")

        ranked = _candidate_controls(
            conn,
            country_iso2=iso2,
            index_month=case["notification_month"],
            keywords=keywords,
            excluded_names=excluded_names,
        )

        selected = []
        for control in ranked:
            stable = f"{control.country}:{control.organisation_id}:{normalize_name(control.name)}"
            if stable in used_controls:
                continue
            normalized = normalize_name(control.name)
            if normalized in ica_names:
                continue
            selected.append(control)
            used_controls.add(stable)
            if len(selected) == controls_per_case:
                break

        if len(selected) != controls_per_case:
            raise ValueError(
                f"{business_name}: required {controls_per_case} controls, "
                f"found {len(selected)} after exclusions"
            )

        for rank, control in enumerate(selected, start=1):
            material = "|".join(
                [candidate["outcome_record_id"], control.organisation_id, control.name]
            )
            control_id = hashlib.sha256(material.encode("utf-8")).hexdigest()
            matches.append(
                {
                    "control_id": control_id,
                    "positive_outcome_record_id": candidate["outcome_record_id"],
                    "positive_business_name": business_name,
                    "pseudo_index_month": case["notification_month"],
                    "control_label": "NO_OBSERVED_ENTRY_CONTROL",
                    "control_name": control.name,
                    "cordis_organisation_id": control.organisation_id,
                    "country": country,
                    "country_iso2": control.country,
                    "city": control.city,
                    "organization_url": control.organization_url,
                    "sme": control.sme,
                    "match_rank": rank,
                    "match_method": "SAME_COUNTRY_CORDIS_PRIVATE_SECTOR_KEYWORD",
                    "sector_keywords": list(keywords),
                    "matched_keywords": list(control.matched_keywords),
                    "sector_score": control.sector_score,
                    "cordis_project_count": control.project_count,
                    "closest_project_year_gap": control.closest_project_year_gap,
                    "investment_canada_normalized_exact_match": False,
                    "cordis_canada_shared_project_before_index":
                        control.has_canada_shared_project_before_index,
                    "cordis_canada_shared_project_count_before_index":
                        control.canada_shared_project_count_before_index,
                }
            )

    return {
        "schema_version": 1,
        "control_definition": (
            "NO_OBSERVED_ENTRY_CONTROL means no normalized exact-name match in the "
            "complete Investment Canada historical snapshot used for this build. "
            "It is not proof that the company had no Canadian activity."
        ),
        "matching_method": {
            "positive_cohort": "TRUE_NEW_ENTRY_CANDIDATE",
            "controls_per_positive": controls_per_case,
            "country": "exact ultimate-control country / CORDIS ISO2",
            "entity_type": "CORDIS activityType=PRC",
            "sector": "deterministic keyword overlap in CORDIS project metadata",
            "tie_breakers": [
                "sector keyword count descending",
                "closest project start year to pseudo-index ascending",
                "CORDIS project count descending",
                "company name",
            ],
            "outcome_exclusion": (
                "normalized exact-name exclusion against Investment Canada investor "
                "and Canadian-business text across the loaded history"
            ),
        },
        "summary": {
            "positive_candidates": len(candidate_rows),
            "controls": len(matches),
            "controls_per_positive": controls_per_case,
            "unique_controls": len({row["control_id"] for row in matches}),
            "controls_with_cordis_canada_signal_before_index": sum(
                row["cordis_canada_shared_project_before_index"] for row in matches
            ),
        },
        "matches": matches,
    }


def load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())
