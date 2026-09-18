from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from atlanticbridge.db import (
    connect,
    corporations_canada_summary,
    ingest_corporations_canada_snapshot,
)
from atlanticbridge.sources.corporations_canada import iter_active_business_csv


FIXTURE = Path(__file__).parent / "fixtures" / "corporations_canada_sample.csv"


class CorporationsCanadaTests(unittest.TestCase):
    def records(self):
        return list(iter_active_business_csv(FIXTURE, source_url="https://example.test/corp.csv"))

    def test_parser_uses_observed_live_schema(self):
        records = self.records()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].corporation_number, "123456-7")
        self.assertEqual(records[0].city_town, "Halifax")
        self.assertEqual(records[0].province_territory, "Nova Scotia")
        self.assertTrue(records[0].record_hash)

    def test_baseline_creates_no_false_events(self):
        conn = connect(":memory:")
        result = ingest_corporations_canada_snapshot(
            conn,
            self.records(),
            observed_at="2026-09-18T20:00:00+00:00",
            mode="baseline",
        )
        self.assertEqual(result, {"records_staged": 2, "appeared": 0, "changed": 0})
        summary = corporations_canada_summary(conn)
        self.assertEqual(summary["active_records"], 2)
        self.assertEqual(summary["events"], [])

    def test_unchanged_diff_is_quiet(self):
        conn = connect(":memory:")
        ingest_corporations_canada_snapshot(
            conn,
            self.records(),
            observed_at="2026-09-18T20:00:00+00:00",
            mode="baseline",
        )
        result = ingest_corporations_canada_snapshot(
            conn,
            self.records(),
            observed_at="2026-09-19T20:00:00+00:00",
            mode="diff",
        )
        self.assertEqual(result["appeared"], 0)
        self.assertEqual(result["changed"], 0)

    def test_diff_emits_appeared_and_changed_only(self):
        conn = connect(":memory:")
        records = self.records()
        ingest_corporations_canada_snapshot(
            conn,
            records,
            observed_at="2026-09-18T20:00:00+00:00",
            mode="baseline",
        )

        changed = replace(records[0], city_town="Dartmouth")
        appeared = replace(
            records[1],
            corporation_number="999999-9",
            business_number="111222333RC0001",
            corporate_name_form_1="New European Canada Inc.",
            city_town="Halifax",
            province_territory="Nova Scotia",
        )

        result = ingest_corporations_canada_snapshot(
            conn,
            [changed, records[1], appeared],
            observed_at="2026-09-19T20:00:00+00:00",
            mode="diff",
        )
        self.assertEqual(result["appeared"], 1)
        self.assertEqual(result["changed"], 1)

        events = conn.execute(
            """
            SELECT corporation_number, event_type, changed_fields_json
            FROM corporations_canada_events
            ORDER BY event_type, corporation_number
            """
        ).fetchall()
        self.assertEqual(len(events), 2)

        changed_event = next(row for row in events if row["event_type"] == "CORPORATION_CHANGED")
        self.assertEqual(changed_event["corporation_number"], "123456-7")
        self.assertIn("city_town", json.loads(changed_event["changed_fields_json"]))

        appeared_event = next(row for row in events if row["event_type"] == "CORPORATION_APPEARED")
        self.assertEqual(appeared_event["corporation_number"], "999999-9")

    def test_diff_requires_baseline(self):
        conn = connect(":memory:")
        with self.assertRaisesRegex(ValueError, "requires an existing baseline"):
            ingest_corporations_canada_snapshot(
                conn,
                self.records(),
                observed_at="2026-09-18T20:00:00+00:00",
                mode="diff",
            )


if __name__ == "__main__":
    unittest.main()
