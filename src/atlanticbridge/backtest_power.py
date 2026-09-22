from __future__ import annotations

import math


ALPHA = 0.05
TARGET_POWER = 0.80


def _validate_probability(value: float, name: str) -> None:
    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")


def _binomial_probabilities(n: int, p: float) -> list[float]:
    if n < 1:
        raise ValueError("sample size must be at least 1")
    _validate_probability(p, "probability")
    return [
        math.comb(n, k) * (p ** k) * ((1.0 - p) ** (n - k))
        for k in range(n + 1)
    ]


def _fisher_rejection_region(
    entrant_n: int,
    control_n: int,
    *,
    alpha: float = ALPHA,
) -> set[tuple[int, int]]:
    if entrant_n < 1 or control_n < 1:
        raise ValueError("sample sizes must be at least 1")
    _validate_probability(alpha, "alpha")
    if alpha == 0:
        return set()

    total_n = entrant_n + control_n
    rejected: set[tuple[int, int]] = set()

    # Fisher's exact test conditions on the total number of observed positives.
    # For a fixed margin, every table probability shares the same denominator.
    # Integer hypergeometric numerators therefore let us reproduce the
    # two-sided "probability <= observed table probability" definition without
    # floating-point ordering ambiguity.
    for total_present in range(total_n + 1):
        entrant_min = max(0, total_present - control_n)
        entrant_max = min(entrant_n, total_present)
        denominator = math.comb(total_n, total_present)

        table_numerators = [
            (
                entrant_present,
                math.comb(entrant_n, entrant_present)
                * math.comb(
                    control_n,
                    total_present - entrant_present,
                ),
            )
            for entrant_present in range(entrant_min, entrant_max + 1)
        ]

        mass_by_numerator: dict[int, int] = {}
        for _, numerator in table_numerators:
            mass_by_numerator[numerator] = (
                mass_by_numerator.get(numerator, 0) + numerator
            )

        cumulative = 0
        p_value_by_numerator: dict[int, float] = {}
        for numerator in sorted(mass_by_numerator):
            cumulative += mass_by_numerator[numerator]
            p_value_by_numerator[numerator] = cumulative / denominator

        for entrant_present, numerator in table_numerators:
            control_present = total_present - entrant_present
            if p_value_by_numerator[numerator] <= alpha + 1e-15:
                rejected.add((entrant_present, control_present))

    return rejected


def exact_fisher_power(
    entrant_n: int,
    control_n: int,
    entrant_positive_rate: float,
    control_positive_rate: float,
    *,
    alpha: float = ALPHA,
) -> float:
    _validate_probability(entrant_positive_rate, "entrant_positive_rate")
    _validate_probability(control_positive_rate, "control_positive_rate")
    rejection_region = _fisher_rejection_region(
        entrant_n,
        control_n,
        alpha=alpha,
    )
    entrant_probs = _binomial_probabilities(
        entrant_n,
        entrant_positive_rate,
    )
    control_probs = _binomial_probabilities(
        control_n,
        control_positive_rate,
    )

    power = sum(
        entrant_probs[entrant_present] * control_probs[control_present]
        for entrant_present, control_present in rejection_region
    )
    return round(power, 12)


def minimum_equal_group_size(
    entrant_positive_rate: float,
    control_positive_rate: float,
    *,
    target_power: float = TARGET_POWER,
    alpha: float = ALPHA,
    max_group_size: int = 500,
) -> dict[str, int | float]:
    _validate_probability(target_power, "target_power")
    if target_power <= 0:
        raise ValueError("target_power must be greater than zero")
    if max_group_size < 2:
        raise ValueError("max_group_size must be at least 2")

    for group_size in range(2, max_group_size + 1):
        power = exact_fisher_power(
            group_size,
            group_size,
            entrant_positive_rate,
            control_positive_rate,
            alpha=alpha,
        )
        if power >= target_power:
            return {
                "entrant_n": group_size,
                "control_n": group_size,
                "total_n": group_size * 2,
                "power": power,
            }

    raise ValueError(
        "target power not reached within max_group_size="
        f"{max_group_size}"
    )


def build_backtest_power_plan() -> dict[str, object]:
    scenarios = [
        {
            "name": "CURRENT_MATCHED_HIGH_POINT_ESTIMATE",
            "entrant_positive_rate": 0.50,
            "control_positive_rate": 0.00,
            "current_entrant_n": 4,
            "current_control_n": 2,
            "basis": (
                "Matched-stratum Backtest 002 HIGH point estimates: "
                "2/4 entrants and 0/2 controls. The zero control rate is "
                "based on only two matched controls and is not treated as a "
                "stable population estimate."
            ),
        },
        {
            "name": "CURRENT_MATCHED_HIGH_OR_MEDIUM_POINT_ESTIMATE",
            "entrant_positive_rate": 0.40,
            "control_positive_rate": 0.00,
            "current_entrant_n": 5,
            "current_control_n": 2,
            "basis": (
                "Matched-stratum Backtest 002 HIGH_OR_MEDIUM point "
                "estimates: 2/5 entrants and 0/2 controls. The zero control "
                "rate is based on only two matched controls and is not "
                "treated as a stable population estimate."
            ),
        },
        {
            "name": "CONTROL_RATE_20_PERCENT_SENSITIVITY_HIGH",
            "entrant_positive_rate": 0.50,
            "control_positive_rate": 0.20,
            "current_entrant_n": 4,
            "current_control_n": 2,
            "basis": (
                "Conservative planning sensitivity using a 20% control "
                "positive rate rather than the unstable observed 0/2."
            ),
        },
        {
            "name": "CONTROL_RATE_20_PERCENT_SENSITIVITY_HIGH_OR_MEDIUM",
            "entrant_positive_rate": 0.40,
            "control_positive_rate": 0.20,
            "current_entrant_n": 5,
            "current_control_n": 2,
            "basis": (
                "Conservative planning sensitivity using a 20% control "
                "positive rate rather than the unstable observed 0/2."
            ),
        },
        {
            "name": "STRONGER_EFFECT_SENSITIVITY",
            "entrant_positive_rate": 0.60,
            "control_positive_rate": 0.20,
            "current_entrant_n": 4,
            "current_control_n": 2,
            "basis": (
                "Sensitivity scenario only; not an observed effect estimate."
            ),
        },
    ]

    planned = []
    for scenario in scenarios:
        current_power = exact_fisher_power(
            int(scenario["current_entrant_n"]),
            int(scenario["current_control_n"]),
            float(scenario["entrant_positive_rate"]),
            float(scenario["control_positive_rate"]),
        )
        target = minimum_equal_group_size(
            float(scenario["entrant_positive_rate"]),
            float(scenario["control_positive_rate"]),
        )
        planned.append(
            {
                **scenario,
                "current_exact_power": current_power,
                "target_power": TARGET_POWER,
                "alpha": ALPHA,
                "minimum_equal_group_plan": target,
            }
        )

    return {
        "schema_version": 1,
        "design": "BACKTEST_EXACT_FISHER_POWER_PLANNING",
        "status": "EXPLORATORY_PLANNING_ONLY",
        "test_definition": (
            "Two-sided Fisher exact test using the same probability-ordering "
            "definition as Backtest 002."
        ),
        "planning_boundary": (
            "Matched-stratum Backtest 002 rates are reused only as "
            "effect-size planning scenarios. The observed control rate is "
            "0/2 and is therefore especially unstable; explicit 20% control-"
            "rate sensitivity scenarios are retained. These calculations do "
            "not validate an effect and do not replace a separately "
            "predeclared confirmatory validation cohort."
        ),
        "scenarios": planned,
    }
