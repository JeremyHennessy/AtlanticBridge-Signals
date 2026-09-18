from __future__ import annotations

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from atlanticbridge.canadabuys_store import canadabuys_summary, ingest_awards
from atlanticbridge.sources.canadabuys import (
    EXPECTED_HEADER,
    iter_awards_csv,
    normalize_supplier_country,
)


def _row(**overrides):
    row = {field: "" for field in EXPECTED_HEADER}
    row.update(
        {
            "title-titre-eng": "Cloud services",
            "referenceNumber-numeroReference": "MX-TEST-1",
            "amendmentNumber-numeroModification": "000",
            "publicationDate-datePublication": "2026-09-01",
            "contractAwardDate-dateAttributionContrat": "2026-08-15",
            "contractAmount-montantContrat": "100000.00",
            "contractCurrency-contratMonnaie": "CAD",
            "awardStatus-attributionStatut-eng": "Active",
            "unspsc": "81112100",
            "procurementCategory-categorieApprovisionnement": "*SRV",
            "procurementMethod-methodeApprovisionnement-eng":
                "Competitive - Open bidding",
            "supplierLegalName-nomLegalFournisseur-eng": "Example Ireland Ltd",
            "supplierAddressCity-fournisseurAdresseVille-eng": "Dublin",
            "supplierAddressCountry-fournisseurAdressePays-eng": "IE",
            "contractingEntityName-nomEntitContractante-eng": "Government Buyer",
        }
    )
    row.update(overrides)
    return row


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXPECTED_HEADER)
        writer.writeheader()
        writer.writerows(rows)


class CanadaBuysTests(unittest.TestCase):
    def test_country_normalization_handles_codes_and_names(self):
        self.assertEqual(normalize_supplier_country("IE"), "Ireland")
        self.assertEqual(normalize_supplier_country("France"), "France")
        self.assertEqual(normalize_supplier_country("CA"), "Canada")
        self.assertEqual(normalize_supplier_country("USA"), "United States")

    def test_parser_preserves_source_and_eu_flag(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "awards.csv"
            _write_csv(path, [_row()])
            records = list(iter_awards_csv(path, source_url="https://example.test/awards.csv"))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].supplier_country, "Ireland")
        self.assertTrue(records[0].is_eu27_supplier)
        self.assertEqual(records[0].reference_number, "MX-TEST-1")
        self.assertIn("supplierLegalName", records[0].raw_json)

    def test_duplicate_reference_amendment_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "awards.csv"
            _write_csv(path, [_row(), _row()])
            with self.assertRaisesRegex(ValueError, "duplicate"):
                list(iter_awards_csv(path))

    def test_ingest_and_summary_use_current_snapshot(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "awards.csv"
            _write_csv(
                path,
                [
                    _row(),
                    _row(
                        **{
                            "referenceNumber-numeroReference": "MX-TEST-2",
                            "supplierLegalName-nomLegalFournisseur-eng": "Example Canada Inc",
                            "supplierAddressCountry-fournisseurAdressePays-eng": "Canada",
                            "contractAmount-montantContrat": "50000.00",
                        }
                    ),
                ],
            )
            first = list(iter_awards_csv(path))

        result = ingest_awards(
            conn,
            first,
            source_sha256="sha-one",
            source_url="https://example.test/awards.csv",
            source_bytes=123,
            observed_at="2026-09-18T21:00:00+00:00",
        )
        self.assertEqual(result["records"], 2)
        self.assertEqual(result["eu27_supplier_records"], 1)

        summary = canadabuys_summary(conn)
        self.assertEqual(summary["current_records"], 2)
        self.assertEqual(summary["current_eu27_supplier_records"], 1)
        self.assertEqual(summary["eu27_by_country"][0]["country"], "Ireland")
        self.assertEqual(summary["eu27_suppliers"][0]["contract_amount_cad"], "100000.00")


if __name__ == "__main__":
    unittest.main()
