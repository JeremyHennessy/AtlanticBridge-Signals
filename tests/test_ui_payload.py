import json
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest

from atlanticbridge.outcome_evidence import (
    evidence_publication_status,
    summarize_outcome_publication_gate,
)


ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location("build_ui_payload", ROOT / "scripts" / "build_ui_payload.py")
ui_payload = module_from_spec(spec)
spec.loader.exec_module(ui_payload)


class UIPayloadTests(unittest.TestCase):
    def test_checked_in_payload_matches_source_audits(self):
        generated = ui_payload.build_payload()
        checked_in = json.loads((ROOT / "ui" / "data" / "dashboard.json").read_text())
        self.assertEqual(checked_in, generated)

    def test_ui_fails_closed_on_model_eligibility(self):
        payload = ui_payload.build_payload()
        self.assertEqual(payload["summary"]["model_eligible_count"], 0)
        self.assertEqual(payload["summary"]["first_operation_dates_established"], 0)
        self.assertTrue(all(not case["model_eligible"] for case in payload["cases"]))

    def test_ui_summary_preserves_current_audit_counts(self):
        payload = ui_payload.build_payload()
        self.assertEqual(payload["summary"]["case_count"], 27)
        self.assertEqual(payload["summary"]["evidence_case_count"], 23)
        self.assertEqual(payload["summary"]["identity_supported"], 12)
        self.assertEqual(payload["summary"]["identity_requires_review"], 0)
        self.assertEqual(len(payload["cases"]), payload["summary"]["case_count"])

    def test_ui_publication_cutoff_matches_canonical_gate(self):
        payload = ui_payload.build_payload()
        cases_doc = json.loads(
            (ROOT / "reviews/outcome_audit/2026-09-20-cases.json").read_text()
        )
        expected = summarize_outcome_publication_gate(cases_doc)
        self.assertEqual(
            payload["summary"]["publication_status_counts"],
            expected["publication_status_counts"],
        )
        self.assertEqual(
            payload["summary"]["cases_with_verified_pre_notification_evidence"],
            expected["cases_with_verified_pre_notification_evidence"],
        )

        source_by_id = {
            case["outcome_record_id"]: case
            for case in cases_doc["cases"]
        }
        for ui_case in payload["cases"]:
            source_case = source_by_id[ui_case["id"]]
            self.assertEqual(
                len(ui_case["evidence"]),
                len(source_case["additional_evidence"]),
            )
            for ui_evidence, source_evidence in zip(
                ui_case["evidence"],
                source_case["additional_evidence"],
            ):
                self.assertEqual(
                    ui_evidence["publication_status"],
                    evidence_publication_status(
                        source_evidence,
                        source_case["notification_month"],
                    ),
                )
                self.assertEqual(
                    ui_evidence["publicly_available_date"],
                    source_evidence.get("publicly_available_date"),
                )
                self.assertEqual(
                    ui_evidence["publicly_available_date_precision"],
                    source_evidence.get("publicly_available_date_precision"),
                )

    def test_static_ui_assets_exist_and_reference_payload(self):
        index = (ROOT / "ui" / "index.html").read_text()
        app = (ROOT / "ui" / "app.js").read_text()
        styles = (ROOT / "ui" / "styles.css").read_text()
        self.assertIn("AtlanticBridge Signals", index)
        self.assertIn("Evidence Console", index)
        self.assertIn('fetch("data/dashboard.json"', app)
        self.assertIn(".drawer", styles)


if __name__ == "__main__":
    unittest.main()
