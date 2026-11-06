"""Offline main-integration checks; no source transport or workflow activation."""
import ast
import json
from pathlib import Path
import unittest
from atlanticbridge import source_metadata
from atlanticbridge.automation.review_bridge import prepare_review_collection
from atlanticbridge.sources.halifax_building_permits import build_pinned_collection
from atlanticbridge.sources.nl_environmental_assessments import build_fixture_collection

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PINS = {'halifax_ui': {'contract_id': '6e7d245a153db8773c3904efb1d26f6c93efd6698c6d4db334d5c29bf7759c8a', 'input_sha256': '6e5614ce844f90292fda8941c9813bac0cac6340dd8088b2257fe0284fb18076'}, 'halifax_invented': {'contract_id': '1588dc4b98f057e7df73a6ed7da413719008ab87a30bf6ade8ff4064815620b9', 'input_sha256': '1679af64b936c31b56ef78301f8ab1f0104827fa4ea28b8f69f7700a66876ef4'}, 'nl_fixture': {'contract_id': 'd0ab350f2770ee33dbcd9379c5f0a7e7431d644cac774a65da3e3992cdcbb915', 'input_sha256': 'c35f9181ccc87d6caeadd359575b9fee6483558d2bce0c5a50f8dd9ace30afb5'}}
EXPECTED_METADATA = {'BODACC_ATTRIBUTION': 'Source: bodacc.fr / Direction de l’information légale et administrative (DILA), annonces-commerciales dataset; Etalab Open Licence 2.0. Source-file name: unknown; source-file date: unknown (not supplied by the bounded API response).', 'BODACC_LICENSE_URL': 'https://www.data.gouv.fr/pages/legal/licences/etalab-2-0', 'FEDERAL_GRANTS_ATTRIBUTION': 'Contains information licensed under the Open Government Licence – Canada. Source: Government of Canada, Proactive Disclosure - Grants and Contributions, https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013; https://open.canada.ca/en/open-government-licence-canada.', 'FEDERAL_GRANTS_LICENSE_URL': 'https://open.canada.ca/en/open-government-licence-canada'}

class AutomationMainIntegrationTests(unittest.TestCase):
    def test_metadata_matches_reviewed_literals_without_collector_imports(self):
        for key, value in EXPECTED_METADATA.items():
            self.assertEqual(getattr(source_metadata, key), value)
        syntax = ast.parse((ROOT / "src/atlanticbridge/source_metadata.py").read_text())
        self.assertFalse(any(isinstance(node, (ast.Import, ast.ImportFrom, ast.Call)) for node in ast.walk(syntax)))

    def test_packet_builder_has_no_live_collector_dependency(self):
        syntax = ast.parse((ROOT / "src/atlanticbridge/analyst_review.py").read_text())
        imports = [node.module for node in ast.walk(syntax) if isinstance(node, ast.ImportFrom)]
        self.assertIn("source_metadata", imports)
        for forbidden in ("sources.bodacc", "sources.federal_grants", "urllib.request", "requests", "httpx"):
            self.assertNotIn(forbidden, imports)

    def test_pinned_contracts_and_normalized_bytes_match_reviewed_r2(self):
        cases = {
            "halifax_ui": build_pinned_collection("ui_observed"),
            "halifax_invented": build_pinned_collection("invented"),
            "nl_fixture": build_fixture_collection((ROOT / "tests/fixtures/nl_environmental_assessments/synthetic-projects.html").read_bytes(), ["009901"]),
        }
        for name, collection in cases.items():
            with self.subTest(name=name):
                contract, batch = prepare_review_collection(collection, generated_at="2026-11-06T12:00:00Z")
                self.assertEqual(contract.contract_id, EXPECTED_PINS[name]["contract_id"])
                self.assertEqual(batch.input_sha256, EXPECTED_PINS[name]["input_sha256"])

    def test_pinned_data_are_declared_package_resources(self):
        packaging = (ROOT / "pyproject.toml").read_text()
        for name in ("nl_assessment_fixture_records.json", "halifax_permit_pinned_records.json"):
            self.assertIn("sources/" + name, packaging)
            self.assertTrue((ROOT / "src/atlanticbridge/sources" / name).is_file())

if __name__ == "__main__":
    unittest.main()
