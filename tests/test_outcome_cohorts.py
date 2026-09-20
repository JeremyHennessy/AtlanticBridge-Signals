import json
from pathlib import Path
import unittest

from atlanticbridge.outcome_cohorts import (
    summarize_outcome_cohorts,
    validate_outcome_cohorts,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "reviews/outcome_audit/2026-09-20-cases.json"
COHORTS = ROOT / "reviews/outcome_audit/2026-09-20-outcome-cohorts.json"


class OutcomeCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads(CASES.read_text())
        cls.cohorts = json.loads(COHORTS.read_text())

    def test_all_27_canonical_cases_are_partitioned_once(self):
        canonical_ids = {case["outcome_record_id"] for case in self.canonical["cases"]}
        cohort_ids = [case["outcome_record_id"] for case in self.cohorts["cases"]]
        self.assertEqual(len(cohort_ids), 27)
        self.assertEqual(len(set(cohort_ids)), 27)
        self.assertEqual(set(cohort_ids), canonical_ids)

    def test_current_cohort_counts_are_explicit(self):
        summary = summarize_outcome_cohorts(self.cohorts)
        self.assertEqual(
            summary["cohort_counts"],
            {
                "ESTABLISHMENT_ONLY": 2,
                "EXISTING_PRESENCE": 6,
                "NON_OPERATING_VEHICLE": 1,
                "TRUE_NEW_ENTRY_CANDIDATE": 7,
                "UNRESOLVED": 11,
            },
        )
        self.assertEqual(summary["censored_candidates_for_matching"], 7)
        self.assertEqual(summary["training_positive_eligible"], 0)

    def test_trillium_is_excluded_as_existing_presence_after_operation_window_audit(self):
        case = next(
            case for case in self.cohorts["cases"]
            if case["canadian_business_name"] == "Trillium Supply Chain Inc."
        )
        self.assertEqual(case["cohort"], "EXISTING_PRESENCE")
        self.assertEqual(case["timing_status"], "OPERATING_DURING_PERIOD")
        self.assertEqual(case["notification_relation"], "BEFORE_NOTIFICATION_MONTH")
        self.assertFalse(case["training_positive_eligible"])

    def test_true_entry_candidates_remain_censored_not_training_labels(self):
        candidates = [
            case for case in self.cohorts["cases"]
            if case["cohort"] == "TRUE_NEW_ENTRY_CANDIDATE"
        ]
        self.assertEqual(len(candidates), 7)
        self.assertTrue(all(case["censored_candidate_for_matching"] for case in candidates))
        self.assertTrue(all(not case["training_positive_eligible"] for case in candidates))

    def test_non_operating_holding_vehicle_is_separate(self):
        case = next(
            case for case in self.cohorts["cases"]
            if case["canadian_business_name"] == "K-Rouge Holding Inc."
        )
        self.assertEqual(case["cohort"], "NON_OPERATING_VEHICLE")
        self.assertFalse(case["censored_candidate_for_matching"])

    def test_validator_rejects_training_positive_promotion(self):
        payload = {
            "cases": [
                {
                    "outcome_record_id": "x",
                    "cohort": "TRUE_NEW_ENTRY_CANDIDATE",
                    "training_positive_eligible": True,
                    "censored_candidate_for_matching": True,
                    "rationale": "candidate only",
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "cannot promote training-positive"):
            validate_outcome_cohorts(payload)


if __name__ == "__main__":
    unittest.main()
