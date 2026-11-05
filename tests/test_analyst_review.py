from __future__ import annotations

import json
from pathlib import Path
import unittest

from atlanticbridge.analyst_review import build_review_packet


FIXTURE = "INJECTED_FETCHER_FIXTURE_OR_REPLAY"
RETRIEVED = "2026-11-03T12:00:00+00:00"


def _collection(source: str, record: dict, **extra) -> dict:
    return {
        "source": source,
        "collection_execution": FIXTURE,
        "retrieved_at": RETRIEVED,
        "coverage": "SYNTHETIC_FIXTURE_ONLY",
        "dataset_url": {
            "bodacc_commercial_notices": "https://www.data.gouv.fr/datasets/bodacc",
            "canada_federal_grants_contributions": "https://open.canada.ca/data/en/dataset/example",
            "nova_scotia_awarded_public_tenders": (
                "https://data.novascotia.ca/Procurement-and-Contracts/"
                "Awarded-Public-Tenders/m6ps-8j6u"
            ),
        }[source],
        "api_url": {
            "bodacc_commercial_notices": "https://bodacc-datadila.opendatasoft.com/api/query",
            "canada_federal_grants_contributions": "https://open.canada.ca/data/api/3/action/datastore_search",
            "nova_scotia_awarded_public_tenders": "https://data.novascotia.ca/resource/m6ps-8j6u.json",
        }[source],
        "records": [record],
        **extra,
    }


class AnalystReviewPacketTests(unittest.TestCase):
    def test_three_sources_are_context_only_with_provenance_and_limits(self):
        collections = [
            _collection("bodacc_commercial_notices", {
                "record_id": "SYNTHETIC-BODACC-1",
                "siren": "123456789",
                "notice_family_label": "Synthetic notice",
                "notice_type": "Synthetic type",
                "publication_date": "2026-11-02",
                "bulletin_edition": "BULLETIN_FIXTURE",
                "official_notice_url": (
                    "https://www.bodacc.fr/pages/annonces-commerciales-detail/"
                    "?q.id=id:SYNTHETIC-BODACC-1"
                ),
            }),
            _collection("canada_federal_grants_contributions", {
                "_id": 123,
                "ref_number": "SYNTHETIC-GRANT-1",
                "recipient_legal_name": "Example Recipient Inc. (invented)",
                "agreement_type": "Synthetic contribution",
                "amendment_date": "2026-10-01",
                "agreement_start_date": "2026-01-01",
                "agreement_end_date": "2026-12-31",
                "agreement_value": "1000.00",
                "prog_name_en": "Synthetic program",
                "owner_org_title": "Example Department",
                "recipient_province": "Nova Scotia",
                "coverage": {"private": "must not flow through"},
            }),
            _collection("nova_scotia_awarded_public_tenders", {
                "tender_id": "SYNTHETIC-TENDER-1",
                "vendor": "Example Systems Ltd. (invented)",
                "entity": "Example buyer (invented)",
                "awarded_date": "2026-09-20T00:00:00.000",
                "awarded_amount": "125000.00",
                "goods": "Yes",
                "service": "No",
                "construction": "No",
                "private_note": {"do_not_copy": True},
            }),
        ]
        packet = build_review_packet(
            collections, generated_at="2026-11-04T00:00:00Z"
        )
        self.assertEqual(packet["workflow_mode"], "LOCAL_ANALYST_REVIEW_ONLY")
        self.assertFalse(packet["lead_promotion_allowed"])
        self.assertEqual(len(packet["findings"]), 3)
        self.assertEqual(len(packet["collections"]), 3)
        self.assertEqual(
            [finding["expected_identity_filter"] for finding in packet["findings"]],
            [
                "Expected collector filter: exact SIREN query",
                "Expected collector filter: exact recipient legal name",
                "Expected collector filter: normalized exact vendor name",
            ],
        )
        self.assertIn("does not establish", packet["findings"][0]["identity_resolution_limit"])
        self.assertTrue(all(
            finding["identity_match_verification"] == "NOT_VALIDATED_BY_PACKET"
            for finding in packet["findings"]
        ))
        for finding in packet["findings"]:
            self.assertFalse(finding["lead_eligible"])
            self.assertFalse(finding["lead_promotion_allowed"])
            self.assertEqual(finding["independent_verification"], "NOT_INDEPENDENTLY_VERIFIED")
            self.assertEqual(finding["evidence_class"], "FIXTURE_DEMONSTRATION_NOT_LIVE")
            self.assertEqual(finding["retrieved_at"], RETRIEVED)
            self.assertTrue(finding["license"])
            self.assertTrue(finding["attribution"])
            self.assertTrue(finding["event_stage"])
            self.assertTrue(finding["interpretation_limit"])
        serialized = json.dumps(packet)
        self.assertNotIn("must not flow through", serialized)
        self.assertNotIn("do_not_copy", serialized)
        self.assertIn("does not establish", serialized.lower())
        self.assertIn("not expansion", serialized)

    def test_live_collection_origin_is_not_misrepresented_as_independent_review(self):
        collection = _collection(
            "nova_scotia_awarded_public_tenders",
            {"tender_id": "SYNTHETIC-1", "vendor": "Example Inc.", "awarded_date": "invalid"},
            collection_execution="LIVE_HTTP_RESPONSE",
            independent_review_status="INDEPENDENTLY_VERIFIED",
        )
        finding = build_review_packet([collection])["findings"][0]
        self.assertEqual(finding["evidence_class"], "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED")
        self.assertEqual(finding["independent_verification"], "NOT_INDEPENDENTLY_VERIFIED")
        self.assertIsNone(finding["published_date"])
        self.assertEqual(finding["date_scope"], "SOURCE_DATE_UNKNOWN")

    def test_unknown_legacy_origin_is_labeled_unknown_and_unsafe_urls_are_dropped(self):
        collection = _collection(
            "nova_scotia_awarded_public_tenders",
            {
                "tender_id": "SYNTHETIC-2",
                "vendor": "Example Inc.",
                "awarded_date": "2026-09-20",
            },
        )
        collection.pop("collection_execution")
        collection["dataset_url"] = "https://user@data.novascotia.ca:444/private"
        collection["api_url"] = "https://example.org/arbitrary"
        finding = build_review_packet([collection])["findings"][0]
        self.assertEqual(finding["evidence_class"], "LEGACY_ORIGIN_UNVERIFIED")
        self.assertIsNone(finding["source_url"])
        self.assertIsNone(finding["api_query_url"])

    def test_retrieval_and_packet_timestamps_must_be_timezone_aware(self):
        collection = _collection(
            "nova_scotia_awarded_public_tenders",
            {"tender_id": "SYNTHETIC-3", "vendor": "Example Inc."},
        )
        collection["retrieved_at"] = "2026-11-03T12:00:00"
        packet = build_review_packet([collection], generated_at="2026-11-04T00:00:00+00:00")
        self.assertIsNone(packet["collections"][0]["retrieved_at"])
        self.assertIsNone(packet["findings"][0]["retrieved_at"])
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            build_review_packet([], generated_at="2026-11-04T00:00:00")

    def test_unsupported_sources_and_missing_stable_identifiers_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "not approved"):
            build_review_packet([{"source": "canada_business_registries", "records": []}])
        with self.assertRaisesRegex(ValueError, "stable source identifier"):
            build_review_packet([_collection(
                "nova_scotia_awarded_public_tenders",
                {"vendor": "Example Inc."},
            )])

    def test_requested_identity_criteria_are_carried_for_manual_comparison(self):
        collections = [
            _collection(
                "bodacc_commercial_notices",
                {
                    "record_id": "SYNTHETIC-QUERY-BODACC",
                    "siren": "123456789",
                },
                requested_siren="123456789",
            ),
            _collection(
                "canada_federal_grants_contributions",
                {"_id": 91, "recipient_legal_name": "Example Recipient Inc."},
                requested_recipient_legal_name="Example Recipient Inc.",
                requested_recipient_type_code="F",
            ),
            _collection(
                "nova_scotia_awarded_public_tenders",
                {"tender_id": "SYNTHETIC-QUERY-NS", "vendor": "Example Vendor Inc."},
                requested_vendor_legal_name="Example Vendor Inc.",
            ),
        ]
        findings = build_review_packet(collections)["findings"]
        self.assertEqual(
            [finding["requested_identity_criterion"] for finding in findings],
            [
                "SIREN: 123456789",
                "Recipient legal name (recipient type F): Example Recipient Inc.",
                "Vendor name: Example Vendor Inc.",
            ],
        )

    def test_identity_claims_remain_unverified_for_contradictory_or_legacy_records(self):
        contradictory = _collection(
            "nova_scotia_awarded_public_tenders",
            {
                "tender_id": "SYNTHETIC-MISMATCH-1",
                "vendor": "Returned Vendor Ltd.",
            },
            requested_vendor_legal_name="Requested Company Ltd.",
        )
        mismatch_finding = build_review_packet([contradictory])["findings"][0]
        self.assertEqual(
            mismatch_finding["expected_identity_filter"],
            "Expected collector filter: normalized exact vendor name",
        )
        self.assertEqual(
            mismatch_finding["identity_match_verification"],
            "NOT_VALIDATED_BY_PACKET",
        )
        self.assertIn("does not compare", mismatch_finding["identity_verification_note"])
        self.assertEqual(
            mismatch_finding["requested_identity_criterion"],
            "Vendor name: Requested Company Ltd.",
        )

        legacy_bodacc = _collection(
            "bodacc_commercial_notices",
            {
                "record_id": "SYNTHETIC-LEGACY-NO-SIREN",
                "notice_family_label": "Synthetic notice",
                "notice_type": "Synthetic type",
            },
            requested_siren="123456789",
        )
        legacy_finding = build_review_packet([legacy_bodacc])["findings"][0]
        self.assertEqual(legacy_finding["entity_label"], "Unresolved French entity")
        self.assertEqual(
            legacy_finding["expected_identity_filter"],
            "Expected collector filter: exact SIREN query",
        )
        self.assertEqual(
            legacy_finding["identity_match_verification"],
            "NOT_VALIDATED_BY_PACKET",
        )
        self.assertEqual(
            legacy_finding["requested_identity_criterion"],
            "SIREN: 123456789",
        )
        legacy_bodacc.pop("requested_siren")
        missing_query_finding = build_review_packet([legacy_bodacc])["findings"][0]
        self.assertEqual(
            missing_query_finding["identity_match_verification"],
            "NOT_VALIDATED_BY_PACKET",
        )
        self.assertIsNone(missing_query_finding["requested_identity_criterion"])

    def test_packet_preserves_source_specific_coverage_and_freshness_signals(self):
        bodacc = _collection(
            "bodacc_commercial_notices",
            {
                "record_id": "SYNTHETIC-COVERAGE-BODACC",
                "siren": "123456789",
                "notice_family_label": "Synthetic notice",
                "notice_type": "Synthetic type",
                "publication_date": "2026-11-02",
                "official_notice_url": (
                    "https://www.bodacc.fr/pages/annonces-commerciales-detail/"
                    "?q.id=id:SYNTHETIC-COVERAGE-BODACC"
                ),
            },
            requested_limit=2,
            total_count_for_query=4,
            records_returned_by_api=2,
            records_matching_exact_siren=1,
            records_excluded_by_exact_siren_check=1,
            api_query_has_more_results=True,
            freshness_note="Synthetic publication-age note.",
        )
        federal = _collection(
            "canada_federal_grants_contributions",
            {"_id": 321, "ref_number": "SYNTHETIC-COVERAGE-GRANT"},
            requested_limit=5,
            total_count_for_exact_query=3,
            records_returned_by_api=2,
            records_matching_exact_recipient=1,
            records_excluded_by_exact_recipient_check=1,
            api_query_has_more_results=True,
            source_update_frequency="QUARTERLY",
        )
        nova_scotia = _collection(
            "nova_scotia_awarded_public_tenders",
            {"tender_id": "SYNTHETIC-COVERAGE-NS", "vendor": "Example Inc."},
            requested_limit=10,
            records_returned_by_api=10,
            records_matching_exact_vendor=9,
            records_excluded_by_exact_vendor_check=1,
            page_may_be_truncated=True,
        )

        summaries = build_review_packet([bodacc, federal, nova_scotia])["collections"]
        b_coverage = summaries[0]["coverage_signals"]
        self.assertEqual(b_coverage["requested_limit"], 2)
        self.assertEqual(b_coverage["total_count_for_query"], 4)
        self.assertEqual(b_coverage["records_returned_by_api"], 2)
        self.assertEqual(b_coverage["records_matching_exact_query"], 1)
        self.assertEqual(b_coverage["records_excluded_by_identity_check"], 1)
        self.assertIs(b_coverage["api_query_has_more_results"], True)
        self.assertIsNone(b_coverage["page_may_be_truncated"])
        self.assertEqual(b_coverage["freshness_note"], "Synthetic publication-age note.")

        f_coverage = summaries[1]["coverage_signals"]
        self.assertEqual(f_coverage["total_count_for_query"], 3)
        self.assertEqual(f_coverage["source_update_frequency"], "QUARTERLY")
        self.assertIs(f_coverage["api_query_has_more_results"], True)

        n_coverage = summaries[2]["coverage_signals"]
        self.assertIsNone(n_coverage["total_count_for_query"])
        self.assertEqual(n_coverage["records_returned_by_api"], 10)
        self.assertEqual(n_coverage["records_matching_exact_query"], 9)
        self.assertEqual(n_coverage["records_excluded_by_identity_check"], 1)
        self.assertIsNone(n_coverage["api_query_has_more_results"])
        self.assertIs(n_coverage["page_may_be_truncated"], True)

    def test_duplicate_rows_and_overlapping_collections_fail_before_packet_output(self):
        row = {
            "tender_id": "SYNTHETIC-DUPLICATE-1",
            "vendor": "Example Systems Ltd. (invented)",
            "awarded_date": "2026-09-20",
        }
        first = _collection("nova_scotia_awarded_public_tenders", row)
        second = _collection("nova_scotia_awarded_public_tenders", dict(row))
        with self.assertRaisesRegex(ValueError, "duplicate finding identifier"):
            build_review_packet([first, second])

        first["records"].append(dict(row))
        with self.assertRaisesRegex(ValueError, "duplicate finding identifier"):
            build_review_packet([first])

    def test_grant_amendment_rows_with_shared_reference_keep_distinct_identity(self):
        collection = _collection(
            "canada_federal_grants_contributions",
            {
                "_id": 31480972,
                "ref_number": "SHARED-AGREEMENT-REF",
                "recipient_legal_name": "Example Inc.",
            },
        )
        collection["records"].append({
            "_id": 31480973,
            "ref_number": "SHARED-AGREEMENT-REF",
            "recipient_legal_name": "Example Inc.",
        })
        findings = build_review_packet([collection])["findings"]
        self.assertEqual(
            [finding["source_record_id"] for finding in findings],
            ["31480972", "31480973"],
        )
        self.assertNotEqual(findings[0]["finding_id"], findings[1]["finding_id"])

    def test_packet_carries_response_hash_only_when_well_formed(self):
        collection = _collection(
            "nova_scotia_awarded_public_tenders",
            {"tender_id": "SYNTHETIC-HASH-1", "vendor": "Example Inc."},
            response_sha256="a" * 64,
        )
        packet = build_review_packet([collection])
        self.assertEqual(packet["collections"][0]["response_sha256"], "a" * 64)
        collection["response_sha256"] = "not-a-sha256"
        packet = build_review_packet([collection])
        self.assertIsNone(packet["collections"][0]["response_sha256"])

    def test_local_ui_has_no_network_or_automatic_storage_and_is_not_publicly_wired(self):
        root = Path(__file__).resolve().parents[1]
        app = (root / "local_analyst_review" / "app.js").read_text(encoding="utf-8")
        page = (root / "local_analyst_review" / "index.html").read_text(encoding="utf-8")
        public_page = (root / "ui" / "index.html").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "localStorage", "sessionStorage"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, app)
        self.assertIn("textContent", app)
        self.assertIn("LOCAL_ANALYST_REVIEW_ONLY", app)
        self.assertNotIn("local_analyst_review", public_page)
        self.assertIn("Open local review packet", page)
        self.assertIn("Opening an official source link performs normal browser navigation", page)

    def test_naive_date_values_are_allowed_only_for_source_event_dates(self):
        packet = build_review_packet([_collection(
            "nova_scotia_awarded_public_tenders",
            {"tender_id": "SYNTHETIC-4", "vendor": "Example Inc.",
             "awarded_date": "2026-09-20T00:00:00"},
        )])
        self.assertTrue(packet["findings"][0]["event_date"].startswith("2026-09-20T00:00:00"))
        self.assertFalse(packet["findings"][0]["lead_eligible"])


if __name__ == "__main__":
    unittest.main()
