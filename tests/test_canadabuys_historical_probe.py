from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_canadabuys_historical.py"
SPEC = importlib.util.spec_from_file_location("probe_canadabuys_historical", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CanadaBuysHistoricalProbeTests(unittest.TestCase):
    def test_normalize_name_is_punctuation_and_case_stable(self):
        self.assertEqual(
            probe.normalize_name("Andriani S.p.A."),
            probe.normalize_name("ANDRIANI SPA"),
        )
        self.assertEqual(
            probe.normalize_name("SENZOMATIC, s.r.o."),
            probe.normalize_name("SENZOMATIC S.R.O."),
        )

    def test_amendment_date_is_conservative_public_clock(self):
        record = SimpleNamespace(
            publication_date="2020-01-10",
            amendment_date="2020-03-04",
            reference_number="x",
        )
        self.assertEqual(
            probe.public_availability_date(record),
            date(2020, 3, 4),
        )

    def test_base_notice_uses_publication_date(self):
        record = SimpleNamespace(
            publication_date="2020-01-10",
            amendment_date="",
            reference_number="x",
        )
        self.assertEqual(
            probe.public_availability_date(record),
            date(2020, 1, 10),
        )

    def test_parse_date_accepts_current_formats(self):
        self.assertEqual(probe.parse_date("2022-08-08"), date(2022, 8, 8))
        self.assertEqual(probe.parse_date("2022/08/08"), date(2022, 8, 8))
        self.assertIsNone(probe.parse_date(""))


if __name__ == "__main__":
    unittest.main()
