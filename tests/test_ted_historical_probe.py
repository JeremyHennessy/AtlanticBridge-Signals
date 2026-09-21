from __future__ import annotations

from datetime import date
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/probe_ted_historical.py"
SPEC = importlib.util.spec_from_file_location("probe_ted_historical", SCRIPT)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class TEDHistoricalProbeTests(unittest.TestCase):
    def test_normalize_name_is_case_and_punctuation_stable(self):
        self.assertEqual(
            probe.normalize_name("Global Wind Service A/S"),
            probe.normalize_name("GLOBAL WIND SERVICE A/S"),
        )
        self.assertEqual(
            probe.normalize_name("LINET spol. s.r.o."),
            probe.normalize_name("LINET SPOL. S R O"),
        )

    def test_backtest_end_date_is_latest_cutoff_minus_one_day(self):
        payload = {
            "entities": [
                {"anchor_month": "2019-08"},
                {"anchor_month": "2023-09"},
            ]
        }
        self.assertEqual(
            probe.backtest_end_date(payload),
            date(2023, 5, 31),
        )

    def test_coverage_start_is_fixed_to_2012(self):
        self.assertEqual(
            probe.COVERAGE_START_DATE,
            date(2012, 1, 1),
        )


if __name__ == "__main__":
    unittest.main()
