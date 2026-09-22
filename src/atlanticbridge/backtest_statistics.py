from __future__ import annotations

import math


PRESENT = "PRESENT"
ABSENT = "ABSENT_WITH_PROVEN_COVERAGE"
UNKNOWN = "UNKNOWN_UNVERIFIED_COVERAGE"
ALPHA = 0.05
Z_95 = 1.959963984540054
PUBLICATION_GATE_MODE = "EXPLORATORY_NO_PREDECLARED_PRIMARY_ENDPOINT"


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)


def _wilson_bounds_raw(
    successes: int,
    total: int,
) -> tuple[float, float]:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")

    p = successes / total
    z2 = Z_95 * Z_95
    denominator = 1 + z2 / total
    center = (p + z2 / (2 * total)) / denominator
    half = (
        Z_95
        * math.sqrt(
            p * (1 - p) / total
            + z2 / (4 * total * total)
        )
        / denominator
    )
    return max(0.0, center - half), min(1.0, center + half)


def wilson_interval(successes: int, total: int) -> dict[str, float | int | None]:
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("invalid binomial counts")
    if total == 0:
        return {
            "successes": successes,
            "total": total,
            "point_estimate": None,
            "lower_95": None,
            "upper_95": None,
        }

    lower, upper = _wilson_bounds_raw(successes, total)
    return {
        "successes": successes,
        "total": total,
        "point_estimate": round(successes / total, 6),
        "lower_95": round(lower, 6),
        "upper_95": round(upper, 6),
    }


def fisher_exact_two_sided(
    entrant_present: int,
    entrant_absent: int,
    control_present: int,
    control_absent: int,
) -> float:
    values = (
        entrant_present,
        entrant_absent,
        control_present,
        control_absent,
    )
    if any(value < 0 for value in values):
        raise ValueError("Fisher counts must be non-negative")

    entrant_total = entrant_present + entrant_absent
    control_total = control_present + control_absent
    present_total = entrant_present + control_present
    grand_total = entrant_total + control_total
    if grand_total == 0:
        raise ValueError("Fisher table cannot be empty")

    denominator = math.comb(grand_total, entrant_total)

    def probability(value: int) -> float:
        return (
            math.comb(present_total, value)
            * math.comb(
                grand_total - present_total,
                entrant_total - value,
            )
            / denominator
        )

    lower = max(0, entrant_total - (grand_total - present_total))
    upper = min(entrant_total, present_total)
    observed_probability = probability(entrant_present)
    p_value = sum(
        probability(value)
        for value in range(lower, upper + 1)
        if probability(value) <= observed_probability + 1e-15
    )
    return round(min(1.0, p_value), 6)


def _newcombe_risk_difference(
    entrant_interval: dict[str, float | int | None],
    control_interval: dict[str, float | int | None],
) -> dict[str, float | None]:
    entrant_successes = int(entrant_interval["successes"])
    entrant_total = int(entrant_interval["total"])
    control_successes = int(control_interval["successes"])
    control_total = int(control_interval["total"])
    if entrant_total == 0 or control_total == 0:
        return {
            "point_estimate": None,
            "lower_95": None,
            "upper_95": None,
        }

    entrant_point = entrant_successes / entrant_total
    control_point = control_successes / control_total
    entrant_lower, entrant_upper = _wilson_bounds_raw(
        entrant_successes,
        entrant_total,
    )
    control_lower, control_upper = _wilson_bounds_raw(
        control_successes,
        control_total,
    )

    difference = entrant_point - control_point
    lower_delta = math.sqrt(
        (entrant_point - entrant_lower) ** 2
        + (control_upper - control_point) ** 2
    )
    upper_delta = math.sqrt(
        (entrant_upper - entrant_point) ** 2
        + (control_point - control_lower) ** 2
    )

    return {
        "point_estimate": round(difference, 6),
        "lower_95": round(difference - lower_delta, 6),
        "upper_95": round(difference + upper_delta, 6),
    }


def _extract_candidate_rows(
    backtest_001: dict[str, object],
) -> list[dict[str, object]]:
    signals = backtest_001.get("signals")
    if not isinstance(signals, list):
        raise ValueError("Backtest 001 requires a signals list")

    candidates: list[dict[str, object]] = []
    for signal in signals:
        if not isinstance(signal, dict):
            raise ValueError("Backtest 001 signal rows must be objects")
        counts = signal.get("state_counts")
        if not isinstance(counts, dict):
            raise ValueError("Backtest 001 signal missing state_counts")
        if int(counts.get(PRESENT, 0)) <= 0:
            continue
        if int(counts.get(ABSENT, 0)) <= 0:
            continue
        candidates.append(signal)
    return candidates


def build_backtest_002(
    *,
    backtest_001: dict[str, object],
) -> dict[str, object]:
    summary = backtest_001.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Backtest 001 requires summary")

    candidates = _extract_candidate_rows(backtest_001)
    diagnostics: list[dict[str, object]] = []
    inferentially_resolved_rows = 0

    for signal in candidates:
        family = str(signal.get("signal_family") or "")
        sensitivity = signal.get("identity_confidence_sensitivity")
        if not family or not isinstance(sensitivity, list):
            raise ValueError("candidate signal lacks identity sensitivity")

        rows: list[dict[str, object]] = []
        for row in sensitivity:
            if not isinstance(row, dict):
                raise ValueError("identity sensitivity rows must be objects")
            if row.get("error_rate_status") != (
                "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET"
            ):
                continue

            entrant_unknown = int(row.get("entrant_unknown", 0))
            control_unknown = int(row.get("control_unknown", 0))
            if entrant_unknown or control_unknown:
                continue

            entrant_present = int(row["entrant_present"])
            entrant_absent = int(
                row["entrant_absent_with_proven_coverage"]
            )
            control_present = int(row["control_present"])
            control_absent = int(
                row["control_absent_with_proven_coverage"]
            )

            entrant_interval = wilson_interval(
                entrant_present,
                entrant_present + entrant_absent,
            )
            control_interval = wilson_interval(
                control_present,
                control_present + control_absent,
            )
            risk_difference = _newcombe_risk_difference(
                entrant_interval,
                control_interval,
            )
            p_value = fisher_exact_two_sided(
                entrant_present,
                entrant_absent,
                control_present,
                control_absent,
            )
            resolved = (
                p_value <= ALPHA
                and risk_difference["lower_95"] is not None
                and float(risk_difference["lower_95"]) > 0
            )
            if resolved:
                inferentially_resolved_rows += 1

            rows.append(
                {
                    "identity_tier": row["identity_tier"],
                    "offset_months": row["offset_months"],
                    "entrant_positive_rate": entrant_interval,
                    "control_positive_rate": control_interval,
                    "risk_difference": risk_difference,
                    "fisher_exact_two_sided_p": p_value,
                    "alpha": ALPHA,
                    "directional_discrimination_resolved": resolved,
                }
            )

        diagnostics.append(
            {
                "signal_family": family,
                "tested_rows": rows,
            }
        )

    publication_allowed = False
    if inferentially_resolved_rows:
        reason = (
            "One or more exploratory signal/cutoff rows satisfy the local "
            "diagnostic threshold, but Backtest 002 has no predeclared primary "
            "endpoint and uses the same cohort for exploration. Expansion "
            "Score weight publication remains blocked pending a separate "
            "confirmatory design with a predeclared primary endpoint and "
            "independent holdout or equivalent prospective validation."
        )
    else:
        reason = (
            "No identity-qualified signal/cutoff comparison currently has "
            "both a two-sided Fisher exact p-value <= 0.05 and a 95% "
            "Newcombe risk-difference interval entirely above zero. In "
            "addition, Backtest 002 is exploratory and has no predeclared "
            "primary endpoint. Expansion Score weight publication remains "
            "blocked pending a separate confirmatory design."
        )

    return {
        "schema_version": 1,
        "design": "BACKTEST_002_STATISTICAL_SUFFICIENCY_DIAGNOSTIC",
        "target_boundary": backtest_001.get("target_boundary"),
        "method": {
            "positive_rate_interval": "Wilson score interval, 95%",
            "risk_difference_interval": (
                "Newcombe 1998 method 10 hybrid score interval, 95%"
            ),
            "association_test": "Fisher exact, two-sided",
            "alpha": ALPHA,
            "multiple_testing_boundary": (
                "Exploratory diagnostic only. No cutoff or identity tier is "
                "predeclared as a primary endpoint, so no exploratory row may "
                "open the publication gate."
            ),
        },
        "publication_gate_mode": PUBLICATION_GATE_MODE,
        "backtest_001_weighting_design_gate": bool(
            summary.get("expansion_score_1_0_weighting_allowed")
        ),
        "candidate_signal_count": len(candidates),
        "inferentially_resolved_rows": inferentially_resolved_rows,
        "expansion_score_1_0_weight_publication_allowed": publication_allowed,
        "score_publication_gate_reason": reason,
        "signals": diagnostics,
    }
