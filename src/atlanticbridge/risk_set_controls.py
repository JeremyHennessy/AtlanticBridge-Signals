from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import json
import re
from typing import Iterable

from .sources.gleif import normalize_entity_name
from .sources.investment_canada import InvestmentCanadaRecord


_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_ACTIVITY_STOPWORDS = {
    "a", "an", "and", "as", "at", "business", "businesses", "by", "canada",
    "canadian", "company", "corporation", "develop", "develops", "engaged",
    "for", "from", "in", "inc", "including", "into", "is", "its", "ltd", "of",
    "operates", "provides", "provision", "related", "services", "the", "to",
    "with",
}


@dataclass(frozen=True, slots=True)
class InvestorHistory:
    entity_key: str
    investor_node_id: str
    normalized_name: str
    investor_name: str
    country: str
    earliest_any_month: str
    first_new_business_month: str
    first_new_business_record_id: str
    first_new_business_activity: str


@dataclass(frozen=True, slots=True)
class RiskSetControl:
    control_entity_key: str
    investor_node_id: str
    investor_name: str
    country: str
    earliest_investment_canada_month: str
    future_new_business_month: str
    future_new_business_record_id: str
    future_entry_lag_months: int
    future_business_activity: str
    activity_similarity: float
    match_tier: str
    interpretation: str = (
        "NO_INVESTMENT_CANADA_RECORD_THROUGH_HORIZON_"
        "WITH_LATER_NEW_BUSINESS_OBSERVED"
    )
    negative_label_eligible: bool = False


def _month_index(value: str) -> int:
    match = _MONTH_RE.fullmatch(value or "")
    if match is None:
        raise ValueError(f"Expected YYYY-MM month, received {value!r}")
    year = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month: {value!r}")
    return year * 12 + (month - 1)


def add_months(value: str, months: int) -> str:
    if months < 0:
        raise ValueError("months must be non-negative")
    index = _month_index(value) + months
    year, month_zero = divmod(index, 12)
    return f"{year:04d}-{month_zero + 1:02d}"


def months_between(earlier: str, later: str) -> int:
    result = _month_index(later) - _month_index(earlier)
    if result < 0:
        raise ValueError(f"later month {later!r} precedes earlier month {earlier!r}")
    return result


def _entity_key(record: InvestmentCanadaRecord) -> str:
    if record.investor_node_id:
        return f"node:{record.investor_node_id}"
    normalized = normalize_entity_name(record.investor_name)
    return f"name:{normalized}|country:{record.country_of_ultimate_control.casefold()}"


def _business_activity(record: InvestmentCanadaRecord) -> str:
    try:
        businesses = json.loads(record.canadian_businesses_json or "[]")
    except json.JSONDecodeError:
        businesses = []
    activities = []
    if isinstance(businesses, list):
        for business in businesses:
            if not isinstance(business, dict):
                continue
            value = " ".join(str(business.get("activity") or "").split()).strip()
            if value and value not in activities:
                activities.append(value)
    if activities:
        return " | ".join(activities)
    return " ".join((record.canadian_business_text or "").split()).strip()


def activity_tokens(value: str) -> set[str]:
    tokens = set()
    for raw in _TOKEN_RE.findall((value or "").casefold()):
        if len(raw) < 3 or raw in _ACTIVITY_STOPWORDS:
            continue
        token = raw[:-1] if len(raw) > 4 and raw.endswith("s") else raw
        if token and token not in _ACTIVITY_STOPWORDS:
            tokens.add(token)
    return tokens


def activity_similarity(left: str, right: str) -> float:
    a = activity_tokens(left)
    b = activity_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def investor_histories(
    records: Iterable[InvestmentCanadaRecord],
) -> dict[str, InvestorHistory]:
    grouped: dict[str, list[InvestmentCanadaRecord]] = defaultdict(list)
    for record in records:
        if not record.is_eu27:
            continue
        grouped[_entity_key(record)].append(record)

    histories: dict[str, InvestorHistory] = {}
    for key, rows in grouped.items():
        ordered = sorted(rows, key=lambda r: (r.certification_month, r.record_id))
        new_business = [row for row in ordered if row.is_new_business]
        if not new_business:
            continue
        first_new = new_business[0]
        representative = first_new
        histories[key] = InvestorHistory(
            entity_key=key,
            investor_node_id=representative.investor_node_id,
            normalized_name=normalize_entity_name(representative.investor_name),
            investor_name=representative.investor_name,
            country=representative.country_of_ultimate_control,
            earliest_any_month=ordered[0].certification_month,
            first_new_business_month=first_new.certification_month,
            first_new_business_record_id=first_new.record_id,
            first_new_business_activity=_business_activity(first_new),
        )
    return histories


def _cohort_candidates(
    cohort_payload: dict[str, object],
    audit_payload: dict[str, object],
) -> list[dict[str, object]]:
    cohort_rows = cohort_payload.get("cases")
    audit_rows = audit_payload.get("cases")
    if not isinstance(cohort_rows, list) or not isinstance(audit_rows, list):
        raise ValueError("cohort and audit payloads require cases lists")

    audit_by_id = {
        str(row.get("outcome_record_id") or ""): row
        for row in audit_rows
        if isinstance(row, dict)
    }

    result = []
    for row in cohort_rows:
        if not isinstance(row, dict):
            raise ValueError("cohort case rows must be objects")
        if row.get("cohort") != "TRUE_NEW_ENTRY_CANDIDATE":
            continue
        if row.get("training_positive_eligible"):
            raise ValueError("risk-set matching cannot consume training-positive rows")
        record_id = str(row.get("outcome_record_id") or "")
        audit = audit_by_id.get(record_id)
        if audit is None:
            raise ValueError(f"candidate missing from canonical audit: {record_id}")
        result.append(
            {
                "outcome_record_id": record_id,
                "investor_name": str(row.get("investor_name") or ""),
                "canadian_business_name": str(row.get("canadian_business_name") or ""),
                "notification_month": str(row.get("notification_month") or ""),
                "country": str(audit.get("ultimate_control_country") or ""),
                "business_activity": str(audit.get("canadian_business_activity") or ""),
            }
        )

    return sorted(result, key=lambda item: (item["notification_month"], item["outcome_record_id"]))


def _candidate_history(
    candidate: dict[str, object],
    records_by_id: dict[str, InvestmentCanadaRecord],
    histories: dict[str, InvestorHistory],
) -> InvestorHistory:
    record_id = str(candidate["outcome_record_id"])
    record = records_by_id.get(record_id)
    if record is None:
        raise ValueError(f"candidate outcome is absent from Investment Canada corpus: {record_id}")
    if record.certification_month != candidate["notification_month"]:
        raise ValueError(f"candidate notification month mismatch: {record_id}")
    if record.country_of_ultimate_control != candidate["country"]:
        raise ValueError(f"candidate control-country mismatch: {record_id}")

    history = histories.get(_entity_key(record))
    if history is None:
        raise ValueError(f"candidate investor history is unavailable: {record_id}")
    return history


def _rank_controls(
    *,
    candidate: dict[str, object],
    candidate_history: InvestorHistory,
    histories: dict[str, InvestorHistory],
    horizon_end_month: str,
    max_controls: int,
) -> list[RiskSetControl]:
    strong: list[RiskSetControl] = []
    fallback: list[RiskSetControl] = []

    candidate_name = normalize_entity_name(str(candidate["investor_name"]))
    candidate_activity = str(candidate["business_activity"])

    for history in histories.values():
        if history.entity_key == candidate_history.entity_key:
            continue
        if history.country != candidate["country"]:
            continue
        if history.normalized_name and history.normalized_name == candidate_name:
            continue

        # A control must have no Investment Canada record of any type through
        # the complete 24-month risk window, then a later observed new-business
        # notification in the same source corpus.
        if _month_index(history.earliest_any_month) <= _month_index(horizon_end_month):
            continue
        if _month_index(history.first_new_business_month) <= _month_index(horizon_end_month):
            continue

        similarity = activity_similarity(candidate_activity, history.first_new_business_activity)
        control = RiskSetControl(
            control_entity_key=history.entity_key,
            investor_node_id=history.investor_node_id,
            investor_name=history.investor_name,
            country=history.country,
            earliest_investment_canada_month=history.earliest_any_month,
            future_new_business_month=history.first_new_business_month,
            future_new_business_record_id=history.first_new_business_record_id,
            future_entry_lag_months=months_between(
                str(candidate["notification_month"]),
                history.first_new_business_month,
            ),
            future_business_activity=history.first_new_business_activity,
            activity_similarity=round(similarity, 6),
            match_tier="COUNTRY_ACTIVITY" if similarity > 0 else "COUNTRY_ONLY_FALLBACK",
        )
        (strong if similarity > 0 else fallback).append(control)

    def sort_key(item: RiskSetControl):
        return (
            -item.activity_similarity,
            item.future_entry_lag_months,
            item.investor_name.casefold(),
            item.control_entity_key,
        )

    strong.sort(key=sort_key)
    fallback.sort(key=sort_key)
    return (strong + fallback)[:max_controls]


def build_risk_set_controls(
    records: Iterable[InvestmentCanadaRecord],
    cohort_payload: dict[str, object],
    audit_payload: dict[str, object],
    *,
    horizon_months: int = 24,
    max_controls: int = 5,
) -> dict[str, object]:
    if horizon_months < 1:
        raise ValueError("horizon_months must be at least 1")
    if max_controls < 1:
        raise ValueError("max_controls must be at least 1")

    records = list(records)
    eu_new = [record for record in records if record.is_eu27 and record.is_new_business]
    if not eu_new:
        raise ValueError("complete Investment Canada corpus contains no EU new-business records")

    corpus_end_month = max(record.certification_month for record in records)
    records_by_id = {record.record_id: record for record in records}
    histories = investor_histories(records)
    candidates = _cohort_candidates(cohort_payload, audit_payload)

    rows = []
    for candidate in candidates:
        candidate_history = _candidate_history(candidate, records_by_id, histories)
        horizon_end_month = add_months(str(candidate["notification_month"]), horizon_months)
        followup_complete = _month_index(corpus_end_month) >= _month_index(horizon_end_month)
        controls = (
            _rank_controls(
                candidate=candidate,
                candidate_history=candidate_history,
                histories=histories,
                horizon_end_month=horizon_end_month,
                max_controls=max_controls,
            )
            if followup_complete
            else []
        )

        rows.append(
            {
                **candidate,
                "horizon_months": horizon_months,
                "horizon_end_month": horizon_end_month,
                "corpus_end_month": corpus_end_month,
                "followup_complete": followup_complete,
                "control_semantics": (
                    "RISK_SET_FUTURE_ENTRANT_NO_ICA_RECORD_THROUGH_HORIZON"
                ),
                "negative_label_eligible": False,
                "controls": [asdict(control) for control in controls],
            }
        )

    payload = {
        "schema_version": 1,
        "design": "FUTURE_ENTRANT_RISK_SET_CONTROLS",
        "horizon_months": horizon_months,
        "max_controls_per_candidate": max_controls,
        "corpus_end_month": corpus_end_month,
        "interpretation": (
            "Controls are later EU new-business entrants with no Investment Canada "
            "record of any type through the candidate's risk horizon. They are "
            "censored risk-set controls, not verified non-entry negatives."
        ),
        "matching_note": (
            "Ultimate-control country is matched exactly. Future Canadian-business "
            "activity text is used retrospectively only to rank sector comparability; "
            "it is not a pre-entry feature and must never enter a signal model."
        ),
        "candidates": rows,
    }
    payload["summary"] = summarize_risk_set_controls(payload)
    validate_risk_set_controls(payload)
    return payload


def validate_risk_set_controls(payload: dict[str, object]) -> None:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("risk-set control payload requires candidates")

    max_controls = int(payload.get("max_controls_per_candidate") or 0)
    horizon_months = int(payload.get("horizon_months") or 0)
    seen_candidates: set[str] = set()

    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError("risk-set candidates must be objects")
        record_id = str(candidate.get("outcome_record_id") or "")
        if not record_id or record_id in seen_candidates:
            raise ValueError("risk-set candidate IDs must be unique")
        seen_candidates.add(record_id)
        if candidate.get("negative_label_eligible"):
            raise ValueError("risk-set candidates cannot create negative labels")
        if int(candidate.get("horizon_months") or -1) != horizon_months:
            raise ValueError("candidate horizon does not match payload horizon")

        expected_end = add_months(str(candidate["notification_month"]), horizon_months)
        if candidate.get("horizon_end_month") != expected_end:
            raise ValueError("candidate horizon_end_month is inconsistent")

        controls = candidate.get("controls")
        if not isinstance(controls, list) or len(controls) > max_controls:
            raise ValueError("invalid risk-set control list")

        seen_controls: set[str] = set()
        for control in controls:
            if not isinstance(control, dict):
                raise ValueError("risk-set controls must be objects")
            key = str(control.get("control_entity_key") or "")
            if not key or key in seen_controls:
                raise ValueError("control assignments must be unique per candidate")
            seen_controls.add(key)
            if control.get("negative_label_eligible"):
                raise ValueError("risk-set controls cannot be negative training labels")
            if control.get("country") != candidate.get("country"):
                raise ValueError("risk-set controls must match ultimate-control country")
            if _month_index(str(control["earliest_investment_canada_month"])) <= _month_index(expected_end):
                raise ValueError("control has Investment Canada activity inside risk horizon")
            if _month_index(str(control["future_new_business_month"])) <= _month_index(expected_end):
                raise ValueError("control new-business event falls inside risk horizon")
            expected_lag = months_between(
                str(candidate["notification_month"]),
                str(control["future_new_business_month"]),
            )
            if int(control["future_entry_lag_months"]) != expected_lag:
                raise ValueError("control future-entry lag is inconsistent")
            if control.get("match_tier") not in {
                "COUNTRY_ACTIVITY", "COUNTRY_ONLY_FALLBACK"
            }:
                raise ValueError("unsupported control match tier")


def summarize_risk_set_controls(payload: dict[str, object]) -> dict[str, object]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("risk-set control payload requires candidates")

    assignments = []
    complete = 0
    with_controls = 0
    full_matches = 0
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("followup_complete"):
            complete += 1
        controls = candidate.get("controls") or []
        if controls:
            with_controls += 1
        if len(controls) == int(payload.get("max_controls_per_candidate") or 0):
            full_matches += 1
        assignments.extend(controls)

    return {
        "candidate_count": len(candidates),
        "candidates_with_complete_followup": complete,
        "candidates_with_controls": with_controls,
        "candidates_with_full_control_count": full_matches,
        "control_assignments": len(assignments),
        "distinct_control_entities": len(
            {str(item["control_entity_key"]) for item in assignments if isinstance(item, dict)}
        ),
        "country_activity_matches": sum(
            isinstance(item, dict) and item.get("match_tier") == "COUNTRY_ACTIVITY"
            for item in assignments
        ),
        "country_only_fallbacks": sum(
            isinstance(item, dict) and item.get("match_tier") == "COUNTRY_ONLY_FALLBACK"
            for item in assignments
        ),
        "negative_labels_created": 0,
    }
