from __future__ import annotations

import unittest
from pathlib import Path

from atlanticbridge.constants import is_eu27_country, normalize_country
from atlanticbridge.db import (
    connect,
    insert_investment_canada_records,
    investment_canada_summary,
)
from atlanticbridge.sources.investment_canada import parse_index_html


FIXTURE = Path(__file__).parent / "fixtures" / "investment_canada_sample.html"


class InvestmentCanadaParserTests(unittest.TestCase):
    def records(self):
        return parse_index_html(
            FIXTURE.read_text(encoding="utf-8"),
            source_url_value="https://example.test/index/all",
            source_bucket="all",
        )

    def test_parses_expected_rows(self):
        records = self.records()
        self.assertEqual(len(records), 3)
        self.assertEqual(records[0].country_of_ultimate_control, "France")
        self.assertTrue(records[0].is_new_business)
        self.assertTrue(records[0].is_eu27)
        self.assertIn("Montréal, QC", records[0].canadian_business_text)

    def test_eu_country_normalization(self):
        self.assertEqual(normalize_country(" Czech Republic "), "Czechia")
        self.assertTrue(is_eu27_country("Czech Republic"))
        self.assertFalse(is_eu27_country("United Kingdom"))

    def test_ingestion_is_idempotent(self):
        conn = connect(":memory:")
        records = self.records()
        inserted_first = insert_investment_canada_records(conn, records, "2026-09-18T00:00:00+00:00")
        inserted_second = insert_investment_canada_records(conn, records, "2026-09-18T00:01:00+00:00")
        self.assertEqual(inserted_first, 3)
        self.assertEqual(inserted_second, 0)

    def test_summary_separates_eu_new_business(self):
        conn = connect(":memory:")
        insert_investment_canada_records(conn, self.records(), "2026-09-18T00:00:00+00:00")
        summary = investment_canada_summary(conn)
        self.assertEqual(summary["total_records"], 3)
        self.assertEqual(summary["eu27_records"], 2)
        self.assertEqual(summary["eu27_new_business_records"], 1)


if __name__ == "__main__":
    unittest.main()
