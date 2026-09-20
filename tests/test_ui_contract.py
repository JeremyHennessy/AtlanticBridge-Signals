import json
from pathlib import Path
import unittest

from atlanticbridge.outcome_evidence import (
    PUBLICATION_STATUSES,
    evidence_publication_status,
    summarize_outcome_publication_gate,
)


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reviews/outcome_audit/2026-09-20-cases.json"


class UiAuditContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(AUDIT.read_text())

    def test_ui_shell_files_exist(self):
        for relative in ("ui/index.html", "ui/styles.css", "ui/app.js"):
            path = ROOT / relative
            self.assertTrue(path.is_file(), relative)
            self.assertGreater(path.stat().st_size, 100, relative)

    def test_every_case_has_the_fields_used_by_ui(self):
        required = {
            "outcome_record_id",
            "investor_name",
            "ultimate_control_country",
            "canadian_business_name",
            "notification_month",
            "outcome_classification",
            "model_eligible",
            "additional_evidence",
        }
        for case in self.payload["cases"]:
            self.assertTrue(required.issubset(case), case.get("outcome_record_id"))
            self.assertIsInstance(case["additional_evidence"], list)

    def test_publication_status_contract_is_renderable(self):
        summary = summarize_outcome_publication_gate(self.payload)
        self.assertGreater(summary["case_count"], 0)
        for case in self.payload["cases"]:
            for evidence in case["additional_evidence"]:
                status = evidence_publication_status(evidence, case["notification_month"])
                self.assertIn(status, PUBLICATION_STATUSES)

    def test_ui_data_fallback_tracks_canonical_audit(self):
        app = (ROOT / "ui/app.js").read_text()
        self.assertIn("reviews/outcome_audit/2026-09-20-cases.json", app)
        self.assertIn("VERIFIED_BEFORE_NOTIFICATION_MONTH", app)
        self.assertIn("UNVERIFIED", app)

    def test_ui_does_not_require_a_score_field(self):
        for case in self.payload["cases"]:
            self.assertNotIn("expansion_score", case)
        app = (ROOT / "ui/app.js").read_text()
        self.assertNotIn("item.expansion_score", app)


if __name__ == "__main__":
    unittest.main()
