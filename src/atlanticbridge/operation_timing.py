from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


ALLOWED_TIMING_STATUSES = {
    "OPERATING_BY_DATE",
    "OPERATING_DURING_PERIOD",
    "ESTABLISHMENT_BY_DATE",
    "ESTABLISHMENT_DURING_PERIOD",
    "MARKET_ACTIVITY_BY_DATE",
    "PROJECT_ACTIVITY_BY_DATE",
    "PROJECT_ACTIVITY_DURING_PERIOD",
    "MARKET_SIGNAL_ONLY",
    "NON_OPERATING_HOLDING_VEHICLE",
    "UNRESOLVED",
}

ALLOWED_BOUND_KINDS = {
    "UPPER_BOUND_ON_FIRST_OPERATION",
    "UPPER_BOUND_BY_PERIOD_END",
    "UPPER_BOUND_ON_PREDECESSOR_OPERATION",
    "NO_OPERATION_BOUND",
}


def validate_operation_timing_audit(payload: dict[str, object]) -> None:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("operation timing audit requires a cases list")

    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("operation timing cases must be objects")
        record_id = str(case.get("outcome_record_id") or "")
        if not record_id or record_id in seen:
            raise ValueError("operation timing cases require unique outcome_record_id")
        seen.add(record_id)

        status = str(case.get("timing_status") or "")
        if status not in ALLOWED_TIMING_STATUSES:
            raise ValueError(f"invalid timing_status: {status}")

        bound_kind = str(case.get("operation_bound_kind") or "")
        if bound_kind not in ALLOWED_BOUND_KINDS:
            raise ValueError(f"invalid operation_bound_kind: {bound_kind}")

        exact = bool(case.get("exact_first_operation_proven"))
        first_date = case.get("first_canadian_operations_date")
        if exact != bool(first_date):
            raise ValueError(
                "exact_first_operation_proven must match presence of "
                "first_canadian_operations_date"
            )

        if case.get("model_eligible_from_timing") and not exact:
            raise ValueError(
                "timing model eligibility requires an exact first-operation outcome"
            )

        observation_value = case.get("observation_value")
        observation_precision = case.get("observation_precision")
        if bool(observation_value) != bool(observation_precision):
            raise ValueError(
                "observation_value and observation_precision must be populated together"
            )


def summarize_operation_timing_audit(payload: dict[str, object]) -> dict[str, object]:
    validate_operation_timing_audit(payload)
    cases = payload["cases"]
    status_counts = Counter(str(case["timing_status"]) for case in cases)
    bound_counts = Counter(str(case["operation_bound_kind"]) for case in cases)

    return {
        "case_count": len(cases),
        "exact_first_operation_dates": sum(
            bool(case["exact_first_operation_proven"]) for case in cases
        ),
        "cases_with_operation_upper_bound": sum(
            str(case["operation_bound_kind"]).startswith("UPPER_BOUND")
            for case in cases
        ),
        "model_eligible_from_timing": sum(
            bool(case["model_eligible_from_timing"]) for case in cases
        ),
        "timing_status_counts": dict(sorted(status_counts.items())),
        "operation_bound_counts": dict(sorted(bound_counts.items())),
    }


def load_and_summarize(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text())
    return summarize_operation_timing_audit(payload)
