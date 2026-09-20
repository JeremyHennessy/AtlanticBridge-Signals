import json
from pathlib import Path
import unittest

from atlanticbridge.outcome_evidence import (
    enforce_model_eligibility_publication_gate,
    evidence_publication_status,
    summarize_outcome_publication_gate,
)


class OutcomeEvidencePublicationGateTests(unittest.TestCase):
    def test_explicit_day_before_notification_is_verified(self):
        evidence = {
            "source_date": "2024-05-01",
            "event_date": "2024-05-01",
            "publicly_available_date": "2024-05-01",
            "publicly_available_date_precision": "DAY",
        }
        self.assertEqual(
            evidence_publication_status(evidence, "2024-06"),
            "VERIFIED_BEFORE_NOTIFICATION_MONTH",
        )

    def test_source_and_event_dates_do_not_substitute_for_public_availability(self):
        evidence = {
            "source_date": "2020-01-01",
            "source_date_basis": "Publication date shown by source",
            "event_date": "2020-01-01",
            "observed_at": "2026-09-20",
        }
        self.assertEqual(
            evidence_publication_status(evidence, "2021-01"),
            "UNVERIFIED",
        )

    def test_same_month_and_after_notification_are_distinct(self):
        self.assertEqual(
            evidence_publication_status(
                {
                    "publicly_available_date": "2024-06-12",
                    "publicly_available_date_precision": "DAY",
                },
                "2024-06",
            ),
            "VERIFIED_DURING_NOTIFICATION_MONTH",
        )
        self.assertEqual(
            evidence_publication_status(
                {
                    "publicly_available_date": "2024-07",
                    "publicly_available_date_precision": "MONTH",
                },
                "2024-06",
            ),
            "VERIFIED_AFTER_NOTIFICATION_MONTH",
        )

    def test_year_precision_overlapping_notification_fails_closed(self):
        self.assertEqual(
            evidence_publication_status(
                {
                    "publicly_available_date": "2024",
                    "publicly_available_date_precision": "YEAR",
                },
                "2024-06",
            ),
            "OVERLAPS_NOTIFICATION_MONTH",
        )

    def test_summary_tracks_case_level_gate_and_strict_failure(self):
        payload = {
            "cases": [
                {
                    "outcome_record_id": "a",
                    "investor_name": "Example GmbH",
                    "canadian_business_name": "Example Canada Inc.",
                    "notification_month": "2024-06",
                    "model_eligible": True,
                    "additional_evidence": [
                        {
                            "publicly_available_date": "2024-05-20",
                            "publicly_available_date_precision": "DAY",
                        }
                    ],
                },
                {
                    "outcome_record_id": "b",
                    "investor_name": "Other GmbH",
                    "canadian_business_name": "Other Canada Inc.",
                    "notification_month": "2024-06",
                    "model_eligible": True,
                    "additional_evidence": [
                        {
                            "source_date": "2024-01-01",
                            "event_date": "2024-01-01",
                        }
                    ],
                },
            ]
        }
        summary = summarize_outcome_publication_gate(payload)
        self.assertEqual(summary["case_count"], 2)
        self.assertEqual(summary["evidence_record_count"], 2)
        self.assertEqual(
            summary["cases_with_verified_pre_notification_evidence"], 1
        )
        self.assertEqual(len(summary["model_eligibility_violations"]), 1)
        with self.assertRaisesRegex(ValueError, "Other Canada Inc."):
            enforce_model_eligibility_publication_gate(summary)

    def test_strict_gate_accepts_no_current_model_eligible_cases(self):
        summary = summarize_outcome_publication_gate(
            {
                "cases": [
                    {
                        "outcome_record_id": "a",
                        "investor_name": "Example GmbH",
                        "canadian_business_name": "Example Canada Inc.",
                        "notification_month": "2024-06",
                        "model_eligible": False,
                        "additional_evidence": [],
                    }
                ]
            }
        )
        enforce_model_eligibility_publication_gate(summary)


    def test_real_audit_batch01_publication_rows_remain_pinned(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        expected = {
            "https://central1.com/in_the_news/central-1-transforms-the-digital-banking-experience-with-the-launch-of-forge/": "2018-10-29",
            "https://www.sec.gov/Archives/edgar/data/1767198/000176719819000001/xslFormDX01/primary_doc.xml": "2019-02-08",
            "https://www.wi-bo.com/de/Linet/news/news-and-press-releases/2019/New-Subsidiary-in-Canada-will-Share-Clinical-Experience": "2019-10-21",
            "https://mydigitalcreds.ca/2020/06/15/arucc-partners-with-digitary-to-build-the-canadian-national-network-called-mycreds/": "2020-06-15",
            "https://uwaterloo.ca/daily-bulletin/2020-07-03": "2020-07-03",
            "https://www.doingbusinesswithlcbo.com/content/dbwl/en/basepage/home/updates/AnupdateontheLCBOsTorontoRetailServiceCentre.html": "2020-05-20",
            "https://www.doingbusinesswithlcbo.com/content/dbwl/en/basepage/home/updates/supporting-your-transition-to-the-Trillium-facility-update.html": "2021-01-08",
            "https://www.bayer.com/media/en-us/bayer-to-sell-its-environmental-science-professional-business-to-cinven-for-26-billion-us-dollars/": "2022-03-10",
            "https://www.canada.ca/en/health-canada/services/consumer-product-safety/reports-publications/pesticides-pest-management/decisions-updates/special-registration-decision/2024/fosetyl-aluminum.html": "2024-08-29",
            "https://www.itworldcanada.com/article/customer-service-software-firm-topdesk-stakes-canadian-turf/378282": "2015-11-08",
            "https://www.boe.es/borme/dias/2022/06/14/pdfs/BORME-A-2022-112-46.pdf": "2022-06-14",
            "https://fvdrc.com/solutions/membership-updates-for-november-15-2022/": "2022-11-29",
            "https://www.nefco.int/news/sioo-receives-financing-from-nefco/": "2023-06-21",
            "https://help.reebelo.ca/hc/en-us/articles/20328511773081-What-is-Reebelo": "2023-07-05",
            "https://vaxxinova.com/vaxxinova-bu-aqua-announces-new-rd-and-business-development-director/": "2024-03-04",
        }
        matched = [
            evidence
            for case in payload["cases"]
            for evidence in case["additional_evidence"]
            if evidence["source_url"] in expected
        ]
        self.assertEqual(len(matched), 16)
        for evidence in matched:
            self.assertEqual(
                evidence["publicly_available_date"],
                expected[evidence["source_url"]],
            )
            self.assertEqual(
                evidence["publicly_available_date_precision"], "DAY"
            )


    def test_real_audit_batch02_uses_cipo_advertised_dates_not_filing_dates(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        by_url = {
            evidence["source_url"]: evidence
            for case in payload["cases"]
            for evidence in case["additional_evidence"]
            if evidence["source_url"].startswith(
                "https://ised-isde.canada.ca/cipo/trademark-search/"
            )
        }
        expected = {
            "https://ised-isde.canada.ca/cipo/trademark-search/1022072": "2002-03-13",
            "https://ised-isde.canada.ca/cipo/trademark-search/1799092": "2018-12-12",
            "https://ised-isde.canada.ca/cipo/trademark-search/2233219": "2024-05-22",
            "https://ised-isde.canada.ca/cipo/trademark-search/2198269": "2024-03-27",
            "https://ised-isde.canada.ca/cipo/trademark-search/1912733": "2021-05-05",
        }
        self.assertTrue(set(expected).issubset(by_url))
        for url, advertised in expected.items():
            self.assertEqual(by_url[url]["publicly_available_date"], advertised)
            self.assertEqual(
                by_url[url]["publicly_available_date_precision"], "DAY"
            )
            self.assertIn("Advertised", by_url[url]["publicly_available_date_basis"])

        tiandingfeng = by_url[
            "https://ised-isde.canada.ca/cipo/trademark-search/2198269"
        ]
        self.assertEqual(tiandingfeng["source_date"], "2022-07-14")
        self.assertEqual(
            evidence_publication_status(tiandingfeng, "2023-10"),
            "VERIFIED_AFTER_NOTIFICATION_MONTH",
        )


    def test_real_audit_batch03_uses_lobbying_posted_date_not_effective_date(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        case = next(
            case for case in payload["cases"]
            if case["canadian_business_name"] == "Britishvolt Canada Inc."
        )
        registration = next(
            evidence for evidence in case["additional_evidence"]
            if evidence["source_type"] == "OFFICIAL_FEDERAL_LOBBY_REGISTRY"
        )
        communication = next(
            evidence for evidence in case["additional_evidence"]
            if evidence["source_type"] == "OFFICIAL_FEDERAL_LOBBY_COMMUNICATION_REPORT"
        )
        self.assertNotIn("publicly_available_date", registration)
        self.assertEqual(
            evidence_publication_status(registration, "2021-06"),
            "UNVERIFIED",
        )
        self.assertEqual(communication["source_date"], "2021-03-18")
        self.assertEqual(
            communication["publicly_available_date"], "2021-04-08"
        )
        self.assertEqual(
            evidence_publication_status(communication, "2021-06"),
            "VERIFIED_BEFORE_NOTIFICATION_MONTH",
        )
        self.assertEqual(
            communication["supports"],
            "PRE_NOTIFICATION_PUBLIC_FEDERAL_LOBBYING_COMMUNICATION",
        )


    def test_real_audit_batch04_uses_public_council_date_for_topdesk_report(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        case = next(
            case for case in payload["cases"]
            if case["canadian_business_name"] == "TOPdesk Canada Inc."
        )
        evidence = next(
            evidence for evidence in case["additional_evidence"]
            if evidence["source_type"] == "OFFICIAL_MUNICIPAL_ANNUAL_REPORT"
        )
        self.assertEqual(evidence["source_date"], "2016-05-09")
        self.assertEqual(evidence["publicly_available_date"], "2016-06-07")
        self.assertEqual(
            evidence["publicly_available_date_precision"], "DAY"
        )
        self.assertIn(
            "City Council agenda",
            evidence["publicly_available_date_basis"],
        )
        self.assertEqual(
            evidence_publication_status(evidence, "2022-07"),
            "VERIFIED_BEFORE_NOTIFICATION_MONTH",
        )


    def test_real_audit_batch05_reviews_every_remaining_row_and_backfills_only_proven_clocks(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        review = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-publication-review-05.json").read_text()
        )
        self.assertEqual(review["summary"]["reviewed_rows"], 28)
        self.assertEqual(review["summary"]["newly_verified_rows"], 6)
        self.assertEqual(review["summary"]["remains_unverified_rows"], 22)

        by_key = {
            (case["canadian_business_name"], evidence["source_type"]): evidence
            for case in payload["cases"]
            for evidence in case["additional_evidence"]
        }
        expected = {
            ("Ocellaris Pharma Inc.", "OFFICIAL_COMPANY_FILING"): "2023-03-28",
            ("Acanthas Pharma Inc.", "OFFICIAL_COMPANY_FILING"): "2023-03-28",
            ("Trillium Supply Chain Inc.", "JUDICIAL_DECISION_TEXT_REPRODUCTION"): "2024-03-28",
            ("Britishvolt Canada Inc.", "INSOLVENCY_ADMINISTRATOR_REPORT"): "2023-03-22",
            ("Tiandingfeng Canada Nonwovens Co., Ltd.", "OFFICIAL_MUNICIPAL_RECORD"): "2025-03-31",
            ("Bolton BG Canada Inc.", "OFFICIAL_GOVERNMENT_EVENT_PAGE"): "2020-03-20",
        }
        for key, available_date in expected.items():
            evidence = by_key[key]
            self.assertEqual(evidence["publicly_available_date"], available_date)
            self.assertEqual(evidence["publicly_available_date_precision"], "DAY")
            self.assertTrue(evidence["publicly_available_date_basis"])

        # Source dates/effective dates that still lack a defensible public clock
        # remain fail-closed rather than being copied into publication fields.
        remains_unverified = [
            row for row in review["rows"]
            if row["review_disposition"] == "REMAINS_UNVERIFIED"
        ]
        for row in remains_unverified:
            case = next(
                case for case in payload["cases"]
                if case["outcome_record_id"] == row["outcome_record_id"]
            )
            evidence = next(
                evidence for evidence in case["additional_evidence"]
                if evidence["source_url"] == row["source_url"]
                and evidence["source_type"] == row["source_type"]
            )
            self.assertNotIn("publicly_available_date", evidence)
            self.assertEqual(
                evidence_publication_status(evidence, case["notification_month"]),
                "UNVERIFIED",
            )

    def test_batch05_bolton_cutoff_is_pre_notification_but_post_event_rows_stay_after(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        by_business = {
            case["canadian_business_name"]: case for case in payload["cases"]
        }
        bolton = next(
            evidence for evidence in by_business["Bolton BG Canada Inc."]["additional_evidence"]
            if evidence["source_type"] == "OFFICIAL_GOVERNMENT_EVENT_PAGE"
        )
        self.assertEqual(
            evidence_publication_status(bolton, "2025-10"),
            "VERIFIED_BEFORE_NOTIFICATION_MONTH",
        )
        britishvolt = next(
            evidence for evidence in by_business["Britishvolt Canada Inc."]["additional_evidence"]
            if evidence["source_type"] == "INSOLVENCY_ADMINISTRATOR_REPORT"
        )
        self.assertEqual(
            evidence_publication_status(britishvolt, "2021-06"),
            "VERIFIED_AFTER_NOTIFICATION_MONTH",
        )


if __name__ == "__main__":
    unittest.main()
