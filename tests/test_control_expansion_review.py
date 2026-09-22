from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.control_identity import add_months


ROOT = Path(__file__).resolve().parents[1]
EXPANSION = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-risk-set-control-expansion.json"
)
BATCH = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-01.json"
)
COHORTS = ROOT / "reviews/outcome_audit/2026-09-20-outcome-cohorts.json"
BASELINE = ROOT / "reviews/control_cohorts/2026-09-20-backtest-controls.json"


class ExpandedControlReviewBatch01Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expansion = json.loads(EXPANSION.read_text(encoding="utf-8"))
        cls.batch = json.loads(BATCH.read_text(encoding="utf-8"))
        cls.cohorts = json.loads(COHORTS.read_text(encoding="utf-8"))
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_expansion_checkpoint_is_complete_and_fail_closed(self):
        summary = self.expansion["summary"]
        self.assertEqual(summary["candidate_count"], 7)
        self.assertEqual(summary["risk_set_candidate_assignments"], 48)
        self.assertEqual(summary["distinct_risk_set_entities"], 48)
        self.assertEqual(summary["identity_unreviewed_assignments"], 48)
        self.assertEqual(summary["backtest_control_eligible_assignments"], 0)
        self.assertEqual(summary["negative_labels_created"], 0)
        self.assertEqual(len(self.expansion["records"]), 48)
        self.assertTrue(all(
            row["identity_qualification_status"] == "UNREVIEWED"
            and row["backtest_control_eligible"] is False
            for row in self.expansion["records"]
        ))

    def test_batch_01_reviews_six_exact_queue_entities(self):
        expansion_by_key = {
            row["control_entity_key"]: row
            for row in self.expansion["records"]
        }
        self.assertEqual(self.batch["summary"]["records_reviewed"], 6)
        self.assertEqual(
            self.batch["summary"]["qualified_foreign_operating_legal_entities"],
            6,
        )
        self.assertEqual(
            self.batch["summary"]["promoted_to_accepted_backtest_controls"],
            0,
        )

        for row in self.batch["records"]:
            source = expansion_by_key[row["control_entity_key"]]
            for field in (
                "investor_node_id",
                "investor_name",
                "investor_locality",
                "ultimate_control_country",
                "assigned_candidate_outcome_ids",
            ):
                self.assertEqual(row[field], source[field])
            self.assertEqual(
                row["review_decision"],
                "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY",
            )
            self.assertEqual(row["identity_confidence"], "HIGH")
            self.assertTrue(row["foreign_legal_name"])
            self.assertTrue(row["foreign_legal_identifier"]["value"])
            self.assertGreaterEqual(len(row["identity_evidence"]), 2)
            self.assertFalse(row["accepted_backtest_control_eligible"])
            self.assertFalse(row["negative_label_eligible"])

    def test_each_later_entry_is_after_original_24_month_horizon(self):
        cohort_by_id = {
            row["outcome_record_id"]: row
            for row in self.cohorts["cases"]
        }
        for row in self.batch["records"]:
            self.assertEqual(len(row["assigned_candidate_outcome_ids"]), 1)
            candidate_id = row["assigned_candidate_outcome_ids"][0]
            candidate = cohort_by_id[candidate_id]
            self.assertEqual(candidate["cohort"], "TRUE_NEW_ENTRY_CANDIDATE")
            horizon_end = add_months(candidate["notification_month"], 24)
            self.assertGreater(row["later_new_business_month"], horizon_end)

    def test_accepted_five_control_baseline_is_unchanged(self):
        self.assertEqual(
            self.baseline["summary"]["distinct_eligible_controls"],
            5,
        )
        accepted_keys = {
            row["control_entity_key"]
            for row in self.baseline["controls"]
        }
        reviewed_keys = {
            row["control_entity_key"]
            for row in self.batch["records"]
        }
        self.assertTrue(accepted_keys.isdisjoint(reviewed_keys))


if __name__ == "__main__":
    unittest.main()
