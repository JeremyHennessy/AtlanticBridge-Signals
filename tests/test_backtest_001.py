from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.backtest_metrics import build_backtest_001


ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "reviews/backtests/2026-09-21-backtest-entities.json"
SEMANTICS = ROOT / "reviews/backtests/2026-09-21-signal-source-semantics.json"
INPUT = ROOT / "reviews/backtests/2026-09-21-backtest-001-input.json"


class Backtest001Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_backtest_001(
            entities_payload=json.loads(ENTITIES.read_text()),
            semantics_payload=json.loads(SEMANTICS.read_text()),
            accepted_input=json.loads(INPUT.read_text()),
        )

    def test_backtest_cohort_and_score_gate_fail_closed(self):
        self.assertEqual(self.result["cohort"]["entrant_entities"], 7)
        self.assertEqual(self.result["cohort"]["time_indexed_control_entities"], 5)
        self.assertEqual(self.result["cohort"]["permanent_negative_labels"], 0)

        summary = self.result["summary"]
        self.assertEqual(summary["signal_family_count"], 5)
        self.assertEqual(summary["signals_with_any_present_evidence"], 1)
        self.assertEqual(summary["signals_with_proven_absence_coverage"], 1)
        self.assertEqual(summary["signals_with_estimable_false_rates"], 0)
        self.assertEqual(
            summary["signals_with_identity_eligible_estimable_false_rates"],
            1,
        )
        self.assertEqual(
            summary["signals_with_both_positive_and_absence_evidence"],
            0,
        )
        self.assertFalse(summary["expansion_score_1_0_weighting_allowed"])
        self.assertTrue(summary["score_gate_reason"])

    def test_cipo_is_presence_only_and_never_claims_absence(self):
        cipo = next(
            row for row in self.result["signals"]
            if row["signal_family"] == "CIPO_CANADIAN_TRADEMARK"
        )
        self.assertFalse(cipo["absence_coverage_proven"])
        self.assertEqual(cipo["state_counts"]["PRESENT"], 12)
        self.assertEqual(
            cipo["state_counts"]["ABSENT_WITH_PROVEN_COVERAGE"],
            0,
        )
        self.assertEqual(
            cipo["state_counts"]["UNKNOWN_UNVERIFIED_COVERAGE"],
            36,
        )

        for metric in cipo["offset_metrics"]:
            self.assertEqual(metric["entrant_prevalence"]["present"], 2)
            self.assertEqual(metric["entrant_prevalence"]["unknown"], 5)
            self.assertEqual(metric["control_prevalence"]["present"], 1)
            self.assertEqual(metric["control_prevalence"]["unknown"], 4)
            self.assertEqual(
                metric["entrant_prevalence"]["status"],
                "NOT_ESTIMABLE_UNKNOWN_SOURCE_COVERAGE",
            )
            self.assertEqual(
                metric["control_prevalence"]["status"],
                "NOT_ESTIMABLE_UNKNOWN_SOURCE_COVERAGE",
            )
            self.assertEqual(
                metric["error_rates"]["status"],
                "NOT_ESTIMABLE_SOURCE_ABSENCE_UNPROVEN",
            )
            self.assertIsNone(metric["error_rates"]["false_positive_rate"])
            self.assertIsNone(metric["error_rates"]["false_negative_rate"])
            self.assertEqual(metric["source_observable_rows"], 3)
            self.assertEqual(metric["source_total_rows"], 12)
            self.assertEqual(metric["source_observable_fraction"], 0.25)

    def test_cipo_positive_rates_are_explicit_lower_bounds(self):
        cipo = next(
            row for row in self.result["signals"]
            if row["signal_family"] == "CIPO_CANADIAN_TRADEMARK"
        )
        for metric in cipo["offset_metrics"]:
            self.assertEqual(
                metric["entrant_prevalence"]["observed_positive_lower_bound"],
                0.285714,
            )
            self.assertEqual(
                metric["control_prevalence"]["observed_positive_lower_bound"],
                0.2,
            )

    def test_anchor_lead_time_is_not_called_first_operation_lead(self):
        cipo = next(
            row for row in self.result["signals"]
            if row["signal_family"] == "CIPO_CANADIAN_TRADEMARK"
        )
        lead = cipo["anchor_lead_time"]
        self.assertIn("not a verified first-operation", lead["interpretation"])

        entrants = lead["entrants"]
        self.assertEqual(entrants["n"], 2)
        self.assertEqual(entrants["median_days"], 2955.0)
        self.assertEqual(entrants["p25_days"], 2308.5)
        self.assertEqual(entrants["p75_days"], 3601.5)

        controls = lead["controls"]
        self.assertEqual(controls["n"], 1)
        self.assertEqual(controls["median_days"], 1121.0)

    def test_identity_confidence_sensitivity_is_preserved(self):
        cipo = next(
            row for row in self.result["signals"]
            if row["signal_family"] == "CIPO_CANADIAN_TRADEMARK"
        )
        sensitivity = cipo["identity_confidence_sensitivity"]

        high_3 = next(
            row for row in sensitivity
            if row["identity_tier"] == "HIGH" and row["offset_months"] == 3
        )
        self.assertEqual(high_3["entrant_entities"], 4)
        self.assertEqual(high_3["entrant_present"], 2)
        self.assertEqual(high_3["entrant_present_lower_bound"], 0.5)
        self.assertEqual(high_3["control_entities"], 5)
        self.assertEqual(high_3["control_present"], 1)
        self.assertEqual(high_3["control_present_lower_bound"], 0.2)

        eligible_3 = next(
            row for row in sensitivity
            if row["identity_tier"] == "HIGH_OR_MEDIUM"
            and row["offset_months"] == 3
        )
        self.assertEqual(eligible_3["entrant_entities"], 5)
        self.assertEqual(eligible_3["entrant_present"], 2)
        self.assertEqual(eligible_3["entrant_present_lower_bound"], 0.4)

    def test_canadabuys_proves_absence_only_for_identity_eligible_subset(self):
        signal = next(
            row for row in self.result["signals"]
            if row["signal_family"] == "CANADABUYS_AWARD"
        )
        self.assertEqual(signal["state_counts"]["PRESENT"], 0)
        self.assertEqual(
            signal["state_counts"]["ABSENT_WITH_PROVEN_COVERAGE"],
            40,
        )
        self.assertEqual(
            signal["state_counts"]["UNKNOWN_UNVERIFIED_COVERAGE"],
            8,
        )
        self.assertEqual(signal["source_availability"]["observable_rows"], 40)
        self.assertEqual(signal["source_availability"]["observable_fraction"], 0.833333)

        for metric in signal["offset_metrics"]:
            self.assertEqual(metric["entrant_prevalence"]["present"], 0)
            self.assertEqual(
                metric["entrant_prevalence"]["absent_with_proven_coverage"],
                5,
            )
            self.assertEqual(metric["entrant_prevalence"]["unknown"], 2)
            self.assertEqual(metric["control_prevalence"]["present"], 0)
            self.assertEqual(
                metric["control_prevalence"]["absent_with_proven_coverage"],
                5,
            )
            self.assertEqual(metric["control_prevalence"]["unknown"], 0)
            self.assertEqual(metric["source_observable_rows"], 10)
            self.assertEqual(metric["source_total_rows"], 12)
            self.assertEqual(metric["source_observable_fraction"], 0.833333)
            self.assertEqual(
                metric["error_rates"]["status"],
                "NOT_ESTIMABLE_SOURCE_ABSENCE_UNPROVEN",
            )
            self.assertIsNone(metric["error_rates"]["false_positive_rate"])
            self.assertIsNone(metric["error_rates"]["false_negative_rate"])

        high = next(
            row for row in signal["identity_confidence_sensitivity"]
            if row["identity_tier"] == "HIGH" and row["offset_months"] == 3
        )
        self.assertEqual(high["entrant_entities"], 4)
        self.assertEqual(high["entrant_present"], 0)
        self.assertEqual(high["entrant_absent_with_proven_coverage"], 4)
        self.assertEqual(high["entrant_unknown"], 0)
        self.assertEqual(high["control_entities"], 5)
        self.assertEqual(high["control_present"], 0)
        self.assertEqual(high["control_absent_with_proven_coverage"], 5)
        self.assertEqual(high["control_unknown"], 0)
        self.assertEqual(high["false_positive_rate"], 0.0)
        self.assertEqual(high["false_negative_rate"], 1.0)
        self.assertEqual(
            high["error_rate_status"],
            "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET",
        )

        high_or_medium = next(
            row for row in signal["identity_confidence_sensitivity"]
            if row["identity_tier"] == "HIGH_OR_MEDIUM"
            and row["offset_months"] == 3
        )
        self.assertEqual(high_or_medium["entrant_entities"], 5)
        self.assertEqual(
            high_or_medium["entrant_absent_with_proven_coverage"],
            5,
        )
        self.assertEqual(high_or_medium["false_positive_rate"], 0.0)
        self.assertEqual(high_or_medium["false_negative_rate"], 1.0)

    def test_still_unverified_signal_families_remain_unknown(self):
        for signal in self.result["signals"]:
            if signal["signal_family"] in {
                "CIPO_CANADIAN_TRADEMARK",
                "CANADABUYS_AWARD",
            }:
                continue
            self.assertEqual(signal["state_counts"]["PRESENT"], 0)
            self.assertEqual(
                signal["state_counts"]["ABSENT_WITH_PROVEN_COVERAGE"],
                0,
            )
            self.assertEqual(
                signal["state_counts"]["UNKNOWN_UNVERIFIED_COVERAGE"],
                48,
            )
            self.assertEqual(signal["source_availability"]["observable_rows"], 0)
            for metric in signal["offset_metrics"]:
                self.assertEqual(metric["source_observable_rows"], 0)
                self.assertEqual(
                    metric["error_rates"]["status"],
                    "NOT_ESTIMABLE_SOURCE_ABSENCE_UNPROVEN",
                )


if __name__ == "__main__":
    unittest.main()
