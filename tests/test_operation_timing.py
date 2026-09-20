import json
from pathlib import Path
import unittest

from atlanticbridge.operation_timing import (
    summarize_operation_timing_audit,
    validate_operation_timing_audit,
)


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "reviews/outcome_audit/2026-09-20-cases.json"
TIMING = ROOT / "reviews/outcome_audit/2026-09-20-operation-windows.json"


class OperationTimingAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.canonical = json.loads(CASES.read_text())
        cls.timing = json.loads(TIMING.read_text())

    def test_all_27_canonical_cases_are_covered_exactly_once(self):
        canonical_ids = {case["outcome_record_id"] for case in self.canonical["cases"]}
        timing_ids = [case["outcome_record_id"] for case in self.timing["cases"]]
        self.assertEqual(len(timing_ids), 27)
        self.assertEqual(len(set(timing_ids)), 27)
        self.assertEqual(set(timing_ids), canonical_ids)

    def test_exact_first_operation_gate_remains_closed(self):
        summary = summarize_operation_timing_audit(self.timing)
        self.assertEqual(summary["case_count"], 27)
        self.assertEqual(summary["exact_first_operation_dates"], 0)
        self.assertEqual(summary["model_eligible_from_timing"], 0)
        self.assertEqual(summary["cases_with_operation_upper_bound"], 6)
        self.assertTrue(
            all(
                case["first_canadian_operations_date"] is None
                and not case["exact_first_operation_proven"]
                and not case["model_eligible_from_timing"]
                for case in self.timing["cases"]
            )
        )

    def test_precise_operating_by_dates_are_bounds_not_first_dates(self):
        by_business = {
            case["canadian_business_name"]: case for case in self.timing["cases"]
        }
        expected = {
            "Backbase Canada Inc.": "2018-10-29",
            "2022 Environmental Science CA Inc.": "2018-06-13",
            "Reebelo Canada, Inc.": "2023-07-05",
        }
        for business, value in expected.items():
            case = by_business[business]
            self.assertEqual(case["timing_status"], "OPERATING_BY_DATE")
            self.assertEqual(case["observation_value"], value)
            self.assertTrue(case["operation_bound_kind"].startswith("UPPER_BOUND"))
            self.assertIsNone(case["first_canadian_operations_date"])

    def test_coarse_windows_do_not_invent_day_precision(self):
        by_business = {
            case["canadian_business_name"]: case for case in self.timing["cases"]
        }
        self.assertEqual(
            by_business["Trillium Supply Chain Inc."]["observation_value"], "2021-01"
        )
        self.assertEqual(
            by_business["Trillium Supply Chain Inc."]["observation_precision"], "MONTH"
        )
        self.assertEqual(by_business["Aiut Inc."]["observation_value"], "2021")
        self.assertEqual(by_business["Aiut Inc."]["observation_precision"], "YEAR")
        self.assertEqual(by_business["Bolton BG Canada Inc."]["observation_value"], "2017")
        self.assertEqual(
            by_business["Bolton BG Canada Inc."]["observation_precision"], "YEAR"
        )

    def test_holding_vehicle_is_not_promoted_to_operating_outcome(self):
        case = next(
            case
            for case in self.timing["cases"]
            if case["canadian_business_name"] == "K-Rouge Holding Inc."
        )
        self.assertEqual(case["timing_status"], "NON_OPERATING_HOLDING_VEHICLE")
        self.assertEqual(case["operation_bound_kind"], "NO_OPERATION_BOUND")
        self.assertEqual(case["notification_relation"], "NOT_APPLICABLE")

    def test_validator_rejects_timing_eligibility_without_exact_outcome(self):
        payload = {
            "cases": [
                {
                    "outcome_record_id": "x",
                    "timing_status": "UNRESOLVED",
                    "operation_bound_kind": "NO_OPERATION_BOUND",
                    "observation_value": None,
                    "observation_precision": None,
                    "first_canadian_operations_date": None,
                    "exact_first_operation_proven": False,
                    "model_eligible_from_timing": True,
                }
            ]
        }
        with self.assertRaisesRegex(ValueError, "requires an exact first-operation"):
            validate_operation_timing_audit(payload)


if __name__ == "__main__":
    unittest.main()
