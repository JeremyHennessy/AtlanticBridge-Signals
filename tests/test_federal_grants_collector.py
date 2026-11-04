import json
from urllib.parse import parse_qs, urlsplit
import unittest

from atlanticbridge.sources.federal_grants import (
    FIELDS,
    RECIPIENT_TYPE_CODE,
    RECIPIENT_TYPE_LABEL,
    RESOURCE_ID,
    build_query_url,
    collect_grants_context,
)


def sample_payload(rows=None, total=1, fields=FIELDS, resource_id=RESOURCE_ID):
    return {
        "success": True,
        "result": {
            "resource_id": resource_id,
            "total": total,
            "records": rows if rows is not None else [{
                "_id": 17,
                "ref_number": "REF-17",
                "amendment_number": "0",
                "amendment_date": "2026-06-30",
                "agreement_type": "Contribution",
                "recipient_type": RECIPIENT_TYPE_CODE,
                "recipient_legal_name": "Example Industrial Ltd.",
                "recipient_operating_name": "Example Industrial",
                "recipient_country": "Canada",
                "recipient_province": "Nova Scotia",
                "recipient_city": "Halifax",
                "prog_name_en": "Regional Industrial Support",
                "agreement_number": "AGR-17",
                "agreement_value": "250000.00",
                "foreign_currency_type": None,
                "foreign_currency_value": None,
                "agreement_start_date": "2026-07-01",
                "agreement_end_date": "2027-03-31",
                "coverage": None,
                "naics_identifier": "333",
                "owner_org_title": "Atlantic Canada Opportunities Agency",
                "description_en": "Do not request this free text",
                "postal_code": "B3H 0A1",
            }],
            "fields": [{"id": field, "type": "int" if field == "_id" else "text"} for field in fields],
        },
    }


class FederalGrantsCollectorTests(unittest.TestCase):
    def test_query_is_one_page_exact_for_profit_recipient_and_minimal_fields(self):
        url = build_query_url(" Example Industrial Ltd. ", limit=12)
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["resource_id"], [RESOURCE_ID])
        self.assertEqual(params["limit"], ["12"])
        self.assertEqual(params["sort"], ["amendment_date desc"])
        filters = json.loads(params["filters"][0])
        self.assertEqual(filters, {
            "recipient_legal_name": "Example Industrial Ltd.",
            "recipient_type": RECIPIENT_TYPE_CODE,
        })
        self.assertEqual(params["fields"][0].split(","), list(FIELDS))
        self.assertNotIn("description_en", FIELDS)
        self.assertNotIn("recipient_postal_code", FIELDS)
        self.assertNotIn("coverage", FIELDS)

    def test_collect_preserves_provenance_and_only_allowlisted_fields(self):
        seen = {}

        def fetch(url, timeout):
            seen["url"] = url
            seen["timeout"] = timeout
            return sample_payload(), b'{"bounded":"fixture"}'

        result = collect_grants_context(
            "Example Industrial Ltd.", limit=1, timeout_seconds=10, fetch_json=fetch
        )
        self.assertEqual(result["source"], "canada_federal_grants_contributions")
        self.assertEqual(result["source_license_id"], "ogl-canada")
        self.assertEqual(result["source_update_frequency"], "QUARTERLY")
        self.assertEqual(result["records_matching_exact_recipient"], 1)
        self.assertEqual(result["response_sha256"], __import__("hashlib").sha256(b'{"bounded":"fixture"}').hexdigest())
        self.assertEqual(result["records"][0]["_id"], 17)
        self.assertNotIn("description_en", result["records"][0])
        self.assertNotIn("recipient_postal_code", result["records"][0])
        self.assertNotIn("coverage", result["records"][0])
        self.assertIn("source_attribution", result)
        self.assertIn("Open Government Licence - Canada", result["source_attribution"])
        self.assertEqual(result["requested_recipient_type_code"], RECIPIENT_TYPE_CODE)
        self.assertEqual(result["requested_recipient_type_label"], RECIPIENT_TYPE_LABEL)
        self.assertEqual(seen["timeout"], 10)

    def test_local_exact_identity_and_recipient_type_filter_fails_closed(self):
        rows = sample_payload()["result"]["records"]
        wrong_name = dict(rows[0], recipient_legal_name="Another Industrial Ltd.")
        wrong_type_label = dict(rows[0], recipient_type=RECIPIENT_TYPE_LABEL)
        wrong_type_code = dict(rows[0], recipient_type="I")

        def fetch(url, timeout):
            return sample_payload([rows[0], wrong_name, wrong_type_label, wrong_type_code], total=4), b"{}"

        result = collect_grants_context("Example Industrial Ltd.", fetch_json=fetch)
        self.assertEqual(result["records_matching_exact_recipient"], 1)
        self.assertEqual(result["records_excluded_by_exact_recipient_check"], 3)
        self.assertEqual(len(result["records"]), 1)

    def test_observed_live_record_and_exact_ckan_types(self):
        live_row = {
            "_id": 31480972,
            "ref_number": "064-2024-2025-Q3-00085",
            "recipient_type": "F",
            "recipient_legal_name": "Mediphage Bioceuticals, Inc.",
            "recipient_operating_name": "Mediphage Bioceuticals, Inc.",
            "recipient_country": "Canada",
            "recipient_province": "Ontario",
            "recipient_city": "Toronto",
            "agreement_type": "Contribution",
            "amendment_number": "0",
            "amendment_date": "2025-01-01",
            "prog_name_en": "Industrial Research Assistance Program",
            "agreement_number": "00085",
            "agreement_value": "1000",
            "foreign_currency_type": None,
            "foreign_currency_value": None,
            "agreement_start_date": "2025-01-01",
            "agreement_end_date": "2025-12-31",
            "naics_identifier": "54171",
            "owner_org_title": "National Research Council Canada",
        }

        def fetch(url, timeout):
            params = parse_qs(urlsplit(url).query)
            self.assertEqual(json.loads(params["filters"][0]), {
                "recipient_legal_name": "Mediphage Bioceuticals, Inc.",
                "recipient_type": "F",
            })
            return sample_payload([live_row], total=7), b'{"bounded":"observed-shape"}'

        result = collect_grants_context(
            "Mediphage Bioceuticals, Inc.", limit=1, fetch_json=fetch
        )
        self.assertEqual(result["records_matching_exact_recipient"], 1)
        self.assertTrue(result["api_query_has_more_results"])
        self.assertEqual(result["records"][0]["_id"], 31480972)
        self.assertEqual(result["records"][0]["ref_number"], "064-2024-2025-Q3-00085")
        self.assertEqual(result["records"][0]["recipient_type"], "F")
        self.assertEqual(result["requested_recipient_type_label"], RECIPIENT_TYPE_LABEL)

    def test_rejects_live_schema_type_drift_and_duplicate_columns(self):
        def wrong_type(url, timeout):
            payload = sample_payload()
            payload["result"]["fields"][0]["type"] = "text"
            return payload, b"{}"

        with self.assertRaisesRegex(ValueError, "schema drift"):
            collect_grants_context("Example Industrial Ltd.", fetch_json=wrong_type)

        def duplicate_column(url, timeout):
            payload = sample_payload()
            payload["result"]["fields"].append({"id": "_id", "type": "int"})
            return payload, b"{}"

        with self.assertRaisesRegex(ValueError, "duplicate columns"):
            collect_grants_context("Example Industrial Ltd.", fetch_json=duplicate_column)

    def test_more_results_never_claim_complete_coverage(self):
        row = sample_payload()["result"]["records"][0]

        def fetch(url, timeout):
            return sample_payload([row], total=4), b"{}"

        result = collect_grants_context("Example Industrial Ltd.", limit=1, fetch_json=fetch)
        self.assertTrue(result["api_query_has_more_results"])
        self.assertIn("NOT_AN_ABSENCE_PROOF", result["coverage"])

    def test_rejects_bad_limits_and_schema_drift(self):
        with self.assertRaises(ValueError):
            build_query_url("Example Industrial Ltd.", limit=0)

        def missing_schema(url, timeout):
            return sample_payload(fields=FIELDS[:-1]), b"{}"

        with self.assertRaisesRegex(ValueError, "schema drift"):
            collect_grants_context("Example Industrial Ltd.", fetch_json=missing_schema)

    def test_rejects_inconsistent_counts_and_changed_resource(self):
        row = sample_payload()["result"]["records"][0]

        def inconsistent(url, timeout):
            return sample_payload([row, row], total=1), b"{}"

        with self.assertRaisesRegex(ValueError, "count is inconsistent"):
            collect_grants_context("Example Industrial Ltd.", fetch_json=inconsistent)

        def changed_resource(url, timeout):
            return sample_payload(resource_id="unexpected-resource"), b"{}"

        with self.assertRaisesRegex(ValueError, "resource ID changed"):
            collect_grants_context("Example Industrial Ltd.", fetch_json=changed_resource)


if __name__ == "__main__":
    unittest.main()
