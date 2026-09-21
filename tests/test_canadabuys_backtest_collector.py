from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_backtest_canadabuys.py"
SPEC = importlib.util.spec_from_file_location("probe_canadabuys_historical", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class CanadaBuysBacktestCollectorTests(unittest.TestCase):
    def test_normalize_name_is_punctuation_and_case_stable(self):
        self.assertEqual(
            collector.normalize_name("Andriani S.p.A."),
            collector.normalize_name("ANDRIANI SPA"),
        )
        self.assertEqual(
            collector.normalize_name("SENZOMATIC, s.r.o."),
            collector.normalize_name("SENZOMATIC S.R.O."),
        )

    def test_amendment_date_is_conservative_public_clock(self):
        record = SimpleNamespace(
            publication_date="2020-01-10",
            amendment_date="2020-03-04",
            reference_number="x",
        )
        self.assertEqual(
            collector.public_availability_date(record),
            date(2020, 3, 4),
        )

    def test_base_notice_uses_publication_date(self):
        record = SimpleNamespace(
            publication_date="2020-01-10",
            amendment_date="",
            reference_number="x",
        )
        self.assertEqual(
            collector.public_availability_date(record),
            date(2020, 1, 10),
        )

    def test_parse_date_accepts_current_formats(self):
        self.assertEqual(collector.parse_date("2022-08-08"), date(2022, 8, 8))
        self.assertEqual(collector.parse_date("2022/08/08"), date(2022, 8, 8))
        self.assertIsNone(collector.parse_date(""))


if __name__ == "__main__":
    unittest.main()
