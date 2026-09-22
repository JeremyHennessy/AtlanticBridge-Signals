from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.expanded_control_cipo import (
    build_reviewed_entity_contract,
    scanner_entities_payload,
)


ROOT = Path(__file__).resolve().parents[1]
BATCH_01 = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-01.json"
)
BATCH_02 = (
    ROOT
    / "reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-02.json"
)


class ExpandedControlCIPOTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.batch_01 = json.loads(BATCH_01.read_text(encoding="utf-8"))
        cls.batch_02 = json.loads(BATCH_02.read_text(encoding="utf-8"))
        cls.contract = build_reviewed_entity_contract(
            [cls.batch_01, cls.batch_02]
        )

    def test_review_contract_contains_exactly_nine_high_identities(self):
        self.assertEqual(self.contract["entity_count"], 9)
        self.assertEqual(len(self.contract["entities"]), 9)
        self.assertTrue(all(
            row["identity_confidence"] == "HIGH"
            and row["foreign_signal_identity_eligible"] is True
            for row in self.contract["entities"]
        ))

    def test_rwe_preserves_both_reviewed_legal_spellings(self):
        rwe = next(
            row for row in self.contract["entities"]
            if row["entity_id"] == "node:213011"
        )
        self.assertEqual(
            set(rwe["exact_aliases"]),
            {
                "RWE Supply and Trading GmbH",
                "RWE Supply & Trading GmbH",
            },
        )

    def test_other_exact_duplicate_spellings_are_deduplicated(self):
        db = next(
            row for row in self.contract["entities"]
            if row["entity_id"] == "node:213007"
        )
        self.assertEqual(
            db["exact_aliases"],
            ["Deutsche Bahn International Operations GmbH"],
        )

    def test_scanner_payload_does_not_import_backtest_eligibility(self):
        payload = scanner_entities_payload(self.contract)
        self.assertEqual(len(payload["entities"]), 9)
        self.assertTrue(all(
            row["foreign_signal_identity_eligible"] is True
            for row in payload["entities"]
        ))
        self.assertTrue(all(
            "backtest_control_eligible" not in row
            for row in payload["entities"]
        ))


if __name__ == "__main__":
    unittest.main()
