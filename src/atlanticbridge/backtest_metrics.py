from __future__ import annotations

from collections import Counter
from datetime import date
import math
from typing import Iterable

from .event_time_signals import OFFSETS_MONTHS, cutoff_exclusive, month_start


PRESENT = "PRESENT"
ABSENT = "ABSENT_WITH_PROVEN_COVERAGE"
UNKNOWN = "UNKNOWN_UNVERIFIED_COVERAGE"
NOT_ESTIMABLE = "NOT_ESTIMABLE"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _linear_quantile(values: Iterable[int], probability: float) -> float | None:
    ordered = sorted(int(value) for value in values)
    if not ordered:
        return None
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    if len(ordered) == 1:
        return float(ordered[0])
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _lead_time_summary(days: list[int]) -> dict[str, object]:
    if not days:
        return {
            "n": 0,
            "median_days": None,
            "p25_days": None,
            "p75_days": None,
            "median_months_approx": None,
            "p25_months_approx": None,
            "p75_months_approx": None,
        }

    p25 = _linear_quantile(days, 0.25)
    median = _linear_quantile(days, 0.50)
    p75 = _linear_quantile(days, 0.75)
    assert p25 is not None and median is not None and p75 is not None

    def months(value: float) -> float:
        return round(value / 30.4375, 3)

    return {
        "n": len(days),
        "median_days": round(median, 3),
        "p25_days": round(p25, 3),
        "p75_days": round(p75, 3),
        "median_months_approx": months(median),
        "p25_months_approx": months(p25),
        "p75_months_approx": months(p75),
    }


def _entity_index(
    entities_payload: dict[str, object],
) -> dict[str, dict[str, object]]:
    rows = entities_payload.get("entities")
    if not isinstance(rows, list):
        raise ValueError("backtest entities payload requires entities list")
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("entity rows must be objects")
        entity_id = str(row.get("entity_id") or "")
        if not entity_id:
            raise ValueError("entity row missing entity_id")
        if entity_id in result:
            raise ValueError(f"duplicate backtest entity {entity_id}")
        if row.get("role") not in {"ENTRANT", "CONTROL"}:
            raise ValueError(f"invalid role for {entity_id}")
        result[entity_id] = row
    return result


def _signal_input_index(
    accepted_input: dict[str, object],
) -> dict[str, dict[str, object]]:
    rows = accepted_input.get("signals")
    if not isinstance(rows, list):
        raise ValueError("accepted input requires signals list")
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("signal input rows must be objects")
        family = str(row.get("signal_family") or "")
        if not family:
            raise ValueError("signal input row missing signal_family")
        if family in result:
            raise ValueError(f"duplicate signal input {family}")
        result[family] = row
    return result


def _semantics_index(
    semantics_payload: dict[str, object],
) -> dict[str, dict[str, object]]:
    rows = semantics_payload.get("sources")
    if not isinstance(rows, list):
        raise ValueError("signal semantics requires sources list")
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source semantics rows must be objects")
        family = str(row.get("signal_family") or "")
        if not family:
            raise ValueError("source semantics row missing signal_family")
        if family in result:
            raise ValueError(f"duplicate source semantics {family}")
        result[family] = row
    return result


def _earliest_evidence_index(
    signal_input: dict[str, object],
) -> dict[str, date]:
    rows = signal_input.get("earliest_public_evidence") or []
    if not isinstance(rows, list):
        raise ValueError("earliest_public_evidence must be a list")
    result: dict[str, date] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("earliest evidence rows must be objects")
        entity_id = str(row.get("entity_id") or "")
        value = str(row.get("earliest_public_date") or "")
        if not entity_id or not value:
            raise ValueError("earliest evidence requires entity_id and date")
        parsed = date.fromisoformat(value)
        current = result.get(entity_id)
        if current is None or parsed < current:
            result[entity_id] = parsed
    return result


def _state_for(
    *,
    entity: dict[str, object],
    signal_input: dict[str, object],
    earliest_evidence: dict[str, date],
    offset_months: int,
) -> str:
    if not bool(entity.get("foreign_signal_identity_eligible")):
        return UNKNOWN

    family_mode = str(signal_input.get("observation_mode") or "")
    cutoff = cutoff_exclusive(str(entity["anchor_month"]), offset_months)
    earliest = earliest_evidence.get(str(entity["entity_id"]))
    if earliest is not None and earliest < cutoff:
        return PRESENT

    if bool(signal_input.get("absence_coverage_proven")):
        start_value = str(
            signal_input.get("absence_coverage_start_date") or ""
        ).strip()
        end_value = str(
            signal_input.get("absence_coverage_end_exclusive") or ""
        ).strip()
        if not start_value or not end_value:
            raise ValueError(
                "absence_coverage_proven requires explicit start/end bounds"
            )
        start = date.fromisoformat(start_value)
        end_exclusive = date.fromisoformat(end_value)
        if start < cutoff <= end_exclusive:
            return ABSENT

    if not family_mode:
        raise ValueError(
            f"signal input lacks observation_mode: {signal_input.get('signal_family')}"
        )
    return UNKNOWN


def _role_counts(
    rows: list[dict[str, object]],
    role: str,
) -> dict[str, int]:
    subset = [row for row in rows if row["role"] == role]
    states = Counter(str(row["state"]) for row in subset)
    return {
        "entities": len(subset),
        "present": states[PRESENT],
        "absent_with_proven_coverage": states[ABSENT],
        "unknown": states[UNKNOWN],
    }


def _prevalence_metrics(
    role_counts: dict[str, int],
) -> dict[str, object]:
    total = role_counts["entities"]
    present = role_counts["present"]
    absent = role_counts["absent_with_proven_coverage"]
    unknown = role_counts["unknown"]
    lower_bound = _ratio(present, total)

    if unknown == 0:
        estimate = _ratio(present, present + absent)
        status = "ESTIMABLE"
    else:
        estimate = None
        status = "NOT_ESTIMABLE_UNKNOWN_SOURCE_COVERAGE"

    return {
        "status": status,
        "point_estimate": estimate,
        "observed_positive_lower_bound": lower_bound,
        "present": present,
        "absent_with_proven_coverage": absent,
        "unknown": unknown,
        "denominator": total,
    }


def _error_rate_metrics(
    entrant_counts: dict[str, int],
    control_counts: dict[str, int],
) -> dict[str, object]:
    if (
        entrant_counts["entities"] == 0
        or control_counts["entities"] == 0
    ):
        return {
            "false_positive_rate": None,
            "false_negative_rate": None,
            "status": "NOT_ESTIMABLE_EMPTY_ROLE",
            "observed_control_positive_lower_bound": _ratio(
                control_counts["present"],
                control_counts["entities"],
            ),
            "observed_entrant_positive_lower_bound": _ratio(
                entrant_counts["present"],
                entrant_counts["entities"],
            ),
        }

    entrant_unknown = entrant_counts["unknown"]
    control_unknown = control_counts["unknown"]
    if entrant_unknown or control_unknown:
        return {
            "false_positive_rate": None,
            "false_negative_rate": None,
            "status": "NOT_ESTIMABLE_SOURCE_ABSENCE_UNPROVEN",
            "observed_control_positive_lower_bound": _ratio(
                control_counts["present"],
                control_counts["entities"],
            ),
            "observed_entrant_positive_lower_bound": _ratio(
                entrant_counts["present"],
                entrant_counts["entities"],
            ),
        }

    false_positive_rate = _ratio(
        control_counts["present"],
        control_counts["entities"],
    )
    false_negative_rate = _ratio(
        entrant_counts["absent_with_proven_coverage"],
        entrant_counts["entities"],
    )
    return {
        "false_positive_rate": false_positive_rate,
        "false_negative_rate": false_negative_rate,
        "status": "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET",
        "observed_control_positive_lower_bound": false_positive_rate,
        "observed_entrant_positive_lower_bound": _ratio(
            entrant_counts["present"],
            entrant_counts["entities"],
        ),
    }


def _confidence_allowed(entity: dict[str, object], tier: str) -> bool:
    confidence = str(entity.get("identity_confidence") or "").upper()
    if not bool(entity.get("foreign_signal_identity_eligible")):
        return False
    if tier == "HIGH":
        return confidence == "HIGH"
    if tier == "HIGH_OR_MEDIUM":
        return confidence in {"HIGH", "MEDIUM"}
    raise ValueError(f"unsupported identity tier {tier}")


def build_backtest_001(
    *,
    entities_payload: dict[str, object],
    semantics_payload: dict[str, object],
    accepted_input: dict[str, object],
) -> dict[str, object]:
    entities = _entity_index(entities_payload)
    semantics = _semantics_index(semantics_payload)
    signals = _signal_input_index(accepted_input)

    if set(semantics) != set(signals):
        raise ValueError(
            "accepted signal input must cover exactly the source-semantics families"
        )

    role_totals = Counter(str(row["role"]) for row in entities.values())
    if role_totals != Counter({"ENTRANT": 7, "CONTROL": 5}):
        raise ValueError(f"Backtest 001 cohort changed unexpectedly: {role_totals}")

    entrant_candidate_ids = {
        str(row.get("candidate_outcome_id") or "")
        for row in entities.values()
        if row["role"] == "ENTRANT"
    }
    if "" in entrant_candidate_ids:
        raise ValueError("entrant entity missing candidate_outcome_id")
    for entity_id, entity in entities.items():
        if entity["role"] != "CONTROL":
            continue
        matched_candidate = str(
            entity.get("candidate_outcome_id") or ""
        )
        if matched_candidate not in entrant_candidate_ids:
            raise ValueError(
                f"control {entity_id} references unknown entrant stratum "
                f"{matched_candidate!r}"
            )

    output_signals: list[dict[str, object]] = []
    signals_with_any_present = 0
    signals_with_proven_absence = 0
    signals_with_estimable_error_rates = 0
    signals_with_identity_eligible_estimable_error_rates = 0
    signals_with_both_positive_and_absence_evidence = 0

    for family in semantics:
        signal_input = signals[family]
        earliest = _earliest_evidence_index(signal_input)
        family_rows: list[dict[str, object]] = []

        for entity_id, entity in entities.items():
            for offset in OFFSETS_MONTHS:
                state = _state_for(
                    entity=entity,
                    signal_input=signal_input,
                    earliest_evidence=earliest,
                    offset_months=offset,
                )
                family_rows.append(
                    {
                        "entity_id": entity_id,
                        "role": entity["role"],
                        "offset_months": offset,
                        "state": state,
                        "identity_confidence": entity["identity_confidence"],
                    }
                )

        offset_metrics: list[dict[str, object]] = []
        for offset in OFFSETS_MONTHS:
            offset_rows = [
                row for row in family_rows
                if row["offset_months"] == offset
            ]
            entrants = _role_counts(offset_rows, "ENTRANT")
            controls = _role_counts(offset_rows, "CONTROL")
            non_unknown = sum(
                1 for row in offset_rows if row["state"] != UNKNOWN
            )
            offset_metrics.append(
                {
                    "offset_months": offset,
                    "entrant_prevalence": _prevalence_metrics(entrants),
                    "control_prevalence": _prevalence_metrics(controls),
                    "error_rates": _error_rate_metrics(entrants, controls),
                    "source_observable_rows": non_unknown,
                    "source_total_rows": len(offset_rows),
                    "source_observable_fraction": _ratio(
                        non_unknown, len(offset_rows)
                    ),
                }
            )

        state_counts = Counter(str(row["state"]) for row in family_rows)
        if state_counts[PRESENT]:
            signals_with_any_present += 1
        if state_counts[ABSENT]:
            signals_with_proven_absence += 1
        if all(
            metric["error_rates"]["status"]
            == "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET"
            for metric in offset_metrics
        ):
            signals_with_estimable_error_rates += 1

        if state_counts[PRESENT] and state_counts[ABSENT]:
            signals_with_both_positive_and_absence_evidence += 1

        entrant_leads: list[int] = []
        control_leads: list[int] = []
        for entity_id, evidence_date in earliest.items():
            entity = entities.get(entity_id)
            if entity is None:
                raise ValueError(
                    f"accepted evidence references unknown entity {entity_id}"
                )
            if not bool(entity.get("foreign_signal_identity_eligible")):
                continue
            anchor = month_start(str(entity["anchor_month"]))
            if evidence_date >= anchor:
                continue
            days = (anchor - evidence_date).days
            if entity["role"] == "ENTRANT":
                entrant_leads.append(days)
            else:
                control_leads.append(days)

        identity_sensitivity: list[dict[str, object]] = []
        for tier in ("HIGH", "HIGH_OR_MEDIUM"):
            eligible_entrant_strata = {
                str(entity["candidate_outcome_id"])
                for entity in entities.values()
                if entity["role"] == "ENTRANT"
                and _confidence_allowed(entity, tier)
            }
            for offset in OFFSETS_MONTHS:
                tier_rows = []
                matched_control_strata: set[str] = set()
                for row in family_rows:
                    if row["offset_months"] != offset:
                        continue
                    entity = entities[str(row["entity_id"])]
                    if not _confidence_allowed(entity, tier):
                        continue
                    if entity["role"] == "CONTROL":
                        matched_candidate = str(
                            entity["candidate_outcome_id"]
                        )
                        if matched_candidate not in eligible_entrant_strata:
                            continue
                        matched_control_strata.add(matched_candidate)
                    tier_rows.append(row)
                entrant_counts = _role_counts(tier_rows, "ENTRANT")
                control_counts = _role_counts(tier_rows, "CONTROL")
                subset_error_rates = _error_rate_metrics(
                    entrant_counts,
                    control_counts,
                )
                identity_sensitivity.append(
                    {
                        "identity_tier": tier,
                        "offset_months": offset,
                        "eligible_entrant_strata": len(
                            eligible_entrant_strata
                        ),
                        "matched_control_strata": len(
                            matched_control_strata
                        ),
                        "entrant_present_lower_bound": _ratio(
                            entrant_counts["present"],
                            entrant_counts["entities"],
                        ),
                        "entrant_entities": entrant_counts["entities"],
                        "entrant_present": entrant_counts["present"],
                        "entrant_absent_with_proven_coverage":
                            entrant_counts["absent_with_proven_coverage"],
                        "entrant_unknown": entrant_counts["unknown"],
                        "control_present_lower_bound": _ratio(
                            control_counts["present"],
                            control_counts["entities"],
                        ),
                        "control_entities": control_counts["entities"],
                        "control_present": control_counts["present"],
                        "control_absent_with_proven_coverage":
                            control_counts["absent_with_proven_coverage"],
                        "control_unknown": control_counts["unknown"],
                        "false_positive_rate":
                            subset_error_rates["false_positive_rate"],
                        "false_negative_rate":
                            subset_error_rates["false_negative_rate"],
                        "error_rate_status": subset_error_rates["status"],
                    }
                )

        high_or_medium_rows = [
            row
            for row in identity_sensitivity
            if row["identity_tier"] == "HIGH_OR_MEDIUM"
        ]
        if high_or_medium_rows and all(
            row["error_rate_status"]
            == "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET"
            for row in high_or_medium_rows
        ):
            signals_with_identity_eligible_estimable_error_rates += 1

        output_signals.append(
            {
                "signal_family": family,
                "source_semantics_status": semantics[family].get("status"),
                "observation_mode": signal_input.get("observation_mode"),
                "absence_coverage_proven": bool(
                    signal_input.get("absence_coverage_proven")
                ),
                "state_counts": {
                    key: state_counts[key]
                    for key in (PRESENT, ABSENT, UNKNOWN)
                },
                "source_availability": {
                    "total_event_time_rows": len(family_rows),
                    "observable_rows": state_counts[PRESENT] + state_counts[ABSENT],
                    "observable_fraction": _ratio(
                        state_counts[PRESENT] + state_counts[ABSENT],
                        len(family_rows),
                    ),
                    "presence_rows": state_counts[PRESENT],
                    "proven_absence_rows": state_counts[ABSENT],
                    "unknown_rows": state_counts[UNKNOWN],
                },
                "offset_metrics": offset_metrics,
                "anchor_lead_time": {
                    "interpretation": (
                        "Days from earliest verified public signal to the first "
                        "day of the censored notification anchor month; not a "
                        "verified first-operation lead time."
                    ),
                    "entrants": _lead_time_summary(entrant_leads),
                    "controls": _lead_time_summary(control_leads),
                },
                "identity_confidence_sensitivity": identity_sensitivity,
            }
        )

    score_allowed = (
        signals_with_identity_eligible_estimable_error_rates >= 1
        and signals_with_both_positive_and_absence_evidence >= 1
    )

    return {
        "schema_version": 1,
        "design": "BACKTEST_001_SOURCE_INDEPENDENT_EVENT_TIME_DIAGNOSTIC",
        "target_boundary": accepted_input.get("target_boundary"),
        "offsets_months": list(OFFSETS_MONTHS),
        "identity_sensitivity_rule": (
            "At each confidence tier, controls are retained only when their "
            "matched entrant candidate stratum is retained at that same tier. "
            "This preserves the risk-set matching design during sensitivity "
            "analysis."
        ),
        "cohort": {
            "entrant_entities": role_totals["ENTRANT"],
            "time_indexed_control_entities": role_totals["CONTROL"],
            "permanent_negative_labels": 0,
        },
        "summary": {
            "signal_family_count": len(output_signals),
            "signals_with_any_present_evidence": signals_with_any_present,
            "signals_with_proven_absence_coverage": signals_with_proven_absence,
            "signals_with_estimable_false_rates":
                signals_with_estimable_error_rates,
            "signals_with_identity_eligible_estimable_false_rates":
                signals_with_identity_eligible_estimable_error_rates,
            "signals_with_both_positive_and_absence_evidence":
                signals_with_both_positive_and_absence_evidence,
            "expansion_score_1_0_weighting_allowed": score_allowed,
            "score_gate_reason": (
                None
                if score_allowed
                else (
                    "No signal currently has both verified positive evidence "
                    "and proven historical absence coverage with estimable "
                    "identity-qualified false rates. Score weights must remain "
                    "disabled."
                )
            ),
        },
        "accepted_snapshot_provenance":
            accepted_input.get("accepted_snapshot_provenance"),
        "signals": output_signals,
    }
