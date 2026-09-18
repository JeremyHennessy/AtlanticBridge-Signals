from __future__ import annotations

import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import MagicMock, patch

from atlanticbridge.constants import is_eu27_country, normalize_country
from atlanticbridge.db import (
    connect,
    insert_investment_canada_records,
    investment_canada_summary,
)
from atlanticbridge.sources.investment_canada import fetch_bucket, parse_index_html


FIXTURE = Path(__file__).parent / "fixtures" / "investment_canada_sample.html"


def _response(body: bytes):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.read.return_value = body
    response.headers.get_content_charset.return_value = "utf-8"
    return response


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

    def test_fetch_retries_transient_transport_failure(self):
        first_error = URLError("timed out")
        success = _response(b"<html>ok</html>")

        with (
            patch(
                "atlanticbridge.sources.investment_canada.urlopen",
                side_effect=[first_error, success],
            ) as opener,
            patch("atlanticbridge.sources.investment_canada.time.sleep") as sleep,
        ):
            url, body = fetch_bucket("all", attempts=3, backoff_seconds=0.5)

        self.assertTrue(url.endswith("/all"))
        self.assertEqual(body, "<html>ok</html>")
        self.assertEqual(opener.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_fetch_raises_after_bounded_retries(self):
        failure = URLError("timed out")

        with (
            patch(
                "atlanticbridge.sources.investment_canada.urlopen",
                side_effect=[failure, failure, failure],
            ) as opener,
            patch("atlanticbridge.sources.investment_canada.time.sleep") as sleep,
        ):
            with self.assertRaises(URLError):
                fetch_bucket("all", attempts=3, backoff_seconds=1.0)

        self.assertEqual(opener.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [1.0, 2.0])

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
