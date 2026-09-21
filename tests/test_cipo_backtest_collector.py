from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_backtest_cipo.py"
SPEC = importlib.util.spec_from_file_location("collect_backtest_cipo", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class CIPOBacktestCollectorTests(unittest.TestCase):
    def test_zip_reader_accepts_large_cipo_fields_and_restores_limit(self):
        original_limit = csv.field_size_limit()
        large_comment = "x" * (original_limit + 1024)

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "event.zip"
            csv_text = (
                "Application Number|CIPO Action Code|Action Date|"
                "Additional Information Comment\n"
                f"1234567|42|2020-01-02|{large_comment}\n"
            )
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("TM_Event.txt", csv_text)

            rows = list(collector.iter_zip_rows(archive_path))

        self.assertEqual(len(rows), 1)
        _, row = rows[0]
        self.assertEqual(row["Application Number"], "1234567")
        self.assertEqual(row["CIPO Action Code"], "42")
        self.assertEqual(
            len(row["Additional Information Comment"]),
            len(large_comment),
        )
        self.assertEqual(csv.field_size_limit(), original_limit)


if __name__ == "__main__":
    unittest.main()
