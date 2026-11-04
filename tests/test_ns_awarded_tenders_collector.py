import json
from urllib.parse import parse_qs, urlsplit
import unittest

from atlanticbridge.sources.ns_awarded_tenders import (
    FIELDS,
    LICENSE_ID,
    REQUIRED_TYPES,
    build_query_url,
    collect_awarded_tenders_context,
)


# Synthetic fixture only; these tender details are invented test values.
def row(vendor="Example Systems Ltd."):
    return {
        "tender_id": "NS-123",
        "entity": "Department of Public Works",
        "goods": "Yes",
        "service": "No",
        "construction": "No",
        "tender_start_date": "2025-01-01T00:00:00.000",
        "tender_close_date": "2025-02-01T00:00:00.000",
        "awarded_date": "2025-02-10T00:00:00.000",
        "awarded_amount": "125000.00",
        "vendor": vendor,
        "tender_description": "Must not be requested or retained",
    }


class NovaScotiaAwardedTendersTests(unittest.TestCase):
    def test_query_is_bounded_exact_company_filter_and_uses_live_schema_allowlist(self):
        url = build_query_url("Bell Canada", limit=7)
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["$limit"], ["7"])
        self.assertEqual(params["$select"], [",".join(FIELDS)])
        self.assertEqual(params["$where"], ["upper(vendor) = 'BELL CANADA'"])
        self.assertEqual(REQUIRED_TYPES, {
            "tender_id": "text",
            "entity": "text",
            "goods": "text",
            "service": "text",
            "construction": "text",
            "tender_start_date": "calendar_date",
            "tender_close_date": "calendar_date",
            "awarded_date": "calendar_date",
            "awarded_amount": "number",
            "vendor": "text",
        })
        self.assertEqual(set(REQUIRED_TYPES), set(FIELDS))
        self.assertEqual(LICENSE_ID, "OGL_NOVA_SCOTIA")
        self.assertNotIn("tender_description", FIELDS)

    def test_soql_literal_is_escaped(self):
        params = parse_qs(urlsplit(build_query_url("O'Brien Systems Ltd.") ).query)
        self.assertEqual(params["$where"], ["upper(vendor) = 'O''BRIEN SYSTEMS LTD.'"])

    def test_exact_result_has_provenance_and_excludes_free_text(self):
        def fetch(url, timeout):
            return [row()], b'[{"bounded":"fixture"}]'

        result = collect_awarded_tenders_context(
            "Example Systems Ltd.", limit=1, timeout_seconds=5, fetch_json=fetch
        )
        self.assertEqual(result["records_matching_exact_vendor"], 1)
        self.assertEqual(result["records"][0]["awarded_amount"], "125000.00")
        self.assertNotIn("tender_description", result["records"][0])
        self.assertIn("Open Government Licence", result["source_attribution"])
        self.assertEqual(result["source_license_id"], LICENSE_ID)
        self.assertIn("NOT_AN_ABSENCE_PROOF", result["coverage"])
        self.assertEqual(result["page_may_be_truncated"], True)

    def test_local_identity_recheck_and_amount_type_are_fail_closed(self):
        def wrong_name(url, timeout):
            return [row(vendor="Example Systems Limited")], b"[]"

        result = collect_awarded_tenders_context("Example Systems Ltd.", fetch_json=wrong_name)
        self.assertEqual(result["records_matching_exact_vendor"], 0)
        self.assertEqual(result["records_excluded_by_exact_vendor_check"], 1)

        def bad_amount(url, timeout):
            value = row()
            value["awarded_amount"] = []
            return [value], b"[]"

        with self.assertRaisesRegex(ValueError, "amount"):
            collect_awarded_tenders_context("Example Systems Ltd.", fetch_json=bad_amount)

    def test_rejects_invalid_bounds_and_overflow(self):
        with self.assertRaises(ValueError):
            build_query_url("Bell Canada", limit=0)

        def too_many(url, timeout):
            return [row(), row()], b"[]"

        with self.assertRaisesRegex(ValueError, "requested bound"):
            collect_awarded_tenders_context("Example Systems Ltd.", limit=1, fetch_json=too_many)

    def test_rejects_record_schema_drift(self):
        def missing_field(url, timeout):
            value = row()
            value.pop("entity")
            return [value], b"[]"

        with self.assertRaisesRegex(ValueError, "schema changed"):
            collect_awarded_tenders_context("Example Systems Ltd.", fetch_json=missing_field)


if __name__ == "__main__":
    unittest.main()
