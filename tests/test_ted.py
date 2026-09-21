from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import patch

from atlanticbridge.sources.ted import (
    TEDSearchResult,
    build_award_query,
    build_exact_winner_query,
    build_exact_winner_search_body,
    build_search_body,
    parse_notice,
    search_awards,
    search_awards_exact_winner,
)
from atlanticbridge.ted_store import ingest_ted_search_result, ted_summary


def _single_winner_notice(number: str = "49657-2024") -> dict[str, object]:
    return {
        "publication-number": number,
        "publication-date": "2024-01-25Z",
        "notice-type": "can-standard",
        "notice-title": {
            "eng": "Germany – Food products – Example procurement",
            "deu": "Deutschland – Lebensmittel – Beispiel",
        },
        "title-proc": {"deu": "Example procurement"},
        "classification-cpv": ["15000000"],
        "winner-name": {"deu": ["Prätorius GmbH"]},
        "winner-country": ["DEU"],
        "winner-identifier": ["DE137529444"],
        "winner-decision-date": ["2023-12-29+01:00"],
        "total-value": 20000,
        "total-value-cur": ["EUR"],
        "links": {
            "html": {
                "ENG": "https://ted.europa.eu/en/notice/-/detail/49657-2024"
            }
        },
    }


class TEDTests(unittest.TestCase):
    def test_exact_winner_query_quotes_name_and_date_range(self):
        query = build_exact_winner_query(
            "Global Wind Service A/S",
            "2012-01-01",
            "2023-05-31",
        )
        self.assertIn("publication-date = (20120101 <> 20230531)", query)
        self.assertIn('winner-name = "Global Wind Service A/S"', query)

    def test_exact_winner_query_rejects_unsafe_quote(self):
        with self.assertRaisesRegex(ValueError, "quote/backslash"):
            build_exact_winner_query(
                'Bad "Name"',
                "2012-01-01",
                "2023-05-31",
            )

    def test_exact_winner_search_body_uses_all_scope(self):
        body = build_exact_winner_search_body(
            "Andriani S.p.A.",
            "2012-01-01",
            "2023-05-31",
            page=1,
            page_size=250,
        )
        self.assertEqual(body["scope"], "ALL")
        self.assertFalse(body["onlyLatestVersions"])
        self.assertFalse(body["checkQuerySyntax"])

    @patch("atlanticbridge.sources.ted._post_json")
    def test_exact_winner_search_requires_complete_retrieval(self, post_json):
        post_json.side_effect = [
            {
                "timedOut": False,
                "totalNoticeCount": 3,
                "notices": [
                    _single_winner_notice("A-2024"),
                    _single_winner_notice("B-2024"),
                ],
            },
            {
                "timedOut": False,
                "totalNoticeCount": 3,
                "notices": [_single_winner_notice("C-2024")],
            },
        ]
        result = search_awards_exact_winner(
            "Prätorius GmbH",
            "2024-01-25",
            "2024-01-25",
            page_size=2,
        )
        self.assertEqual(result.total_notice_count, 3)
        self.assertEqual(len(result.notices), 3)
        self.assertEqual(post_json.call_count, 2)

    def test_award_query_same_day_and_range(self):
        same_day = build_award_query("2024-01-25", "2024-01-25")
        self.assertIn("publication-date = 20240125", same_day)
        self.assertIn("winner-selection-status IN (selec-w)", same_day)

        date_range = build_award_query("2024-01-01", "2024-01-31")
        self.assertIn("publication-date = (20240101 <> 20240131)", date_range)

    def test_search_body_disables_syntax_only_mode(self):
        body = build_search_body(
            "2024-01-25",
            "2024-01-25",
            page=1,
            page_size=250,
            scope="ALL",
            only_latest_versions=False,
        )
        self.assertIs(body["checkQuerySyntax"], False)
        self.assertEqual(body["scope"], "ALL")

    def test_single_winner_alignment_is_explicit(self):
        notice = parse_notice(_single_winner_notice())
        mentions = notice.winner_mentions()
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].winner_name, "Prätorius GmbH")
        self.assertEqual(mentions[0].alignment_status, "SINGLE_WINNER_ALIGNED")
        self.assertEqual(mentions[0].winner_country, "DEU")
        self.assertEqual(mentions[0].winner_identifier, "DE137529444")
        self.assertTrue(notice.english_url.endswith("49657-2024"))

    def test_multi_winner_notice_does_not_assume_array_alignment(self):
        payload = _single_winner_notice("MULTI-2024")
        payload["winner-name"] = {
            "eng": ["Company A", "Company B"],
            "deu": ["Company A", "Company B"],
        }
        payload["winner-country"] = ["DEU", "FRA"]
        payload["winner-identifier"] = ["DE-A", "FR-B"]

        mentions = parse_notice(payload).winner_mentions()
        self.assertEqual(len(mentions), 2)
        for mention in mentions:
            self.assertEqual(mention.alignment_status, "NAME_ONLY_UNALIGNED")
            self.assertEqual(mention.winner_country, "")
            self.assertEqual(mention.winner_identifier, "")

    @patch("atlanticbridge.sources.ted._post_json")
    def test_search_paginates_until_total_count(self, post_json):
        post_json.side_effect = [
            {
                "timedOut": False,
                "totalNoticeCount": 3,
                "notices": [
                    _single_winner_notice("A-2024"),
                    _single_winner_notice("B-2024"),
                ],
            },
            {
                "timedOut": False,
                "totalNoticeCount": 3,
                "notices": [_single_winner_notice("C-2024")],
            },
        ]

        result = search_awards(
            "2024-01-25",
            "2024-01-25",
            page_size=2,
            scope="ALL",
        )
        self.assertEqual(result.total_notice_count, 3)
        self.assertEqual(len(result.notices), 3)
        self.assertEqual(post_json.call_count, 2)

    def test_ingest_is_idempotent_and_preserves_alignment(self):
        notice = parse_notice(_single_winner_notice())
        body = build_search_body(
            "2024-01-25",
            "2024-01-25",
            page=1,
            page_size=250,
            scope="ALL",
            only_latest_versions=False,
        )
        import json

        result = TEDSearchResult(
            start_date="2024-01-25",
            end_date="2024-01-25",
            scope="ALL",
            page_size=250,
            only_latest_versions=False,
            query=str(body["query"]),
            query_body_json=json.dumps(
                body,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            total_notice_count=1,
            notices=(notice,),
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        first = ingest_ted_search_result(
            conn,
            result,
            observed_at="2026-09-18T21:00:00+00:00",
        )
        second = ingest_ted_search_result(
            conn,
            result,
            observed_at="2026-09-18T21:05:00+00:00",
        )

        self.assertEqual(first["search_run_id"], second["search_run_id"])
        summary = ted_summary(conn)
        self.assertEqual(summary["search_runs"], 1)
        self.assertEqual(summary["notices"], 1)
        self.assertEqual(summary["winner_mentions"], 1)
        self.assertEqual(summary["aligned_winner_mentions"], 1)
        self.assertEqual(summary["unaligned_winner_mentions"], 0)


if __name__ == "__main__":
    unittest.main()
