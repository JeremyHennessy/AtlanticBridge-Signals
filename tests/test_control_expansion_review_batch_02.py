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
BATCH_01 = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-01.json"
)
BATCH_02 = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-02.json"
)
COHORTS = ROOT / "reviews/outcome_audit/2026-09-20-outcome-cohorts.json"
BASELINE = ROOT / "reviews/control_cohorts/2026-09-20-backtest-controls.json"


class ExpandedControlReviewBatch02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expansion = json.loads(EXPANSION.read_text(encoding="utf-8"))
        cls.batch_01 = json.loads(BATCH_01.read_text(encoding="utf-8"))
        cls.batch_02 = json.loads(BATCH_02.read_text(encoding="utf-8"))
        cls.cohorts = json.loads(COHORTS.read_text(encoding="utf-8"))
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))

    def test_batch_02_reviews_three_exact_queue_entities(self):
        expansion_by_key = {
            row["control_entity_key"]: row
            for row in self.expansion["records"]
        }
        self.assertEqual(self.batch_02["summary"]["records_reviewed"], 3)
        self.assertEqual(
            self.batch_02["summary"][
                "qualified_foreign_operating_legal_entities"
            ],
            3,
        )
        self.assertEqual(
            self.batch_02["summary"][
                "promoted_to_accepted_backtest_controls"
            ],
            0,
        )

        for row in self.batch_02["records"]:
            source = expansion_by_key[row["control_entity_key"]]
            for field in (
                "investor_name",
                "investor_locality",
                "ultimate_control_country",
                "assigned_candidate_outcome_ids",
            ):
                self.assertEqual(row[field], source[field])
            self.assertEqual(
                row["investor_node_id"],
                source["control_entity_key"].removeprefix("node:"),
            )
            self.assertEqual(
                row["review_decision"],
                "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY",
            )
            self.assertEqual(row["identity_confidence"], "HIGH")
            self.assertTrue(row["foreign_legal_name"])
            self.assertTrue(row["foreign_legal_identifier"]["value"])
            self.assertGreaterEqual(len(row["identity_evidence"]), 3)
            self.assertFalse(row["accepted_backtest_control_eligible"])
            self.assertFalse(row["negative_label_eligible"])

    def test_batch_02_does_not_re_review_batch_01(self):
        batch_01_keys = {
            row["control_entity_key"]
            for row in self.batch_01["records"]
        }
        batch_02_keys = {
            row["control_entity_key"]
            for row in self.batch_02["records"]
        }
        self.assertTrue(batch_01_keys.isdisjoint(batch_02_keys))
        self.assertEqual(len(batch_01_keys | batch_02_keys), 9)

    def test_each_later_entry_is_after_original_24_month_horizon(self):
        cohort_by_id = {
            row["outcome_record_id"]: row
            for row in self.cohorts["cases"]
        }
        for row in self.batch_02["records"]:
            self.assertEqual(len(row["assigned_candidate_outcome_ids"]), 1)
            candidate_id = row["assigned_candidate_outcome_ids"][0]
            candidate = cohort_by_id[candidate_id]
            self.assertEqual(candidate["cohort"], "TRUE_NEW_ENTRY_CANDIDATE")
            horizon_end = add_months(candidate["notification_month"], 24)
            self.assertGreater(row["later_new_business_month"], horizon_end)

    def test_accepted_five_control_baseline_remains_unchanged(self):
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
            for row in self.batch_02["records"]
        }
        self.assertTrue(accepted_keys.isdisjoint(reviewed_keys))


if __name__ == "__main__":
    unittest.main()
