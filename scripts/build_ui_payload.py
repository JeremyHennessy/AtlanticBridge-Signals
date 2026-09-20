from __future__ import annotations

from collections import Counter
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "reviews" / "outcome_audit" / "2026-09-20-cases.json"
IDENTITY_PATH = ROOT / "reviews" / "outcome_audit" / "2026-09-20-identity-dispositions.json"
OUTPUT_PATH = ROOT / "ui" / "data" / "dashboard.json"


def build_payload() -> dict:
    cases_doc = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    identity_doc = json.loads(IDENTITY_PATH.read_text(encoding="utf-8"))
    cases = cases_doc["cases"]

    classification_counts = Counter(case["outcome_classification"] for case in cases)
    source_type_counts = Counter(
        evidence.get("source_type", "UNKNOWN")
        for case in cases
        for evidence in case.get("additional_evidence", [])
    )

    ui_cases = []
    for case in cases:
        evidence = []
        for item in case.get("additional_evidence", []):
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
                }
            )

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
        },
        "cases": ui_cases,
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
