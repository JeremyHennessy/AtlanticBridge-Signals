from __future__ import annotations

from collections import Counter
import json
from pathlib import Path


COHORTS = {
    "EXISTING_PRESENCE",
    "TRUE_NEW_ENTRY_CANDIDATE",
    "ESTABLISHMENT_ONLY",
    "NON_OPERATING_VEHICLE",
    "UNRESOLVED",
}


def validate_outcome_cohorts(payload: dict[str, object]) -> None:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("outcome cohort audit requires a cases list")

    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("outcome cohort cases must be objects")
        record_id = str(case.get("outcome_record_id") or "")
        if not record_id or record_id in seen:
            raise ValueError("outcome cohort rows require unique outcome_record_id")
        seen.add(record_id)

        cohort = str(case.get("cohort") or "")
        if cohort not in COHORTS:
            raise ValueError(f"invalid outcome cohort: {cohort}")

        if case.get("training_positive_eligible"):
            raise ValueError(
                "current audited cohorts cannot promote training-positive labels"
            )

        matching = bool(case.get("censored_candidate_for_matching"))
        if matching != (cohort == "TRUE_NEW_ENTRY_CANDIDATE"):
            raise ValueError(
                "only TRUE_NEW_ENTRY_CANDIDATE rows may be censored candidates for matching"
            )

        if not str(case.get("rationale") or "").strip():
            raise ValueError("every cohort row requires an explicit rationale")


def summarize_outcome_cohorts(payload: dict[str, object]) -> dict[str, object]:
    validate_outcome_cohorts(payload)
    cases = payload["cases"]
    counts = Counter(str(case["cohort"]) for case in cases)
    return {
        "case_count": len(cases),
        "cohort_counts": dict(sorted(counts.items())),
        "censored_candidates_for_matching": sum(
            bool(case["censored_candidate_for_matching"]) for case in cases
        ),
        "training_positive_eligible": sum(
            bool(case["training_positive_eligible"]) for case in cases
        ),
    }


def load_and_summarize(path: str | Path) -> dict[str, object]:
    payload = json.loads(Path(path).read_text())
    return summarize_outcome_cohorts(payload)
