from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "reviews/backtests/2026-09-22-cipo-journal-extension-manifest.json"
)


class CIPOJournalExtensionManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_accepted_prefix_is_exactly_preserved(self):
        prefix = self.manifest["accepted_prefix"]
        self.assertEqual(prefix["issue_count"], 1221)
        self.assertEqual(prefix["end_date"], "2023-05-31")
        self.assertEqual(
            prefix["canonical_issue_sha256"],
            "8a89eccf0c368e82de4fcd62bea62481930210b7ddf2c182b18e7f45e7521a2d",
        )

    def test_extension_proof_is_complete(self):
        extension = self.manifest["extension"]
        self.assertEqual(extension["issue_count"], 52)
        self.assertEqual(extension["first_issue"], "2023-06-07")
        self.assertEqual(extension["last_issue"], "2024-05-29")
        self.assertEqual(extension["application_rows_scanned"], 51269)
        self.assertEqual(
            extension["retrieval_methods"],
            {"OFFICIAL_JOURNAL_HTML": 52},
        )
        self.assertEqual(
            extension["parser_modes"],
            {"MODERN_APPLICATION_NUMBER_APPLICANT": 52},
        )
        self.assertTrue(self.manifest["gate"]["passed"])
        self.assertEqual(self.manifest["gate"]["issue_failure_count"], 0)
        self.assertEqual(self.manifest["gate"]["structural_error_count"], 0)

    def test_source_extension_cannot_authorize_identity_absence(self):
        self.assertFalse(
            self.manifest["identity_absence_inference_allowed"]
        )
        self.assertIn(
            "cannot convert a new entity non-hit into CIPO absence",
            self.manifest["interpretation_boundary"],
        )


if __name__ == "__main__":
    unittest.main()
