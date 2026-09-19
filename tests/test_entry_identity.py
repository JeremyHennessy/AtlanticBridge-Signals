from __future__ import annotations

import json
import sqlite3
import unittest

from atlanticbridge.entry_identity import (
    _city_match,
    _lead_timing,
    _province_match,
    _role_status,
    _unresolved_by_province,
    ensure_entry_identity_schema,
    normalize_legal_name,
)
from atlanticbridge.sources.corporations_canada import (
    detail_corporation_names,
    first_federal_jurisdiction_event,
)


class EntryIdentityTests(unittest.TestCase):
    def test_legal_name_normalization_preserves_word_content(self):
        self.assertEqual(
            normalize_legal_name("Example Canada Inc."),
            "examplecanadainc",
        )
        self.assertEqual(
            normalize_legal_name("Société Énergie S.A."),
            "societeenergiesa",
        )

    def test_geography_matching_is_conservative(self):
        self.assertTrue(_province_match("NS", "Nova Scotia"))
        self.assertTrue(_province_match("Québec", "Quebec"))
        self.assertFalse(_province_match("", "Ontario"))
        self.assertTrue(_city_match("Montréal", "Montreal"))
        self.assertFalse(_city_match("Halifax", "Dartmouth"))

    def test_detail_names_and_jurisdiction_event(self):
        payload = {
            "corporationNames": [
                {
                    "CorporationName": {
                        "name": "Example Canada Inc.",
                        "current": True,
                        "effectiveDate": "2023-01-10",
                    }
                },
                {
                    "CorporationName": {
                        "name": "Old Example Inc.",
                        "current": False,
                        "effectiveDate": "2022-04-01",
                        "expiryDate": "2023-01-10",
                    }
                },
            ],
            "activities": [
                {"activity": {"activity": "Incorporation", "date": "2022-04-01"}},
                {"activity": {"activity": "Amendment", "date": "2023-01-10"}},
            ],
        }
        self.assertEqual(
            detail_corporation_names(payload),
            ("Example Canada Inc.", "Old Example Inc."),
        )
        self.assertEqual(
            first_federal_jurisdiction_event(payload),
            ("Incorporation", "2022-04-01"),
        )

    def test_pre_entry_timing(self):
        status, days = _lead_timing("2024-03", "2023-08-15")
        self.assertEqual(status, "PRE_ENTRY")
        self.assertGreater(days, 180)

        status, days = _lead_timing("2024-03", "2024-03-15")
        self.assertEqual(status, "SAME_MONTH")
        self.assertLess(days, 0)

        self.assertEqual(_lead_timing("2024-03", ""), ("UNKNOWN", None))

    def test_role_status_does_not_call_vehicle_a_foreign_parent(self):
        row = {
            "investor_name": "Example Canada Inc.",
            "canadian_businesses_json": json.dumps(
                [{"name": "Example Canada Inc."}]
            ),
        }
        self.assertEqual(
            _role_status(row, ("Example Canada Inc.",)),
            "CANADIAN_VEHICLE_CONFIRMED",
        )

        distinct = {
            "investor_name": "Example Europe GmbH",
            "canadian_businesses_json": json.dumps(
                [{"name": "Example Canada Inc."}]
            ),
        }
        self.assertEqual(
            _role_status(distinct, ("Example Canada Inc.",)),
            "DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION",
        )


    def test_unresolved_province_queue_preserves_source_geography(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_entry_identity_schema(conn)
        conn.execute(
            """
            INSERT INTO entry_identity_runs (
                run_id, start_month, end_month,
                active_source_sha256, active_source_bytes,
                inactive_source_sha256, inactive_source_bytes,
                cohort_records, detail_limit, gold_limit, observed_at
            ) VALUES (
                'run-1', '2019-01', '2025-12',
                'a', 1, 'b', 2, 3, 3, 3, '2026-09-19T00:00:00Z'
            )
            """
        )

        base = (
            "run-1", "", "2024-01", "Germany", "Investor GmbH", "",
            "", "NO_FEDERAL_EXACT_MATCH", 0, 0, "", "", "", "", "", "",
            0, 0, "NOT_ATTEMPTED", "", 0, "", "{}", "", "", "UNKNOWN",
            None, "UNRESOLVED", 0, 0, "2026-09-19T00:00:00Z"
        )
        rows = [
            (
                base[0], "out-1", base[2], base[3], base[4], base[5],
                json.dumps([{"name":"A","administrative_area":"ON"}]),
                *base[6:]
            ),
            (
                base[0], "out-2", base[2], base[3], base[4], base[5],
                json.dumps([
                    {"name":"B","administrative_area":"QC"},
                    {"name":"B2","administrative_area":"QC"},
                ]),
                *base[6:]
            ),
            (
                base[0], "out-3", base[2], base[3], base[4], base[5],
                "[]",
                *base[6:]
            ),
        ]

        conn.executemany(
            """
            INSERT INTO entry_identity_matches (
                run_id, outcome_record_id, certification_month,
                ultimate_control_country, investor_name, investor_locality,
                source_businesses_json, matched_business_name, match_status,
                candidate_count, geo_candidate_count,
                selected_corporation_number, selected_business_number,
                selected_source_state, selected_corporate_name,
                selected_city, selected_province, city_match, province_match,
                detail_status, detail_source_url, detail_name_match,
                detail_raw_hash, detail_raw_json, federal_event_type,
                federal_event_date, timing_status,
                lead_days_to_outcome_month_start, investor_role_status,
                gold_selected, gold_rank, observed_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            rows,
        )
        queue = _unresolved_by_province(conn, "run-1")
        self.assertEqual(
            queue,
            [
                {"province": "ON", "outcomes": 1},
                {"province": "QC", "outcomes": 1},
                {"province": "UNKNOWN", "outcomes": 1},
            ],
        )


if __name__ == "__main__":
    unittest.main()
