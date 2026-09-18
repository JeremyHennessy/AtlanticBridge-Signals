from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from atlanticbridge.sources.statcan_trade import (
    ANNUAL_CONFIG,
    ANNUAL_HEADER,
    MONTHLY_CONFIG,
    MONTHLY_HEADER,
    StatCanDownload,
    iter_filtered_records,
)
from atlanticbridge.statcan_trade_store import (
    ingest_statcan_snapshot,
    statcan_trade_summary,
)


def _write_archive(
    path: Path,
    *,
    config,
    header: list[str],
    rows: list[dict[str, str]],
) -> None:
    with tempfile.NamedTemporaryFile(
        "w+",
        encoding="utf-8",
        newline="",
        delete=False,
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)
        temp_path = Path(handle.name)

    try:
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(temp_path, arcname=config.data_member)
    finally:
        temp_path.unlink(missing_ok=True)


def _row(header, **values):
    row = {field: "" for field in header}
    row.update(
        {
            "DGUID": "2021A000212",
            "UOM": "Dollars",
            "SCALAR_FACTOR": "thousands",
            "VECTOR": values.get("VECTOR", "v-test"),
            "COORDINATE": "1.1.1",
            "DECIMALS": "1",
        }
    )
    row.update(values)
    return row


class StatCanTradeTests(unittest.TestCase):
    def _monthly_rows(self):
        rows = []
        for geo in ("Canada", "Nova Scotia"):
            for partner in sorted(MONTHLY_CONFIG.target_partners):
                for ref_date, value in (("2025-07", "80"), ("2026-07", "100")):
                    rows.append(
                        _row(
                            MONTHLY_HEADER,
                            REF_DATE=ref_date,
                            GEO=geo,
                            Trade="Import",
                            **{
                                "North American Product Classification System (NAPCS)":
                                    "Total of all merchandise",
                                "Principal trading partners": partner,
                                "VALUE": value,
                                "VECTOR": f"m-{geo}-{partner}-{ref_date}",
                            },
                        )
                    )
        # Decoy rows must not enter the filtered store.
        rows.append(
            _row(
                MONTHLY_HEADER,
                REF_DATE="2026-07",
                GEO="Ontario",
                Trade="Import",
                **{
                    "North American Product Classification System (NAPCS)":
                        "Total of all merchandise",
                    "Principal trading partners": "Germany",
                    "VALUE": "999",
                    "VECTOR": "decoy-geo",
                },
            )
        )
        rows.append(
            _row(
                MONTHLY_HEADER,
                REF_DATE="2026-07",
                GEO="Nova Scotia",
                Trade="Import",
                **{
                    "North American Product Classification System (NAPCS)":
                        "Total of all merchandise",
                    "Principal trading partners": "United States",
                    "VALUE": "999",
                    "VECTOR": "decoy-partner",
                },
            )
        )
        return rows

    def _annual_rows(self):
        rows = []
        for geo in ("Canada", "Nova Scotia"):
            for partner in sorted(ANNUAL_CONFIG.target_partners):
                for ref_date, value in (("2024", "100"), ("2025", "150")):
                    rows.append(
                        _row(
                            ANNUAL_HEADER,
                            REF_DATE=ref_date,
                            GEO=geo,
                            Trade="Export",
                            **{
                                "Trading partner": partner,
                                "North American Product Classification System (NAPCS)":
                                    "All sections",
                                "VALUE": value,
                                "VECTOR": f"a-{geo}-{partner}-{ref_date}",
                            },
                        )
                    )
        return rows

    def _download(self, path: Path, config) -> StatCanDownload:
        return StatCanDownload(
            config=config,
            archive_path=path,
            download_url=f"https://example.test/{config.pid}.zip",
            archive_sha256=f"sha-{config.pid}",
            archive_bytes=path.stat().st_size,
        )

    def test_filters_target_geography_and_partners(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "monthly.zip"
            _write_archive(
                path,
                config=MONTHLY_CONFIG,
                header=MONTHLY_HEADER,
                rows=self._monthly_rows(),
            )
            records = list(
                iter_filtered_records(self._download(path, MONTHLY_CONFIG))
            )
            self.assertEqual(
                len(records),
                2 * len(MONTHLY_CONFIG.target_partners) * 2,
            )
            self.assertEqual({r.geo for r in records}, {"Canada", "Nova Scotia"})
            self.assertEqual(
                {r.partner for r in records},
                set(MONTHLY_CONFIG.target_partners),
            )

    def test_schema_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.zip"
            _write_archive(
                path,
                config=MONTHLY_CONFIG,
                header=["unexpected"],
                rows=[{"unexpected": "value"}],
            )
            with self.assertRaisesRegex(ValueError, "schema changed"):
                list(iter_filtered_records(self._download(path, MONTHLY_CONFIG)))

    def test_ingest_and_summary_keep_cadences_separate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            monthly_path = Path(temp_dir) / "monthly.zip"
            annual_path = Path(temp_dir) / "annual.zip"
            _write_archive(
                monthly_path,
                config=MONTHLY_CONFIG,
                header=MONTHLY_HEADER,
                rows=self._monthly_rows(),
            )
            _write_archive(
                annual_path,
                config=ANNUAL_CONFIG,
                header=ANNUAL_HEADER,
                rows=self._annual_rows(),
            )

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row

            monthly_download = self._download(monthly_path, MONTHLY_CONFIG)
            annual_download = self._download(annual_path, ANNUAL_CONFIG)

            monthly = ingest_statcan_snapshot(
                conn,
                monthly_download,
                iter_filtered_records(monthly_download),
                observed_at="2026-09-18T22:00:00+00:00",
            )
            annual = ingest_statcan_snapshot(
                conn,
                annual_download,
                iter_filtered_records(annual_download),
                observed_at="2026-09-18T22:00:00+00:00",
            )

            self.assertEqual(monthly["partner_count"], 6)
            self.assertEqual(annual["partner_count"], 27)
            self.assertEqual(monthly["latest_ref_date"], "2026-07")
            self.assertEqual(annual["latest_ref_date"], "2025")

            summary = statcan_trade_summary(conn)
            self.assertTrue(summary["context_only"])
            self.assertEqual(summary["monthly"]["partner_count"], 6)
            self.assertEqual(summary["annual"]["partner_count"], 27)

            germany = next(
                row
                for row in summary["monthly"]["markets"]
                if row["partner"] == "Germany" and row["trade"] == "Import"
            )
            self.assertEqual(germany["current_value_cad"], "100000")
            self.assertEqual(germany["previous_value_cad"], "80000")
            self.assertEqual(germany["year_over_year_percent"], "25.00")

            austria = next(
                row
                for row in summary["annual"]["markets"]
                if row["partner"] == "Austria" and row["trade"] == "Export"
            )
            self.assertEqual(austria["year_over_year_percent"], "50.00")

    def test_snapshot_replacement_removes_stale_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "monthly.zip"
            _write_archive(
                path,
                config=MONTHLY_CONFIG,
                header=MONTHLY_HEADER,
                rows=self._monthly_rows(),
            )
            download = self._download(path, MONTHLY_CONFIG)

            conn = sqlite3.connect(":memory:")
            conn.row_factory = sqlite3.Row
            ingest_statcan_snapshot(
                conn,
                download,
                iter_filtered_records(download),
                observed_at="2026-09-18T22:00:00+00:00",
            )
            first_count = conn.execute(
                "SELECT COUNT(*) FROM statcan_trade_rows WHERE source_pid = ?",
                (MONTHLY_CONFIG.pid,),
            ).fetchone()[0]

            # Repeat snapshot must not duplicate the current source state.
            ingest_statcan_snapshot(
                conn,
                download,
                iter_filtered_records(download),
                observed_at="2026-09-18T22:05:00+00:00",
            )
            second_count = conn.execute(
                "SELECT COUNT(*) FROM statcan_trade_rows WHERE source_pid = ?",
                (MONTHLY_CONFIG.pid,),
            ).fetchone()[0]
            self.assertEqual(first_count, second_count)


if __name__ == "__main__":
    unittest.main()
