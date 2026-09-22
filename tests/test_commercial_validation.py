import unittest
from atlanticbridge.commercial_validation import audit_outcomes, historical_signal_eligible, review_metrics, validate_split


class CommercialValidationTests(unittest.TestCase):
    def test_empty_reviews_are_unknown(self):
        result = review_metrics([])
        self.assertIsNone(result["identity_accuracy"]["rate"])
        self.assertIsNone(result["mean_review_seconds"])
        self.assertFalse(result["commercial_viability_proven"])

    def test_review_denominators_and_incremental_value(self):
        rows = [{"alert_id": "a", "reviewer": "independent", "identity_correct": True, "source_supported": True, "useful": True, "already_known": False, "review_seconds": 60},
                {"alert_id": "b", "reviewer": "independent", "identity_correct": False, "source_supported": True, "useful": True, "already_known": False}]
        result = review_metrics(rows)
        self.assertEqual(result["identity_accuracy"]["rate"], 0.5)
        self.assertEqual(result["new_to_reviewer_verified_useful_alerts"], 1)
        self.assertFalse(result["expansion_score_publication_allowed"])

    def test_duplicate_reviews_rejected(self):
        with self.assertRaises(ValueError):
            review_metrics([{"alert_id": "a", "reviewer": "r"}] * 2)

    def test_unreviewed_not_negative(self):
        result = review_metrics([{"alert_id": "a", "reviewer": "r", "identity_correct": None}])
        self.assertEqual(result["identity_accuracy"]["reviewed"], 0)
        self.assertIsNone(result["identity_accuracy"]["rate"])

    def test_false_string_not_boolean(self):
        with self.assertRaises(ValueError):
            review_metrics([{"alert_id": "a", "reviewer": "r", "useful": "false"}])

    def test_cross_group_leakage(self):
        rows = [{"company_id": "a", "corporate_group_id": "same", "split": "development", "legal_identity_confirmed": True},
                {"company_id": "b", "corporate_group_id": "same", "split": "holdout", "legal_identity_confirmed": True, "first_evaluated_at": "2026-09-24T00:00:00Z"}]
        with self.assertRaises(ValueError):
            validate_split(rows, "2026-09-22T00:00:00Z")

    def test_posthoc_holdout_rejected(self):
        row = {"company_id": "a", "corporate_group_id": "g", "split": "holdout", "legal_identity_confirmed": True, "first_evaluated_at": "2026-09-21T00:00:00Z"}
        with self.assertRaises(ValueError):
            validate_split([row], "2026-09-22T00:00:00Z")

    def test_unknown_is_not_no_entry(self):
        row = {"company_id": "a", "corporate_group_id": "g", "split": "development", "legal_identity_confirmed": True, "outcome_label": "NO_ENTRY"}
        with self.assertRaises(ValueError):
            validate_split([row], "2026-09-22T00:00:00Z")

    def test_current_copy_of_old_page_ineligible(self):
        row = {"legal_identity_confirmed": True, "availability_basis": "CONTEMPORANEOUS_RETAINED_SNAPSHOT", "snapshot_sha256": "a" * 64, "snapshot_observed_at": "2026-09-22T00:00:00Z", "publicly_available_at": "2024-01-01T00:00:00Z"}
        self.assertFalse(historical_signal_eligible(row, "2025-01-01T00:00:00Z"))
        self.assertTrue(historical_signal_eligible(row, "2026-09-23T00:00:00Z"))

    def test_missing_evidence_ineligible(self):
        self.assertFalse(historical_signal_eligible({}, "2026-09-22T00:00:00Z"))

    def test_announcement_not_verified_opening(self):
        row = {"id": "a", "event_type": "ANNOUNCED_FIRST_ESTABLISHMENT", "source_url": "https://example.org/a", "source_publication_date": "2026-06-25", "operational_opening_date": "2026-06-25"}
        with self.assertRaises(ValueError):
            audit_outcomes([row])

    def test_calibration_not_independent(self):
        row = {"id": "a", "event_type": "REGULATORY_OR_MEMBERSHIP_MILESTONE", "source_url": "https://example.org/a", "source_publication_date": "2026-06-25", "split": "calibration", "independent_holdout": True}
        with self.assertRaises(ValueError):
            audit_outcomes([row])


if __name__ == "__main__":
    unittest.main()
