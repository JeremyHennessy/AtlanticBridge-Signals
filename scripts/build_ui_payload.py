from __future__ import annotations

from collections import Counter
from pathlib import Path
import json

from atlanticbridge.outcome_evidence import evidence_publication_status

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "reviews" / "outcome_audit" / "2026-09-20-cases.json"
IDENTITY_PATH = ROOT / "reviews" / "outcome_audit" / "2026-09-20-identity-dispositions.json"
OUTPUT_PATH = ROOT / "ui" / "data" / "dashboard.json"
CONTROL_IDENTITY_PATH = ROOT / "reviews" / "control_cohorts" / "2026-09-20-control-identity-decisions.json"
EXPANDED_IDENTITY_PATHS = [
    ROOT / "reviews" / "control_cohorts" / "2026-09-22-expanded-control-identity-batch-01.json",
    ROOT / "reviews" / "control_cohorts" / "2026-09-22-expanded-control-identity-batch-02.json",
]
OUTCOME_COHORT_PATH = ROOT / "reviews" / "outcome_audit" / "2026-09-20-outcome-cohorts.json"


def normalize_company_name(value: str | None) -> str:
    return "".join(char.casefold() for char in (value or "") if char.isalnum())


def build_research_cohort(cases: list[dict]) -> tuple[list[dict], int]:
    historical_names = {
        normalize_company_name(name)
        for case in cases
        for name in (case.get("investor_name"), case.get("canadian_business_name"))
        if name
    }
    outcome_cohorts = json.loads(OUTCOME_COHORT_PATH.read_text(encoding="utf-8"))
    candidate_by_id = {
        row["outcome_record_id"]: row for row in outcome_cohorts["cases"]
    }

    control_doc = json.loads(CONTROL_IDENTITY_PATH.read_text(encoding="utf-8"))
    selected: list[tuple[dict, str]] = [
        (row, "ACCEPTED_BACKTEST_CONTROL")
        for row in control_doc["records"]
        if row.get("backtest_control_eligible") is True
    ]
    for path in EXPANDED_IDENTITY_PATHS:
        doc = json.loads(path.read_text(encoding="utf-8"))
        selected.extend(
            (row, "IDENTITY_QUALIFIED_RESEARCH_CONTROL")
            for row in doc["records"]
            if row.get("review_decision")
            == "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY"
        )

    result = []
    excluded_overlap = 0
    seen = set()
    for row, research_status in selected:
        key = row["control_entity_key"]
        if key in seen:
            continue
        seen.add(key)
        names = {
            normalize_company_name(row.get("investor_name")),
            normalize_company_name(row.get("foreign_legal_name")),
        }
        names.discard("")
        if names & historical_names:
            excluded_overlap += 1
            continue

        assigned = row.get("assigned_candidate_outcome_ids") or []
        matched_candidates = []
        for outcome_id in assigned:
            candidate = candidate_by_id.get(outcome_id, {})
            matched_candidates.append(
                {
                    "outcome_id": outcome_id,
                    "canadian_business_name": candidate.get("canadian_business_name"),
                    "investor_name": candidate.get("investor_name"),
                    "notification_month": candidate.get("notification_month"),
                    "cohort": candidate.get("cohort"),
                }
            )

        legal_identifier = row.get("foreign_legal_identifier")
        if isinstance(legal_identifier, dict):
            legal_identifier_display = " · ".join(
                str(value)
                for value in (
                    legal_identifier.get("type"),
                    legal_identifier.get("value"),
                )
                if value
            )
        else:
            legal_identifier_display = str(legal_identifier or "")

        result.append(
            {
                "id": key,
                "display_name": row.get("foreign_legal_name")
                or row.get("investor_name"),
                "investor_name": row.get("investor_name"),
                "investor_locality": row.get("investor_locality"),
                "ultimate_control_country": row.get("ultimate_control_country"),
                "foreign_legal_name": row.get("foreign_legal_name"),
                "foreign_legal_identifier": legal_identifier_display or None,
                "identity_confidence": row.get("identity_confidence"),
                "research_status": research_status,
                "later_new_business_month": row.get("later_new_business_month"),
                "accepted_backtest_control_eligible": bool(
                    row.get("backtest_control_eligible")
                    or row.get("accepted_backtest_control_eligible")
                ),
                "negative_label_eligible": bool(
                    row.get("negative_label_eligible")
                ),
                "matched_candidates": matched_candidates,
                "rationale": row.get("rationale"),
                "identity_evidence": [
                    {
                        "source_url": evidence.get("source_url"),
                        "source_type": evidence.get("source_type"),
                        "claim": evidence.get("claim"),
                    }
                    for evidence in row.get("identity_evidence", [])
                ],
            }
        )

    result.sort(
        key=lambda row: (
            str(row.get("ultimate_control_country") or ""),
            str(row.get("display_name") or ""),
        )
    )
    return result, excluded_overlap


def build_payload() -> dict:
    cases_doc = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    identity_doc = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    cases = cases_doc["cases"]
    research_cohort, research_overlap_excluded = build_research_cohort(cases)

    classification_counts = Counter(case["outcome_classification"] for case in cases)
    source_type_counts = Counter(
        evidence.get("source_type", "UNKNOWN")
        for case in cases
        for evidence in case.get("additional_evidence", [])
    )
    publication_status_counts = Counter()
    cases_with_verified_pre_notification_evidence = 0

    ui_cases = []
    for case in cases:
        evidence = []
        verified_pre_notification_evidence_count = 0
        for item in case.get("additional_evidence", []):
            publication_status = evidence_publication_status(
                item,
                case["notification_month"],
            )
            publication_status_counts[publication_status] += 1
            if publication_status == "VERIFIED_BEFORE_NOTIFICATION_MONTH":
                verified_pre_notification_evidence_count += 1
            evidence.append(
                {
                    "source_url": item.get("source_url"),
                    "source_type": item.get("source_type", "UNKNOWN"),
                    "source_date": item.get("source_date"),
                    "source_date_basis": item.get("source_date_basis"),
                    "event_date": item.get("event_date"),
                    "event_date_precision": item.get("event_date_precision"),
                    "claim": item.get("claim"),
                    "supports": item.get("supports"),
                    "publicly_available_date": item.get("publicly_available_date"),
                    "publicly_available_date_precision": item.get(
                        "publicly_available_date_precision"
                    ),
                    "publicly_available_date_basis": item.get(
                        "publicly_available_date_basis"
                    ),
                    "publicly_available_date_source_url": item.get(
                        "publicly_available_date_source_url"
                    ),
                    "publication_status": publication_status,
                }
            )

        if verified_pre_notification_evidence_count:
            cases_with_verified_pre_notification_evidence += 1

        ui_cases.append(
            {
                "id": case["outcome_record_id"],
                "investor_name": case["investor_name"],
                "canadian_business_name": case["canadian_business_name"],
                "canadian_business_activity": case.get("canadian_business_activity"),
                "ultimate_control_country": case.get("ultimate_control_country"),
                "corporation_number": case.get("corporation_number"),
                "registry_status": case.get("registry_projection", {}).get("status"),
                "notification_month": case.get("notification_month"),
                "incorporation_date": case.get("federal_event_date"),
                "days_before_notification_month": case.get("days_before_notification_month"),
                "outcome_classification": case.get("outcome_classification"),
                "first_canadian_operations_date": case.get("first_canadian_operations_date"),
                "model_eligible": bool(case.get("model_eligible")),
                "audit_note": case.get("audit_note"),
                "evidence_count": len(evidence),
                "verified_pre_notification_evidence_count":
                    verified_pre_notification_evidence_count,
                "evidence": evidence,
            }
        )

    ui_cases.sort(
        key=lambda case: (
            case.get("notification_month") or "",
            case.get("canadian_business_name") or "",
        ),
        reverse=True,
    )

    return {
        "schema_version": 1,
        "generated_from": {
            "cases": str(CASES_PATH.relative_to(ROOT)),
            "identity_dispositions": str(IDENTITY_PATH.relative_to(ROOT)),
        },
        "audit_date": cases_doc.get("audit_date"),
        "summary": {
            "case_count": cases_doc["case_count"],
            "research_cohort_count": len(research_cohort),
            "browsable_company_count": cases_doc["case_count"] + len(research_cohort),
            "research_historical_overlap_excluded": research_overlap_excluded,
            "evidence_case_count": sum(bool(case.get("additional_evidence")) for case in cases),
            "identity_supported": identity_doc.get("supported", 0),
            "identity_requires_review": identity_doc.get("requires_evidence_review", 0),
            "model_eligible_count": cases_doc.get("model_eligible_count", 0),
            "first_operation_dates_established": cases_doc.get(
                "first_operation_dates_established", 0
            ),
            "before_notification_month": cases_doc["notification_relative_counts"].get(
                "before_month", 0
            ),
            "same_notification_month": cases_doc["notification_relative_counts"].get(
                "same_month", 0
            ),
            "median_days_before_notification_month": cases_doc[
                "notification_relative_counts"
            ].get("median_days_before_month"),
            "classification_counts": dict(sorted(classification_counts.items())),
            "source_type_counts": dict(
                source_type_counts.most_common()
            ),
            "publication_status_counts": dict(
                sorted(publication_status_counts.items())
            ),
            "cases_with_verified_pre_notification_evidence":
                cases_with_verified_pre_notification_evidence,
        },
        "cases": ui_cases,
        "research_cohort": research_cohort,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH.relative_to(ROOT)} with {len(payload['cases'])} cases")


if __name__ == "__main__":
    main()
