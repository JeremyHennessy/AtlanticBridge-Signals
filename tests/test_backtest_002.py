from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.backtest_metrics import build_backtest_001
from atlanticbridge.backtest_statistics import (
    build_backtest_002,
    fisher_exact_two_sided,
    wilson_interval,
)


ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "reviews/backtests/2026-09-21-backtest-entities.json"
SEMANTICS = ROOT / "reviews/backtests/2026-09-21-signal-source-semantics.json"
INPUT = ROOT / "reviews/backtests/2026-09-21-backtest-001-input.json"


class Backtest002Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        backtest_001 = build_backtest_001(
            entities_payload=json.loads(ENTITIES.read_text()),
            semantics_payload=json.loads(SEMANTICS.read_text()),
            accepted_input=json.loads(INPUT.read_text()),
        )
        cls.result = build_backtest_002(backtest_001=backtest_001)

    def test_exact_fisher_reference_tables(self):
        self.assertEqual(
            fisher_exact_two_sided(2, 2, 1, 4),
            0.52381,
        )
        self.assertEqual(
            fisher_exact_two_sided(2, 3, 1, 4),
            1.0,
        )

    def test_wilson_reference_intervals(self):
        self.assertEqual(
            wilson_interval(2, 4),
            {
                "successes": 2,
                "total": 4,
                "point_estimate": 0.5,
                "lower_95": 0.150039,
                "upper_95": 0.849961,
            },
        )
        self.assertEqual(
            wilson_interval(1, 5),
            {
                "successes": 1,
                "total": 5,
                "point_estimate": 0.2,
                "lower_95": 0.036224,
                "upper_95": 0.624465,
            },
        )

    def test_only_signal_with_presence_and_proven_absence_is_candidate(self):
        self.assertTrue(self.result["backtest_001_weighting_design_gate"])
        self.assertEqual(self.result["candidate_signal_count"], 1)
        self.assertEqual(
            self.result["signals"][0]["signal_family"],
            "CIPO_CANADIAN_TRADEMARK",
        )

    def test_high_identity_uncertainty_blocks_publication(self):
        rows = self.result["signals"][0]["tested_rows"]
        high = next(
            row for row in rows
            if row["identity_tier"] == "HIGH"
            and row["offset_months"] == 3
        )
        self.assertEqual(high["entrant_positive_rate"]["point_estimate"], 0.5)
        self.assertEqual(high["control_positive_rate"]["point_estimate"], 0.2)
        self.assertEqual(high["risk_difference"]["point_estimate"], 0.3)
        self.assertEqual(high["risk_difference"]["lower_95"], -0.25013)
        self.assertEqual(high["risk_difference"]["upper_95"], 0.686387)
        self.assertEqual(high["fisher_exact_two_sided_p"], 0.52381)
        self.assertFalse(high["directional_discrimination_resolved"])

    def test_high_or_medium_uncertainty_blocks_publication(self):
        rows = self.result["signals"][0]["tested_rows"]
        eligible = next(
            row for row in rows
            if row["identity_tier"] == "HIGH_OR_MEDIUM"
            and row["offset_months"] == 3
        )
        self.assertEqual(
            eligible["entrant_positive_rate"]["point_estimate"],
            0.4,
        )
        self.assertEqual(
            eligible["control_positive_rate"]["point_estimate"],
            0.2,
        )
        self.assertEqual(eligible["risk_difference"]["point_estimate"], 0.2)
        self.assertEqual(eligible["risk_difference"]["lower_95"], -0.309813)
        self.assertEqual(eligible["risk_difference"]["upper_95"], 0.603964)
        self.assertEqual(eligible["fisher_exact_two_sided_p"], 1.0)
        self.assertFalse(eligible["directional_discrimination_resolved"])

    def test_score_publication_fails_closed(self):
        self.assertEqual(self.result["inferentially_resolved_rows"], 0)
        self.assertEqual(
            self.result["publication_gate_mode"],
            "EXPLORATORY_NO_PREDECLARED_PRIMARY_ENDPOINT",
        )
        self.assertFalse(
            self.result["expansion_score_1_0_weight_publication_allowed"]
        )
        self.assertIn(
            "publication remains blocked",
            self.result["score_publication_gate_reason"],
        )

    def test_exploratory_significant_row_cannot_open_publication(self):
        synthetic = {
            "summary": {
                "expansion_score_1_0_weighting_allowed": True,
            },
            "target_boundary": {
                "positive_class": "SYNTHETIC_CENSORED_ANCHOR",
            },
            "signals": [
                {
                    "signal_family": "SYNTHETIC_SIGNAL",
                    "state_counts": {
                        "PRESENT": 10,
                        "ABSENT_WITH_PROVEN_COVERAGE": 10,
                        "UNKNOWN_UNVERIFIED_COVERAGE": 0,
                    },
                    "identity_confidence_sensitivity": [
                        {
                            "identity_tier": "HIGH",
                            "offset_months": 3,
                            "error_rate_status":
                                "ESTIMABLE_FOR_CENSORED_ANCHOR_TARGET",
                            "entrant_unknown": 0,
                            "control_unknown": 0,
                            "entrant_present": 10,
                            "entrant_absent_with_proven_coverage": 0,
                            "control_present": 0,
                            "control_absent_with_proven_coverage": 10,
                        }
                    ],
                }
            ],
        }
        result = build_backtest_002(backtest_001=synthetic)
        self.assertEqual(result["inferentially_resolved_rows"], 1)
        self.assertTrue(
            result["signals"][0]["tested_rows"][0][
                "directional_discrimination_resolved"
            ]
        )
        self.assertFalse(
            result["expansion_score_1_0_weight_publication_allowed"]
        )
        self.assertIn(
            "predeclared primary endpoint",
            result["score_publication_gate_reason"],
        )


if __name__ == "__main__":
    unittest.main()
