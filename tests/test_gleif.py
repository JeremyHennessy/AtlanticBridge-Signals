from __future__ import annotations

import json
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

from atlanticbridge.gleif_resolution import (
    ResolutionTarget,
    ensure_gleif_schema,
    gleif_resolution_summary,
    persist_search_result,
)
from atlanticbridge.sources.gleif import (
    GLEIFSearchResult,
    normalize_entity_name,
    search_legal_name,
)


def _response(payload: dict):
    response = MagicMock()
    response.__enter__.return_value = response
    response.__exit__.return_value = False
    response.__iter__.return_value = iter([])
    return response


class GLEIFTests(unittest.TestCase):
    def test_name_normalization_is_conservative(self):
        self.assertEqual(normalize_entity_name("Siemens Healthineers AG"), "siemenshealthineersag")
        self.assertEqual(normalize_entity_name("Société Exemple S.A."), "societeexemplesa")

    @patch("atlanticbridge.sources.gleif._request_json")
    def test_search_classifies_exact_name_country_without_confirming(self, request_json):
        request_json.return_value = {
            "meta": {
                "goldenCopy": {"publishDate": "2026-09-18T08:00:00Z"},
                "pagination": {"total": 2},
            },
            "data": [
                {
                    "id": "LEI-EXACT",
                    "attributes": {
                        "entity": {
                            "legalName": {"name": "Example GmbH"},
                            "jurisdiction": "DE",
                            "status": "ACTIVE",
                            "category": "GENERAL",
                            "registeredAs": "HRB 123",
                            "registeredAt": {"id": "RA-DE"},
                            "legalAddress": {"city": "Berlin", "country": "DE"},
                            "headquartersAddress": {"city": "Berlin", "country": "DE"},
                        }
                    },
                    "relationships": {"direct-parent": {"links": {"related": "https://example.test"}}},
                },
                {
                    "id": "LEI-OTHER",
                    "attributes": {
                        "entity": {
                            "legalName": {"name": "Example Holdings GmbH"},
                            "jurisdiction": "DE",
                            "status": "ACTIVE",
                            "category": "GENERAL",
                            "registeredAs": "HRB 999",
                            "registeredAt": {"id": "RA-DE"},
                            "legalAddress": {"city": "Munich", "country": "DE"},
                            "headquartersAddress": {"city": "Munich", "country": "DE"},
                        }
                    },
                    "relationships": {},
                },
            ],
        }

        result = search_legal_name("Example GmbH", source_country="DE", page_size=5)
        self.assertEqual(result.total_results, 2)
        self.assertEqual(result.candidates[0].match_class, "EXACT_NAME_COUNTRY")
        self.assertTrue(result.candidates[0].exact_normalized_name)
        self.assertTrue(result.candidates[0].jurisdiction_match)
        self.assertNotEqual(result.candidates[1].match_class, "EXACT_NAME_COUNTRY")

    def test_single_exact_match_is_review_ready_not_confirmed(self):
        candidate = MagicMock()
        candidate.lei = "LEI-EXACT"
        candidate.legal_name = "Example GmbH"
        candidate.jurisdiction = "DE"
        candidate.entity_status = "ACTIVE"
        candidate.entity_category = "GENERAL"
        candidate.registered_as = "HRB 123"
        candidate.registration_authority_id = "RA-DE"
        candidate.legal_address_city = "Berlin"
        candidate.legal_address_country = "DE"
        candidate.headquarters_city = "Berlin"
        candidate.headquarters_country = "DE"
        candidate.rank = 1
        candidate.name_similarity = 1.0
        candidate.exact_normalized_name = True
        candidate.jurisdiction_match = True
        candidate.match_class = "EXACT_NAME_COUNTRY"
        candidate.relationship_links_json = "{}"
        candidate.record_json = json.dumps({"id": "LEI-EXACT"})

        result = GLEIFSearchResult(
            query_url="https://api.gleif.org/example",
            golden_copy_publish_date="2026-09-18T08:00:00Z",
            total_results=1,
            candidates=(candidate,),
        )
        target = ResolutionTarget(
            source_system="CORDIS",
            source_entity_id="ORG-1",
            source_name="Example GmbH",
            source_country="DE",
            source_vat_number="DE123",
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        ensure_gleif_schema(conn)
        persisted = persist_search_result(
            conn,
            target,
            result,
            observed_at="2026-09-18T20:00:00+00:00",
        )

        self.assertEqual(persisted["status"], "REVIEW_READY")
        status = conn.execute(
            "SELECT status, confirmed_lei FROM gleif_resolution_status"
        ).fetchone()
        self.assertEqual(status["status"], "REVIEW_READY")
        self.assertEqual(status["confirmed_lei"], "")

        summary = gleif_resolution_summary(conn)
        self.assertEqual(summary["source_entities"], 1)
        self.assertEqual(summary["candidate_rows"], 1)

    def test_no_results_is_explicit(self):
        result = GLEIFSearchResult(
            query_url="https://api.gleif.org/example",
            golden_copy_publish_date="2026-09-18T08:00:00Z",
            total_results=0,
            candidates=(),
        )
        target = ResolutionTarget(
            source_system="CORDIS",
            source_entity_id="ORG-404",
            source_name="No Match Example",
            source_country="FR",
            source_vat_number="",
        )

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        persisted = persist_search_result(
            conn,
            target,
            result,
            observed_at="2026-09-18T20:00:00+00:00",
        )
        self.assertEqual(persisted["status"], "NO_RESULTS")


if __name__ == "__main__":
    unittest.main()
