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


    def test_real_audit_batch01_publication_cutoffs_are_pinned(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        summary = summarize_outcome_publication_gate(payload)
        self.assertEqual(summary["case_count"], 27)
        self.assertEqual(summary["evidence_record_count"], 50)
        self.assertEqual(
            summary["publication_status_counts"],
            {
                "UNVERIFIED": 34,
                "VERIFIED_AFTER_NOTIFICATION_MONTH": 3,
                "VERIFIED_BEFORE_NOTIFICATION_MONTH": 11,
                "VERIFIED_DURING_NOTIFICATION_MONTH": 2,
            },
        )
        self.assertEqual(
            summary["cases_with_verified_pre_notification_evidence"], 10
        )
        self.assertEqual(summary["model_eligible_cases"], 0)
        self.assertEqual(summary["model_eligibility_violations"], [])

        cipo = next(
            evidence
            for case in payload["cases"]
            if case["canadian_business_name"] == "Tiandingfeng Canada Nonwovens Co., Ltd."
            for evidence in case["additional_evidence"]
            if evidence["source_url"].endswith("/2198269")
        )
        self.assertNotIn("publicly_available_date", cipo)
        self.assertEqual(
            evidence_publication_status(cipo, "2023-10"), "UNVERIFIED"
        )


    def test_real_audit_batch02_uses_cipo_advertised_dates_not_filing_dates(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        summary = summarize_outcome_publication_gate(payload)
        self.assertEqual(
            summary["publication_status_counts"],
            {
                "UNVERIFIED": 29,
                "VERIFIED_AFTER_NOTIFICATION_MONTH": 5,
                "VERIFIED_BEFORE_NOTIFICATION_MONTH": 14,
                "VERIFIED_DURING_NOTIFICATION_MONTH": 2,
            },
        )
        self.assertEqual(
            summary["cases_with_verified_pre_notification_evidence"], 11
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
        self.assertEqual(set(by_url), set(expected))
        for url, advertised in expected.items():
            self.assertEqual(by_url[url]["publicly_available_date"], advertised)
            self.assertEqual(
                by_url[url]["publicly_available_date_precision"], "DAY"
            )
            self.assertIn("Advertised", by_url[url]["publicly_available_date_basis"])

        tiandingfeng = by_url[
            "https://ised-isde.canada.ca/cipo/trademark-search/2198269"
        ]
        self.assertEqual(
            tiandingfeng["source_date"], "2022-07-14"
        )
        self.assertEqual(
            evidence_publication_status(tiandingfeng, "2023-10"),
            "VERIFIED_AFTER_NOTIFICATION_MONTH",
        )


if __name__ == "__main__":
    unittest.main()
