from __future__ import annotations

import unittest

from atlanticbridge.backtest_power import (
    build_backtest_power_plan,
    exact_fisher_power,
    minimum_equal_group_size,
)


class BacktestPowerPlanningTests(unittest.TestCase):
    def test_current_high_exact_power(self):
        self.assertEqual(
            exact_fisher_power(4, 5, 0.50, 0.20),
            0.1285,
        )

    def test_current_high_or_medium_exact_power(self):
        self.assertEqual(
            exact_fisher_power(5, 5, 0.40, 0.20),
            0.0333210624,
        )

    def test_high_effect_requires_44_per_group_for_80_percent_power(self):
        below = exact_fisher_power(43, 43, 0.50, 0.20)
        target = minimum_equal_group_size(0.50, 0.20)
        self.assertLess(below, 0.80)
        self.assertEqual(target["entrant_n"], 44)
        self.assertEqual(target["control_n"], 44)
        self.assertEqual(target["total_n"], 88)
        self.assertEqual(target["power"], 0.802089515244)

    def test_high_or_medium_effect_requires_90_per_group(self):
        below = exact_fisher_power(89, 89, 0.40, 0.20)
        target = minimum_equal_group_size(0.40, 0.20)
        self.assertLess(below, 0.80)
        self.assertEqual(target["entrant_n"], 90)
        self.assertEqual(target["control_n"], 90)
        self.assertEqual(target["total_n"], 180)
        self.assertEqual(target["power"], 0.801679998874)

    def test_stronger_effect_sensitivity_requires_27_per_group(self):
        target = minimum_equal_group_size(0.60, 0.20)
        self.assertLess(
            exact_fisher_power(26, 26, 0.60, 0.20),
            0.80,
        )
        self.assertEqual(target["entrant_n"], 27)
        self.assertEqual(target["control_n"], 27)
        self.assertEqual(target["total_n"], 54)
        self.assertEqual(target["power"], 0.802432204664)

    def test_plan_is_explicitly_exploratory(self):
        result = build_backtest_power_plan()
        self.assertEqual(result["status"], "EXPLORATORY_PLANNING_ONLY")
        self.assertIn(
            "separately predeclared confirmatory validation cohort",
            result["planning_boundary"],
        )


if __name__ == "__main__":
    unittest.main()
