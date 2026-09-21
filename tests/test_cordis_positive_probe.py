from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_cordis_canada_relationships.py"
SPEC = importlib.util.spec_from_file_location(
    "probe_cordis_canada_relationships",
    SCRIPT,
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CordisPositiveProbeTests(unittest.TestCase):
    def test_normalize_name_is_stable(self):
        self.assertEqual(
            probe.normalize_name("Global Wind Service A/S"),
            probe.normalize_name("GLOBAL WIND SERVICE A/S"),
        )
        self.assertEqual(
            probe.normalize_name("Sioo Wood Protection Industry AB"),
            probe.normalize_name("SIOO WOOD PROTECTION INDUSTRY AB"),
        )

    def test_alias_index_deduplicates_normalized_aliases(self):
        payload = {
            "entities": [
                {
                    "entity_id": "e",
                    "exact_aliases": [
                        "Andriani S.p.A.",
                        "ANDRIANI SPA",
                    ],
                }
            ]
        }
        index = probe.build_alias_index(payload)
        self.assertEqual(len(index), 1)
        self.assertEqual(next(iter(index.values())), {"e"})


if __name__ == "__main__":
    unittest.main()
