from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest

from atlanticbridge.sources.canadabuys import EXPECTED_HEADER


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_backtest_canadabuys.py"
SPEC = importlib.util.spec_from_file_location("collect_backtest_canadabuys", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def _entities():
    return {
        "entities": [
            {
                "entity_id": "entrant:test",
                "role": "ENTRANT",
                "candidate_outcome_id": "candidate",
                "anchor_month": "2020-01",
                "identity_confidence": "HIGH",
                "foreign_signal_identity_eligible": True,
                "exact_aliases": ["Example GmbH"],
            },
            {
                "entity_id": "control:test",
                "role": "CONTROL",
                "candidate_outcome_id": "candidate",
                "anchor_month": "2020-01",
                "identity_confidence": "HIGH",
                "foreign_signal_identity_eligible": True,
                "exact_aliases": ["Other A/S"],
            },
        ]
    }


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_HEADER)
        writer.writeheader()
        for supplied in rows:
            row = {field: "" for field in EXPECTED_HEADER}
            row.update(supplied)
            writer.writerow(row)


class CanadaBuysBacktestCollectorTests(unittest.TestCase):
    def test_exact_supplier_match_and_complete_absence_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all.csv"
            _write_csv(
                path,
                [
                    {
                        "referenceNumber-numeroReference": "REF-1",
                        "amendmentNumber-numeroModification": "000",
                        "publicationDate-datePublication": "2018-01-15",
                        "supplierLegalName-nomLegalFournisseur-eng": "EXAMPLE GMBH",
                        "supplierAddressCountry-fournisseurAdressePays-eng": "DE",
                    }
                ],
            )
            payload = collector.build_payload(
                entities_payload=_entities(),
                source_files=[
                    {
                        "source_id": "synthetic",
                        "url": "https://example.test/all.csv",
                        "coverage_start": "2012-02-03",
                        "coverage_end": "2024-03-31",
                        "path": path,
                        "sha256": "x",
                        "bytes": path.stat().st_size,
                    }
                ],
            )

        self.assertEqual(payload["summary"]["evidence_count"], 1)
        self.assertEqual(payload["records"][0]["entity_id"], "entrant:test")
        self.assertEqual(
            payload["records"][0]["publicly_available_date"],
            "2018-01-15",
        )
        self.assertTrue(all(
            row["coverage_status"] == "COMPLETE_EXACT_ALIAS_HISTORY"
            for row in payload["coverage"]
        ))

    def test_exact_match_without_publication_date_fails_closed_for_absence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all.csv"
            _write_csv(
                path,
                [
                    {
                        "referenceNumber-numeroReference": "REF-2",
                        "amendmentNumber-numeroModification": "000",
                        "supplierLegalName-nomLegalFournisseur-eng": "Other A/S",
                    }
                ],
            )
            payload = collector.build_payload(
                entities_payload=_entities(),
                source_files=[
                    {
                        "source_id": "synthetic",
                        "url": "https://example.test/all.csv",
                        "coverage_start": "2012-02-03",
                        "coverage_end": "2024-03-31",
                        "path": path,
                        "sha256": "x",
                        "bytes": path.stat().st_size,
                    }
                ],
            )

        coverage = {
            row["entity_id"]: row["coverage_status"]
            for row in payload["coverage"]
        }
        self.assertEqual(
            coverage["control:test"],
            "INCOMPLETE_MATCH_PUBLICATION_DATE",
        )
        self.assertEqual(
            coverage["entrant:test"],
            "COMPLETE_EXACT_ALIAS_HISTORY",
        )

    def test_source_coverage_gap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "all.csv"
            _write_csv(path, [])
            with self.assertRaisesRegex(ValueError, "coverage gap"):
                collector.build_payload(
                    entities_payload=_entities(),
                    source_files=[
                        {
                            "source_id": "a",
                            "url": "https://example.test/a.csv",
                            "coverage_start": "2012-02-03",
                            "coverage_end": "2018-12-31",
                            "path": path,
                            "sha256": "x",
                            "bytes": path.stat().st_size,
                        },
                        {
                            "source_id": "b",
                            "url": "https://example.test/b.csv",
                            "coverage_start": "2019-02-01",
                            "coverage_end": "2024-03-31",
                            "path": path,
                            "sha256": "y",
                            "bytes": path.stat().st_size,
                        },
                    ],
                )


if __name__ == "__main__":
    unittest.main()
