from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re


_ALLOWED_DECISIONS = {"QUALIFIED", "REJECTED", "UNRESOLVED"}
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def add_months(value: str, months: int) -> str:
    match = _MONTH_RE.fullmatch(value)
    if not match:
        raise ValueError(f"invalid month: {value}")
    year = int(match.group(1))
    month = int(match.group(2))
    total = year * 12 + (month - 1) + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def validate_control_identity_review(
    queue: dict[str, object],
    review: dict[str, object],
) -> dict[str, int]:
    queue_rows = queue.get("records")
    review_rows = review.get("records")
    if not isinstance(queue_rows, list) or not isinstance(review_rows, list):
        raise ValueError("queue and review must contain records lists")

    queue_by_key = {
        str(row["control_entity_key"]): row
        for row in queue_rows
    }
    review_by_key = {
        str(row["control_entity_key"]): row
        for row in review_rows
    }
    if set(queue_by_key) != set(review_by_key):
        missing = sorted(set(queue_by_key) - set(review_by_key))
        extra = sorted(set(review_by_key) - set(queue_by_key))
        raise ValueError(f"identity review key mismatch missing={missing} extra={extra}")

    decisions: Counter[str] = Counter()
    eligible = 0
    for key, source in queue_by_key.items():
        row = review_by_key[key]
        for field in (
            "investor_node_id",
            "investor_name",
            "ultimate_control_country",
            "assigned_candidate_outcome_ids",
        ):
            if row.get(field) != source.get(field):
                raise ValueError(f"identity review changed queue field {field} for {key}")

        decision = str(row.get("identity_qualification_status") or "")
        if decision not in _ALLOWED_DECISIONS:
            raise ValueError(f"invalid identity decision for {key}: {decision}")
        decisions[decision] += 1

        is_eligible = bool(row.get("backtest_control_eligible"))
        if is_eligible != (decision == "QUALIFIED"):
            raise ValueError(
                f"backtest eligibility must equal QUALIFIED identity status for {key}"
            )
        if bool(row.get("negative_label_eligible")):
            raise ValueError(f"negative labels are prohibited for risk-set control {key}")

        evidence = row.get("identity_evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"identity review requires explicit evidence for {key}")

        if decision == "QUALIFIED":
            eligible += 1
            if not str(row.get("foreign_legal_name") or "").strip():
                raise ValueError(f"qualified row lacks foreign legal name: {key}")
            future_month = str(row.get("later_new_business_month") or "")
            if not _MONTH_RE.fullmatch(future_month):
                raise ValueError(f"qualified row lacks later new-business month: {key}")

    summary = review.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("identity review requires summary")
    expected = {
        "record_count": len(review_rows),
        "qualified": decisions["QUALIFIED"],
        "rejected": decisions["REJECTED"],
        "unresolved": decisions["UNRESOLVED"],
        "backtest_control_eligible": eligible,
        "negative_labels_created": 0,
    }
    for field, value in expected.items():
        if summary.get(field) != value:
            raise ValueError(
                f"identity review summary mismatch {field}: "
                f"{summary.get(field)} != {value}"
            )
    return expected


def build_backtest_control_set(
    *,
    queue: dict[str, object],
    review: dict[str, object],
    cohorts: dict[str, object],
    risk_manifest: dict[str, object],
) -> dict[str, object]:
    validate_control_identity_review(queue, review)

    manifest_summary = risk_manifest.get("summary")
    if not isinstance(manifest_summary, dict):
        raise ValueError("risk manifest requires summary")
    if manifest_summary.get("candidate_count") != manifest_summary.get(
        "candidates_with_complete_followup"
    ):
        raise ValueError("risk-set candidate follow-up is incomplete")

    cohort_rows = cohorts.get("cases")
    if not isinstance(cohort_rows, list):
        raise ValueError("cohort payload requires cases")
    cohort_by_id = {
        str(row["outcome_record_id"]): row
        for row in cohort_rows
    }

    rows: list[dict[str, object]] = []
    for identity in review["records"]:
        if identity["identity_qualification_status"] != "QUALIFIED":
            continue
        future_month = str(identity["later_new_business_month"])
        assignments = identity["assigned_candidate_outcome_ids"]
        assert isinstance(assignments, list)

        for candidate_id in assignments:
            candidate = cohort_by_id.get(str(candidate_id))
            if candidate is None:
                raise ValueError(f"missing candidate cohort row: {candidate_id}")
            if candidate.get("cohort") != "TRUE_NEW_ENTRY_CANDIDATE":
                raise ValueError(
                    f"control assigned outside TRUE_NEW_ENTRY_CANDIDATE: {candidate_id}"
                )
            notification_month = str(candidate["notification_month"])
            horizon_end = add_months(notification_month, 24)
            if future_month <= horizon_end:
                raise ValueError(
                    f"qualified control {identity['control_entity_key']} enters "
                    f"inside risk horizon {horizon_end}"
                )
            rows.append(
                {
                    "candidate_outcome_id": candidate_id,
                    "candidate_notification_month": notification_month,
                    "risk_horizon_months": 24,
                    "risk_horizon_end_month": horizon_end,
                    "control_entity_key": identity["control_entity_key"],
                    "investor_node_id": identity["investor_node_id"],
                    "investor_name": identity["investor_name"],
                    "ultimate_control_country": identity["ultimate_control_country"],
                    "foreign_legal_name": identity["foreign_legal_name"],
                    "identity_qualification_status": "QUALIFIED",
                    "identity_confidence": identity["identity_confidence"],
                    "later_new_business_month": future_month,
                    "observation_coverage_status":
                        "COMPLETE_INVESTMENT_CANADA_RISK_HORIZON",
                    "control_interpretation": "TIME_INDEXED_AT_RISK_FUTURE_ENTRANT",
                    "backtest_control_eligible": True,
                    "negative_label_eligible": False,
                }
            )

    rows.sort(
        key=lambda row: (
            str(row["candidate_notification_month"]),
            str(row["candidate_outcome_id"]),
            str(row["investor_name"]).casefold(),
        )
    )
    candidate_ids = sorted({str(row["candidate_outcome_id"]) for row in rows})
    all_candidate_ids = sorted(
        str(row["outcome_record_id"])
        for row in cohort_rows
        if row.get("cohort") == "TRUE_NEW_ENTRY_CANDIDATE"
    )
    unmatched = sorted(set(all_candidate_ids) - set(candidate_ids))

    return {
        "schema_version": 1,
        "design": "IDENTITY_QUALIFIED_TIME_INDEXED_RISK_SET_CONTROLS",
        "source_control_design":
            "FUTURE_ENTRANT_RISK_SET_CONTROL_CANDIDATES",
        "horizon_months": 24,
        "negative_label_rule":
            "No row is a permanent negative label. Controls are future entrants "
            "observed at risk only through the matched candidate horizon.",
        "source_availability_rule":
            "Backtest eligibility here establishes identity and Investment Canada "
            "risk-horizon coverage only. Each signal source must independently "
            "establish historical availability at each event-time cutoff.",
        "summary": {
            "eligible_control_assignments": len(rows),
            "distinct_eligible_controls": len(
                {str(row["control_entity_key"]) for row in rows}
            ),
            "candidate_strata_with_eligible_controls": len(candidate_ids),
            "candidate_strata_without_eligible_controls": len(unmatched),
            "negative_labels_created": 0,
        },
        "candidate_strata_without_eligible_controls": unmatched,
        "controls": rows,
    }


def load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
