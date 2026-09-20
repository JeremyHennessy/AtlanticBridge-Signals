from __future__ import annotations

import json
import unittest

from atlanticbridge.risk_set_controls import (
    activity_similarity,
    add_months,
    build_risk_set_controls,
    validate_risk_set_controls,
)
from atlanticbridge.sources.investment_canada import InvestmentCanadaRecord


def _record(
    month: str,
    investor: str,
    node: str,
    country: str,
    activity: str,
    *,
    notification_type: str = "Notification - new business",
    business: str | None = None,
) -> InvestmentCanadaRecord:
    business = business or f"{investor} Canada Inc."
    businesses = json.dumps(
        [{
            "node_id": f"b-{node}-{month}",
            "name": business,
            "locality": "Toronto",
            "administrative_area": "ON",
            "activity": activity,
        }],
        separators=(",", ":"),
    )
    return InvestmentCanadaRecord(
        certification_month=month,
        notification_type=notification_type,
        investor_text=investor,
        investor_name=investor,
        investor_locality="Berlin" if country == "Germany" else "Paris",
        investor_node_id=node,
        country_of_ultimate_control=country,
        canadian_business_text=f"{business} Business activity {activity}",
        canadian_businesses_json=businesses,
        canadian_business_node_ids=(f"b-{node}-{month}",),
        source_url=f"https://example.test/{node}/{month}",
        source_bucket="all",
    )


def _payloads(candidate_records):
    cohort_cases = []
    audit_cases = []
    for record in candidate_records:
        business = json.loads(record.canadian_businesses_json)[0]
        cohort_cases.append({
            "outcome_record_id": record.record_id,
            "investor_name": record.investor_name,
            "canadian_business_name": business["name"],
            "notification_month": record.certification_month,
            "cohort": "TRUE_NEW_ENTRY_CANDIDATE",
            "training_positive_eligible": False,
            "censored_candidate_for_matching": True,
        })
        audit_cases.append({
            "outcome_record_id": record.record_id,
            "ultimate_control_country": record.country_of_ultimate_control,
            "canadian_business_activity": business["activity"],
        })
    return {"cases": cohort_cases}, {"cases": audit_cases}


class RiskSetControlTests(unittest.TestCase):
    def setUp(self):
        self.candidate = _record(
            "2020-01",
            "Candidate Software GmbH",
            "cand",
            "Germany",
            "Develops software platforms for banks.",
        )
        self.late_candidate = _record(
            "2025-01",
            "Late Candidate GmbH",
            "late",
            "Germany",
            "Develops industrial software.",
        )
        self.software_control = _record(
            "2022-03",
            "Future Software GmbH",
            "soft",
            "Germany",
            "Provides software platform solutions.",
        )
        self.food_control = _record(
            "2023-01",
            "Future Food GmbH",
            "food",
            "Germany",
            "Imports specialty food products.",
        )
        self.prior_activity = _record(
            "2021-06",
            "Prior Activity GmbH",
            "prior",
            "Germany",
            "Provides software services.",
            notification_type="Notification - acquisition",
        )
        self.prior_activity_future_entry = _record(
            "2023-06",
            "Prior Activity GmbH",
            "prior",
            "Germany",
            "Provides software services.",
        )
        self.france_control = _record(
            "2023-02",
            "Future France SAS",
            "fr",
            "France",
            "Provides software platform services.",
        )
        self.corpus_end = _record(
            "2026-07",
            "Corpus End GmbH",
            "end",
            "Germany",
            "Manufactures industrial equipment.",
            notification_type="Notification - acquisition",
        )
        self.records = [
            self.candidate,
            self.late_candidate,
            self.software_control,
            self.food_control,
            self.prior_activity,
            self.prior_activity_future_entry,
            self.france_control,
            self.corpus_end,
        ]
        self.cohorts, self.audit = _payloads([self.candidate, self.late_candidate])

    def test_month_arithmetic_and_activity_similarity(self):
        self.assertEqual(add_months("2020-01", 24), "2022-01")
        self.assertGreater(
            activity_similarity(
                "Develops software platforms for banks.",
                "Provides software platform solutions.",
            ),
            0,
        )
        self.assertEqual(
            activity_similarity(
                "Develops software platforms for banks.",
                "Imports specialty food products.",
            ),
            0,
        )

    def test_future_entrants_form_censored_risk_set_controls(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=2,
        )
        first = payload["candidates"][0]
        self.assertTrue(first["followup_complete"])
        self.assertEqual(first["horizon_end_month"], "2022-01")
        self.assertEqual(len(first["controls"]), 2)
        self.assertEqual(first["controls"][0]["investor_name"], "Future Software GmbH")
        self.assertEqual(first["controls"][0]["match_tier"], "COUNTRY_ACTIVITY")
        self.assertEqual(first["controls"][1]["investor_name"], "Late Candidate GmbH")
        self.assertEqual(first["controls"][1]["match_tier"], "COUNTRY_ACTIVITY")
        self.assertTrue(all(not row["negative_label_eligible"] for row in first["controls"]))
        self.assertTrue(all(
            row["identity_qualification_status"] == "UNREVIEWED"
            for row in first["controls"]
        ))
        self.assertTrue(all(
            not row["backtest_control_eligible"]
            for row in first["controls"]
        ))

    def test_future_candidate_may_serve_as_earlier_risk_set_control(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=5,
        )
        names = {
            row["investor_name"]
            for row in payload["candidates"][0]["controls"]
        }
        self.assertIn("Late Candidate GmbH", names)

    def test_prior_investment_canada_activity_disqualifies_control(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=5,
        )
        names = {
            row["investor_name"]
            for row in payload["candidates"][0]["controls"]
        }
        self.assertNotIn("Prior Activity GmbH", names)

    def test_country_mismatch_is_excluded(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=5,
        )
        names = {
            row["investor_name"]
            for row in payload["candidates"][0]["controls"]
        }
        self.assertNotIn("Future France SAS", names)

    def test_incomplete_followup_fails_closed(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=5,
        )
        late = payload["candidates"][1]
        self.assertFalse(late["followup_complete"])
        self.assertEqual(late["controls"], [])

    def test_summary_never_creates_negative_labels(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=2,
        )
        self.assertEqual(payload["summary"]["candidate_count"], 2)
        self.assertEqual(payload["summary"]["candidates_with_complete_followup"], 1)
        self.assertEqual(payload["summary"]["negative_labels_created"], 0)
        self.assertEqual(
            payload["summary"]["identity_unreviewed_assignments"],
            payload["summary"]["risk_set_candidate_assignments"],
        )
        self.assertEqual(
            payload["summary"]["backtest_control_eligible_assignments"],
            0,
        )
        validate_risk_set_controls(payload)

    def test_validator_rejects_unreviewed_candidate_promoted_to_backtest(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=2,
        )
        payload["candidates"][0]["controls"][0]["backtest_control_eligible"] = True
        with self.assertRaisesRegex(ValueError, "cannot be backtest controls"):
            validate_risk_set_controls(payload)

    def test_validator_rejects_control_inside_horizon(self):
        payload = build_risk_set_controls(
            self.records,
            self.cohorts,
            self.audit,
            horizon_months=24,
            max_controls=2,
        )
        payload["candidates"][0]["controls"][0]["future_new_business_month"] = "2021-12"
        with self.assertRaisesRegex(ValueError, "inside risk horizon"):
            validate_risk_set_controls(payload)


if __name__ == "__main__":
    unittest.main()
