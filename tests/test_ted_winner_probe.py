from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_ted_winner_alias.py"
SPEC = importlib.util.spec_from_file_location("probe_ted_winner_alias", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class TEDWinnerAliasProbeTests(unittest.TestCase):
    def test_normalize_name_is_stable(self):
        self.assertEqual(
            probe.normalize_name("Global Wind Service A/S"),
            probe.normalize_name("GLOBAL WIND SERVICE A/S"),
        )
        self.assertEqual(
            probe.normalize_name("SENZOMATIC, s.r.o."),
            probe.normalize_name("SENZOMATIC S.R.O."),
        )

    def test_query_is_award_winner_bounded(self):
        query = probe.build_query("Andriani S.p.A.")
        self.assertIn("publication-date = (20120203 <> 20230531)", query)
        self.assertIn("winner-selection-status IN (selec-w)", query)
        self.assertIn('winner-name ~ "Andriani S.p.A."', query)
        for notice_type in ("can-standard", "can-social", "can-desg", "can-tran"):
            self.assertIn(notice_type, query)

    def test_query_escapes_quotes(self):
        query = probe.build_query('Example "Quoted" GmbH')
        self.assertIn('winner-name ~ "Example \\"Quoted\\" GmbH"', query)


if __name__ == "__main__":
    unittest.main()
