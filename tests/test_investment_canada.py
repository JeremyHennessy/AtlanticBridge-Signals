from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import MagicMock, patch

from atlanticbridge.constants import is_eu27_country, normalize_country
from atlanticbridge.db import (
    connect,
    insert_investment_canada_records,
    investment_canada_summary,
    replace_investment_canada_history,
)
from atlanticbridge.sources.investment_canada import (
    InvestmentCanadaPageSnapshot,
    fetch_bucket,
    last_page_index,
    parse_index_html,
)


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


    def test_structural_identity_dedupes_bucket_views(self):
        html = """
        <table>
          <tr>
            <th>Date Certification</th><th>Notification Type</th><th>Investor</th>
            <th>Country of Ultimate Control</th><th>Canadian Business</th>
          </tr>
          <tr>
            <td>2024-03</td>
            <td>Notification - new business</td>
            <td>
              <article data-history-node-id="9001">
                <div class="field--name-title"><span>Example Europe GmbH</span></div>
                <span class="locality-element">Berlin</span>
              </article>
            </td>
            <td>Germany</td>
            <td>
              <article data-history-node-id="9101">
                <div class="field--name-title"><span>Example Canada Inc.</span></div>
                <span class="locality-element">Halifax</span>
                <span class="administrative-area-element">NS</span>
              </article>
            </td>
          </tr>
        </table>
        """
        first = parse_index_html(
            html,
            source_url_value="https://example.test/index/e",
            source_bucket="e",
        )[0]
        second = parse_index_html(
            html,
            source_url_value="https://example.test/index/9?page=2",
            source_bucket="9",
            source_page=2,
        )[0]

        self.assertEqual(first.record_id, second.record_id)
        self.assertEqual(first.investor_name, "Example Europe GmbH")
        self.assertEqual(first.investor_node_id, "9001")
        self.assertEqual(first.canadian_business_node_ids, ("9101",))

    def test_same_display_text_different_source_nodes_stays_distinct(self):
        template = """
        <table>
          <tr>
            <th>Date Certification</th><th>Notification Type</th><th>Investor</th>
            <th>Country of Ultimate Control</th><th>Canadian Business</th>
          </tr>
          <tr>
            <td>2024-03</td>
            <td>Notification - new business</td>
            <td><article data-history-node-id="{investor_id}">Same Name GmbH</article></td>
            <td>Germany</td>
            <td><article data-history-node-id="{business_id}">Same Canada Inc.</article></td>
          </tr>
        </table>
        """
        first = parse_index_html(
            template.format(investor_id="1", business_id="11"),
            source_url_value="https://example.test/a",
            source_bucket="a",
        )[0]
        second = parse_index_html(
            template.format(investor_id="2", business_id="12"),
            source_url_value="https://example.test/s",
            source_bucket="s",
        )[0]

        self.assertEqual(first.raw_record_hash, second.raw_record_hash)
        self.assertNotEqual(first.record_id, second.record_id)

    def test_last_page_index_reads_pager(self):
        html = """
        <a href="?page=1">2</a>
        <a href="/index/a?page=17">18</a>
        <a href="?page=4&other=x">5</a>
        """
        self.assertEqual(last_page_index(html), 17)

    def test_history_replacement_removes_legacy_rows_and_is_idempotent(self):
        conn = connect(":memory:")
        legacy = self.records()[0]
        insert_investment_canada_records(
            conn,
            [legacy],
            "2026-09-18T00:00:00+00:00",
        )

        html = """
        <table>
          <tr>
            <th>Date Certification</th><th>Notification Type</th><th>Investor</th>
            <th>Country of Ultimate Control</th><th>Canadian Business</th>
          </tr>
          <tr>
            <td>2024-03</td>
            <td>Notification - new business</td>
            <td>
              <article data-history-node-id="9001">
                <div class="field--name-title"><span>Example Europe GmbH</span></div>
              </article>
            </td>
            <td>Germany</td>
            <td>
              <article data-history-node-id="9101">
                <div class="field--name-title"><span>Example Canada Inc.</span></div>
              </article>
            </td>
          </tr>
        </table>
        """
        record = parse_index_html(
            html,
            source_url_value="https://example.test/index/e",
            source_bucket="e",
        )[0]
        snapshot = InvestmentCanadaPageSnapshot(
            source_url="https://example.test/index/e",
            source_bucket="e",
            source_page=0,
            sha256="abc",
            record_count=1,
        )

        result = replace_investment_canada_history(
            conn,
            [record],
            [snapshot],
            observed_at="2026-09-18T01:00:00+00:00",
        )
        self.assertEqual(result["records_stored"], 1)
        self.assertEqual(
            conn.execute(
                "SELECT record_id FROM investment_canada_notifications"
            ).fetchone()[0],
            record.record_id,
        )

        replace_investment_canada_history(
            conn,
            [record],
            [snapshot],
            observed_at="2026-09-18T02:00:00+00:00",
        )
        row = conn.execute(
            """
            SELECT first_observed_at, last_observed_at
            FROM investment_canada_notifications
            WHERE record_id = ?
            """,
            (record.record_id,),
        ).fetchone()
        self.assertEqual(row["first_observed_at"], "2026-09-18T01:00:00+00:00")
        self.assertEqual(row["last_observed_at"], "2026-09-18T02:00:00+00:00")

    def test_connect_migrates_pre_structured_investment_table(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "legacy.sqlite"
            legacy = sqlite3.connect(path)
            legacy.execute(
                """
                CREATE TABLE investment_canada_notifications (
                    record_id TEXT PRIMARY KEY,
                    certification_month TEXT NOT NULL,
                    notification_type TEXT NOT NULL,
                    investor_text TEXT NOT NULL,
                    country_of_ultimate_control TEXT NOT NULL,
                    canadian_business_text TEXT NOT NULL,
                    is_new_business INTEGER NOT NULL,
                    is_eu27 INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    source_bucket TEXT NOT NULL,
                    raw_record_hash TEXT NOT NULL,
                    first_observed_at TEXT NOT NULL
                )
                """
            )
            legacy.commit()
            legacy.close()

            conn = connect(path)
            columns = {
                row["name"]
                for row in conn.execute(
                    "PRAGMA table_info(investment_canada_notifications)"
                )
            }
            self.assertIn("investor_node_id", columns)
            self.assertIn("canadian_businesses_json", columns)
            self.assertIn("last_observed_at", columns)


if __name__ == "__main__":
    unittest.main()
