"""Prevent malformed supplied review data from creating accepted denominators."""
import unittest
from atlanticbridge.commercial_validation import audit_outcomes, review_metrics, validate_split


class ValidationInputTests(unittest.TestCase):
    def outcome(self, **extra):
        return {"id": "fixture", "event_type": "VERIFIED_OPERATIONAL_OPENING",
                "source_url": "https://example.org/opening", "source_publication_date": "2026-06-25", **extra}

    def test_verified_label_without_date_or_evidence_rejected(self):
        with self.assertRaises(ValueError):
            audit_outcomes([self.outcome()])

    def test_verified_date_without_evidence_rejected(self):
        with self.assertRaises(ValueError):
            audit_outcomes([self.outcome(operational_opening_date="2026-06-25")])

    def test_complete_opening_contract_counted(self):
        result = audit_outcomes([self.outcome(operational_opening_date="2026-06-25", opening_evidence="retained fixture reference")])
        self.assertEqual(result["verified_operational_openings"], 1)
        self.assertFalse(result["expansion_score_publication_allowed"])

    def test_false_string_cannot_confirm_outcome(self):
        with self.assertRaises(ValueError):
            audit_outcomes([self.outcome(legal_identity_confirmed="false")])

    def test_false_string_cannot_qualify_cohort(self):
        row = {"company_id": "fixture", "corporate_group_id": "fixture-group", "split": "development", "legal_identity_confirmed": "false"}
        with self.assertRaises(ValueError):
            validate_split([row], "2026-09-22T00:00:00Z")

    def test_non_finite_review_times_rejected(self):
        for seconds in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                review_metrics([{"alert_id": "fixture", "reviewer": "fixture-reviewer", "review_seconds": seconds}])


if __name__ == "__main__":
    unittest.main()
