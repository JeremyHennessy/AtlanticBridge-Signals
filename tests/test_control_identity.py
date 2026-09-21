from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.control_identity import (
    build_backtest_control_set,
    validate_control_identity_review,
)


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "reviews/control_cohorts/2026-09-20-risk-set-control-identity-review.json"
REVIEW = ROOT / "reviews/control_cohorts/2026-09-20-control-identity-decisions.json"
COHORTS = ROOT / "reviews/outcome_audit/2026-09-20-outcome-cohorts.json"
MANIFEST = ROOT / "reviews/control_cohorts/2026-09-20-risk-set-controls.manifest.json"
BACKTEST = ROOT / "reviews/control_cohorts/2026-09-20-backtest-controls.json"


class ControlIdentityQualificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.queue = json.loads(QUEUE.read_text())
        cls.review = json.loads(REVIEW.read_text())
        cls.cohorts = json.loads(COHORTS.read_text())
        cls.manifest = json.loads(MANIFEST.read_text())

    def test_all_raw_controls_receive_explicit_decision(self):
        summary = validate_control_identity_review(self.queue, self.review)
        self.assertEqual(summary["record_count"], 21)
        self.assertEqual(summary["qualified"], 5)
        self.assertEqual(summary["rejected"], 14)
        self.assertEqual(summary["unresolved"], 2)
        self.assertEqual(summary["backtest_control_eligible"], 5)
        self.assertEqual(summary["negative_labels_created"], 0)

    def test_only_qualified_foreign_operating_entities_are_eligible(self):
        for row in self.review["records"]:
            self.assertEqual(
                row["backtest_control_eligible"],
                row["identity_qualification_status"] == "QUALIFIED",
            )
            self.assertFalse(row["negative_label_eligible"])
            if row["identity_qualification_status"] == "QUALIFIED":
                self.assertEqual(
                    row["entity_classification"],
                    "FOREIGN_OPERATING_LEGAL_ENTITY",
                )
                self.assertTrue(row["foreign_legal_name"])
                self.assertTrue(row["later_new_business_month"])
                self.assertGreaterEqual(len(row["identity_evidence"]), 2)

    def test_known_person_and_canadian_vehicle_rows_are_rejected(self):
        rejected = {
            row["investor_name"]: row
            for row in self.review["records"]
            if row["identity_qualification_status"] == "REJECTED"
        }
        for name in (
            "Dirk Riehle",
            "Emeka Ikwukeme",
            "Gary O'Keeffe",
            "Jake Stenson",
            "Robert Michalak",
        ):
            self.assertEqual(rejected[name]["entity_classification"], "NATURAL_PERSON")
        for name in (
            "Stormont Automatization Canada Inc.",
            "Audi Red Inc.",
            "MountainByte IT Canada Inc.",
            "Piterion Canada Inc.",
            "Azorra Aviation Canada ULC",
            "Data Intellect Services (Canada) Ltd.",
            "Cosmo Consult Inc.",
            "Utopia Gaming Inc.",
            "NUTRONIC NUCLEAR INC.",
        ):
            self.assertEqual(
                rejected[name]["entity_classification"],
                "NAMED_INVESTOR_IS_CANADIAN_VEHICLE",
            )

    def test_unresolved_rows_fail_closed(self):
        unresolved = {
            row["investor_name"]
            for row in self.review["records"]
            if row["identity_qualification_status"] == "UNRESOLVED"
        }
        self.assertEqual(unresolved, {"Doku Asia Limited", "Nothing Technology Inc."})
        self.assertTrue(all(
            not row["backtest_control_eligible"]
            for row in self.review["records"]
            if row["identity_qualification_status"] == "UNRESOLVED"
        ))

    def test_backtest_control_set_is_exact_and_has_no_negative_labels(self):
        generated = build_backtest_control_set(
            queue=self.queue,
            review=self.review,
            cohorts=self.cohorts,
            risk_manifest=self.manifest,
        )
        checked_in = json.loads(BACKTEST.read_text())
        self.assertEqual(generated, checked_in)
        self.assertEqual(generated["summary"]["eligible_control_assignments"], 5)
        self.assertEqual(generated["summary"]["distinct_eligible_controls"], 5)
        self.assertEqual(
            generated["summary"]["candidate_strata_with_eligible_controls"], 3
        )
        self.assertEqual(
            generated["summary"]["candidate_strata_without_eligible_controls"], 4
        )
        self.assertEqual(generated["summary"]["negative_labels_created"], 0)
        self.assertTrue(all(
            row["control_interpretation"] == "TIME_INDEXED_AT_RISK_FUTURE_ENTRANT"
            and row["backtest_control_eligible"]
            and not row["negative_label_eligible"]
            for row in generated["controls"]
        ))

    def test_controls_enter_only_after_the_24_month_risk_horizon(self):
        payload = json.loads(BACKTEST.read_text())
        for row in payload["controls"]:
            self.assertGreater(
                row["later_new_business_month"],
                row["risk_horizon_end_month"],
            )
            self.assertEqual(
                row["observation_coverage_status"],
                "COMPLETE_INVESTMENT_CANADA_RISK_HORIZON",
            )


if __name__ == "__main__":
    unittest.main()
