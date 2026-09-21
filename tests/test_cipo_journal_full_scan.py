from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/scan_cipo_journal_shard.py"
SPEC = importlib.util.spec_from_file_location("scan_cipo_journal_shard", SCRIPT)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scanner)


class CIPOJournalFullScanTests(unittest.TestCase):
    def test_alias_contract_adds_only_source_backed_historical_name(self):
        entities = {
            "entities": [
                {
                    "entity_id": "andriani",
                    "exact_aliases": [
                        "Andriani S.p.A.",
                        "ANDRIANI SPA",
                    ],
                    "foreign_signal_identity_eligible": True,
                },
                {
                    "entity_id": "linet",
                    "exact_aliases": ["LINET spol. s.r.o."],
                    "foreign_signal_identity_eligible": True,
                },
            ]
        }
        identities = {
            "cases": [
                {
                    "case_id": "ANDRIANI",
                    "entity_id": "andriani",
                    "expected_applicant": "MOLINO ANDRIANI S.r.l.",
                    "accepted_applicant_aliases": [
                        "Andriani S.p.A.",
                        "MOLINO ANDRIANI S.r.l.",
                    ],
                    "relation":
                        "SOURCE_BACKED_LEGAL_NAME_PREDECESSOR_SAME_COMPANY",
                },
                {
                    "case_id": "LINET",
                    "entity_id": "linet",
                    "expected_applicant": "Linet spol. S.r.o.",
                    "accepted_applicant_aliases": [
                        "LINET spol. s.r.o.",
                    ],
                    "relation": "EXACT_REVIEWED_FOREIGN_LEGAL_ENTITY",
                },
            ]
        }

        aliases, by_entity = scanner.build_alias_contract(
            entities_payload=entities,
            journal_identity_payload=identities,
        )

        self.assertEqual(set(by_entity), {"andriani", "linet"})
        alias_map = {
            (row["entity_id"], scanner.normalize_name(row["alias"])): row
            for row in aliases
        }

        historical = alias_map[
            ("andriani", scanner.normalize_name("MOLINO ANDRIANI S.r.l."))
        ]
        self.assertEqual(
            historical["alias_kind"],
            "HISTORICAL_LEGAL_NAME",
        )
        self.assertEqual(
            historical["provenance"],
            "JOURNAL_IDENTITY_CASE:ANDRIANI",
        )

        current = alias_map[
            ("linet", scanner.normalize_name("LINET spol. s.r.o."))
        ]
        self.assertNotEqual(
            current["alias_kind"],
            "HISTORICAL_LEGAL_NAME",
        )

    def test_unknown_identity_case_is_rejected(self):
        entities = {
            "entities": [
                {
                    "entity_id": "known",
                    "exact_aliases": ["Known Ltd."],
                }
            ]
        }
        identities = {
            "cases": [
                {
                    "case_id": "BAD",
                    "entity_id": "missing",
                    "expected_applicant": "Missing Ltd.",
                    "accepted_applicant_aliases": ["Missing Ltd."],
                    "relation": "EXACT_REVIEWED_FOREIGN_LEGAL_ENTITY",
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "unknown entity"):
            scanner.build_alias_contract(
                entities_payload=entities,
                journal_identity_payload=identities,
            )


if __name__ == "__main__":
    unittest.main()
