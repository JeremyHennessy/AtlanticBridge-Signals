from __future__ import annotations

import unittest

from atlanticbridge.backtest_power import (
    build_backtest_power_plan,
    exact_fisher_power,
    minimum_equal_group_size,
)


class BacktestPowerPlanningTests(unittest.TestCase):
    def test_current_matched_high_exact_power_is_zero(self):
        self.assertEqual(
            exact_fisher_power(4, 2, 0.50, 0.00),
            0.0,
        )

    def test_current_matched_high_or_medium_exact_power(self):
        self.assertEqual(
            exact_fisher_power(5, 2, 0.40, 0.00),
            0.01024,
        )

    def test_matched_high_point_estimate_requires_12_per_group(self):
        target = minimum_equal_group_size(0.50, 0.00)
        self.assertLess(
            exact_fisher_power(11, 11, 0.50, 0.00),
            0.80,
        )
        self.assertEqual(target["entrant_n"], 12)
        self.assertEqual(target["control_n"], 12)
        self.assertEqual(target["total_n"], 24)
        self.assertEqual(target["power"], 0.80615234375)

    def test_matched_high_or_medium_requires_16_per_group(self):
        target = minimum_equal_group_size(0.40, 0.00)
        self.assertLess(
            exact_fisher_power(15, 15, 0.40, 0.00),
            0.80,
        )
        self.assertEqual(target["entrant_n"], 16)
        self.assertEqual(target["control_n"], 16)
        self.assertEqual(target["total_n"], 32)
        self.assertEqual(target["power"], 0.833432615649)

    def test_20_percent_control_sensitivity_retains_large_targets(self):
        high = minimum_equal_group_size(0.50, 0.20)
        eligible = minimum_equal_group_size(0.40, 0.20)
        self.assertEqual(high["entrant_n"], 44)
        self.assertEqual(high["control_n"], 44)
        self.assertEqual(eligible["entrant_n"], 90)
        self.assertEqual(eligible["control_n"], 90)

    def test_stronger_effect_sensitivity_requires_27_per_group(self):
        target = minimum_equal_group_size(0.60, 0.20)
        self.assertEqual(target["entrant_n"], 27)
        self.assertEqual(target["control_n"], 27)
        self.assertEqual(target["total_n"], 54)
        self.assertEqual(target["power"], 0.802432204664)

    def test_plan_is_explicitly_exploratory_and_matched(self):
        result = build_backtest_power_plan()
        self.assertEqual(result["status"], "EXPLORATORY_PLANNING_ONLY")
        self.assertIn("Matched-stratum", result["planning_boundary"])
        self.assertIn(
            "separately predeclared confirmatory validation cohort",
            result["planning_boundary"],
        )
        names = {row["name"] for row in result["scenarios"]}
        self.assertIn("CURRENT_MATCHED_HIGH_POINT_ESTIMATE", names)
        self.assertIn("CONTROL_RATE_20_PERCENT_SENSITIVITY_HIGH", names)


if __name__ == "__main__":
    unittest.main()
