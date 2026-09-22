from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENTITIES = ROOT / "reviews/backtests/2026-09-21-backtest-entities.json"
RECHECK = (
    ROOT
    / "reviews/backtests/2026-09-21-low-confidence-entrant-identity-recheck.json"
)


class LowConfidenceEntrantIdentityRecheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entities = json.loads(ENTITIES.read_text(encoding="utf-8"))
        cls.recheck = json.loads(RECHECK.read_text(encoding="utf-8"))

    def test_recheck_is_fail_closed_and_changes_no_eligibility(self):
        summary = self.recheck["summary"]
        self.assertEqual(summary["records_reviewed"], 2)
        self.assertEqual(
            summary["promoted_to_foreign_signal_identity_eligible"],
            0,
        )
        self.assertEqual(summary["remain_unresolved"], 2)
        self.assertEqual(summary["backtest_entity_eligibility_changes"], 0)

    def test_rechecked_entities_match_current_backtest_state(self):
        entity_index = {
            row["entity_id"]: row
            for row in self.entities["entities"]
        }
        reviewed_ids = set()

        for review in self.recheck["records"]:
            entity_id = review["entity_id"]
            reviewed_ids.add(entity_id)
            self.assertIn(entity_id, entity_index)
            entity = entity_index[entity_id]

            self.assertEqual(
                review["review_status"],
                "UNRESOLVED_INSUFFICIENT_PARENT_LINK",
            )
            self.assertEqual(review["identity_confidence"], "LOW")
            self.assertFalse(review["foreign_signal_identity_eligible"])
            self.assertEqual(entity["identity_confidence"], "LOW")
            self.assertFalse(entity["foreign_signal_identity_eligible"])
            self.assertEqual(
                entity["identity_status"],
                "UNRESOLVED_FOREIGN_PARENT",
            )

        self.assertEqual(
            reviewed_ids,
            {
                "entrant:653b0de34ba760e11f7a193a48b785e9a49b8af7c3c3764be2aa091886b27cc8",
                "entrant:023105d8069075cda3876e597d6c25a0ffb98be017ac01d9786be98a979cd1ed",
            },
        )

    def test_no_review_claims_primary_parent_evidence(self):
        for review in self.recheck["records"]:
            self.assertTrue(review["missing_evidence_required_for_promotion"])
            self.assertFalse(review["foreign_signal_identity_eligible"])
            self.assertGreaterEqual(len(review["identity_evidence"]), 3)


if __name__ == "__main__":
    unittest.main()
