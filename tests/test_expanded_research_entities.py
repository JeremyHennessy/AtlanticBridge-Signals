import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location(
    "build_expanded_research_entities",
    ROOT / "scripts" / "build_expanded_research_entities.py",
)
module = module_from_spec(spec)
spec.loader.exec_module(module)


class ExpandedResearchEntitiesTests(unittest.TestCase):
    def test_checked_in_payload_matches_reviewed_identity_batches(self):
        generated = module.build_payload()
        checked_in = json.loads(
            (ROOT / "reviews/backtests/2026-09-22-expanded-research-entities.json").read_text()
        )
        self.assertEqual(checked_in, generated)

    def test_all_rows_are_identity_qualified_future_entrant_controls(self):
        payload = module.build_payload()
        self.assertEqual(len(payload["entities"]), 9)
        self.assertEqual(len({row["entity_id"] for row in payload["entities"]}), 9)
        for row in payload["entities"]:
            self.assertEqual(row["role"], "CONTROL")
            self.assertEqual(
                row["identity_status"],
                "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY",
            )
            self.assertEqual(row["identity_confidence"], "HIGH")
            self.assertTrue(row["foreign_signal_identity_eligible"])
            self.assertTrue(row["exact_aliases"])
            self.assertGreater(row["later_new_business_month"], row["anchor_month"])


if __name__ == "__main__":
    unittest.main()
