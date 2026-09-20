from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date
from pathlib import Path
import json


PUBLICATION_STATUSES = {
    "VERIFIED_BEFORE_NOTIFICATION_MONTH",
    "VERIFIED_DURING_NOTIFICATION_MONTH",
    "VERIFIED_AFTER_NOTIFICATION_MONTH",
    "OVERLAPS_NOTIFICATION_MONTH",
    "UNVERIFIED",
}


def _month_interval(value: str) -> tuple[date, date]:
    year_text, month_text = value.split("-")
    year = int(year_text)
    month = int(month_text)
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _dated_interval(value: str, precision: str) -> tuple[date, date]:
    precision = precision.upper()
    if precision == "DAY":
        parsed = date.fromisoformat(value)
        return parsed, parsed
    if precision == "MONTH":
        return _month_interval(value)
    if precision == "YEAR":
        year = int(value)
        return date(year, 1, 1), date(year, 12, 31)
    raise ValueError(
        "publicly_available_date_precision must be DAY, MONTH or YEAR"
    )


def evidence_publication_status(
    evidence: dict[str, object],
    notification_month: str,
) -> str:
    """Compare explicit public-availability evidence against notification month.

    This function deliberately ignores source_date, event_date and observed_at.
    They do not prove when a source was publicly available.
    """
    available = str(evidence.get("publicly_available_date") or "").strip()
    precision = str(
        evidence.get("publicly_available_date_precision") or ""
    ).strip().upper()
    if not available or not precision:
        return "UNVERIFIED"

    evidence_start, evidence_end = _dated_interval(available, precision)
    notification_start, notification_end = _month_interval(notification_month)

    if evidence_end < notification_start:
        return "VERIFIED_BEFORE_NOTIFICATION_MONTH"
    if evidence_start > notification_end:
        return "VERIFIED_AFTER_NOTIFICATION_MONTH"
    if (
        evidence_start >= notification_start
        and evidence_end <= notification_end
    ):
        return "VERIFIED_DURING_NOTIFICATION_MONTH"
    return "OVERLAPS_NOTIFICATION_MONTH"


def summarize_outcome_publication_gate(
    payload: dict[str, object],
) -> dict[str, object]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Outcome audit payload must contain a cases list")

    status_counts: Counter[str] = Counter()
    case_rows: list[dict[str, object]] = []
    model_eligibility_violations: list[dict[str, str]] = []
    total_evidence = 0

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Each outcome audit case must be an object")
        notification_month = str(case.get("notification_month") or "")
        if not notification_month:
            raise ValueError("Each outcome audit case requires notification_month")

        evidence_rows = case.get("additional_evidence") or []
        if not isinstance(evidence_rows, list):
            raise ValueError("additional_evidence must be a list")

        statuses = [
            evidence_publication_status(evidence, notification_month)
            for evidence in evidence_rows
        ]
        total_evidence += len(statuses)
        status_counts.update(statuses)
        verified_before = statuses.count(
            "VERIFIED_BEFORE_NOTIFICATION_MONTH"
        )

        row = {
            "outcome_record_id": str(case.get("outcome_record_id") or ""),
            "investor_name": str(case.get("investor_name") or ""),
            "canadian_business_name": str(
                case.get("canadian_business_name") or ""
            ),
            "notification_month": notification_month,
            "model_eligible": bool(case.get("model_eligible")),
            "evidence_records": len(statuses),
            "verified_pre_notification_evidence": verified_before,
            "publication_status_counts": dict(
                sorted(Counter(statuses).items())
            ),
        }
        case_rows.append(row)

        if row["model_eligible"] and verified_before == 0:
            model_eligibility_violations.append(
                {
                    "outcome_record_id": row["outcome_record_id"],
                    "canadian_business_name": row["canadian_business_name"],
                    "reason": (
                        "model_eligible case has no evidence with explicit "
                        "public availability before the notification month"
                    ),
                }
            )

    return {
        "schema_version": 1,
        "case_count": len(cases),
        "evidence_record_count": total_evidence,
        "publication_status_counts": dict(sorted(status_counts.items())),
        "cases_with_verified_pre_notification_evidence": sum(
            row["verified_pre_notification_evidence"] > 0
            for row in case_rows
        ),
        "model_eligible_cases": sum(row["model_eligible"] for row in case_rows),
        "model_eligibility_violations": model_eligibility_violations,
        "cases": case_rows,
    }


def load_and_summarize(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text())
    return summarize_outcome_publication_gate(payload)


def enforce_model_eligibility_publication_gate(
    summary: dict[str, object],
) -> None:
    violations = summary.get("model_eligibility_violations") or []
    if violations:
        names = ", ".join(
            str(item.get("canadian_business_name") or item.get("outcome_record_id"))
            for item in violations
        )
        raise ValueError(
            "Publication-cutoff gate failed for model-eligible cases: "
            + names
        )
