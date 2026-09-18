from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from atlanticbridge.cipo_store import (
    cipo_summary,
    persist_detail,
    persist_owner_search,
)
from atlanticbridge.sources.cipo import (
    CIPOIncompleteSearch,
    CIPOOwnerSearchResult,
    CIPOResultCapExceeded,
    CIPOSearchRecord,
    CIPOSession,
    MAX_RETURN,
    normalize_owner_name,
    parse_detail_html,
)


FIXTURE = Path(__file__).parent / "fixtures" / "cipo_detail_sample.html"


def _search_record(record_id: str = "2319647") -> CIPOSearchRecord:
    payload = {
        "id": record_id,
        "appNo": record_id,
        "intlRegNos": ["1783639"],
        "markName": "Depot360",
        "niceCodes": [9, 35, 36, 37, 39, 42],
        "statusCode": 12,
        "statusDesc": "REGISTERED",
        "type": "Standard Characters",
        "st13ApplicationNumber": None,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return CIPOSearchRecord(
        record_id=record_id,
        application_number=record_id,
        international_registration_numbers=("1783639",),
        mark_name="Depot360",
        nice_codes=(9, 35, 36, 37, 39, 42),
        status_code="12",
        status_description="REGISTERED",
        mark_type="Standard Characters",
        st13_application_number="",
        raw_json=raw,
    )


def _search_result() -> CIPOOwnerSearchResult:
    record = _search_record()
    return CIPOOwnerSearchResult(
        owner_query="Siemens Aktiengesellschaft",
        normalized_owner_query=normalize_owner_name("Siemens Aktiengesellschaft"),
        request_payload_json=json.dumps(
            {
                "searchfield1": "ownname",
                "textfield1": "Siemens Aktiengesellschaft",
                "maxReturn": str(MAX_RETURN),
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        num_found=1,
        num_returned=1,
        response_hash="response-hash",
        records=(record,),
    )


class CIPOSearchTests(unittest.TestCase):
    def test_owner_normalization(self):
        self.assertEqual(
            normalize_owner_name("Siemens Aktiengesellschaft"),
            "siemensaktiengesellschaft",
        )
        self.assertEqual(
            normalize_owner_name("Société Exemple S.A."),
            "societeexemplesa",
        )

    def test_detail_parser_extracts_signal_fields(self):
        detail = parse_detail_html(
            FIXTURE.read_text(encoding="utf-8"),
            record_id="2319647",
            detail_url="https://example.test/2319647",
        )
        self.assertEqual(detail.application_number, "2319647")
        self.assertEqual(detail.filed_date, "2024-02-06")
        self.assertEqual(detail.registered_date, "2026-05-08")
        self.assertEqual(detail.owner_name, "Siemens Aktiengesellschaft")
        self.assertEqual(detail.owner_label, "Registered Owner")
        self.assertEqual(detail.match_status("Siemens Aktiengesellschaft"), "EXACT_DETAIL_OWNER")
        self.assertEqual(detail.match_status("Another Company"), "DETAIL_OWNER_MISMATCH")
        self.assertIn("EUIPO", detail.priority_claims[0])
        self.assertEqual(detail.action_history[0]["Action"], "Filed")

    def test_search_fails_closed_above_result_cap(self):
        session = CIPOSession()
        session.initialize = MagicMock()
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = json.dumps(
            {
                "numFound": MAX_RETURN + 1,
                "numReturned": MAX_RETURN,
                "docs": [{"id": str(i)} for i in range(MAX_RETURN)],
            }
        ).encode("utf-8")
        session._open = MagicMock(return_value=response)

        with self.assertRaises(CIPOResultCapExceeded):
            session.search_owner("Too Broad Owner")

    def test_search_rejects_partial_response_below_cap(self):
        session = CIPOSession()
        session.initialize = MagicMock()
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.headers.get_content_type.return_value = "application/json"
        response.read.return_value = json.dumps(
            {
                "numFound": 2,
                "numReturned": 1,
                "docs": [{"id": "1"}],
            }
        ).encode("utf-8")
        session._open = MagicMock(return_value=response)

        with self.assertRaises(CIPOIncompleteSearch):
            session.search_owner("Partial Owner")

    def test_store_tracks_search_and_detail_separately(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        search = _search_result()
        run_id = persist_owner_search(
            conn,
            search,
            observed_at="2026-09-18T21:00:00+00:00",
        )
        detail = parse_detail_html(
            FIXTURE.read_text(encoding="utf-8"),
            record_id="2319647",
            detail_url="https://example.test/2319647",
        )
        status = persist_detail(
            conn,
            search_run_id=run_id,
            owner_query=search.owner_query,
            detail=detail,
            observed_at="2026-09-18T21:01:00+00:00",
        )
        self.assertEqual(status, "EXACT_DETAIL_OWNER")

        summary = cipo_summary(conn)
        self.assertEqual(summary["search_runs"], 1)
        self.assertEqual(summary["search_records"], 1)
        self.assertEqual(summary["details"], 1)
        self.assertEqual(summary["exact_detail_owner_matches"], 1)


if __name__ == "__main__":
    unittest.main()
