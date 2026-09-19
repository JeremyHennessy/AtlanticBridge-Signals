from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from atlanticbridge.foreign_identity import (
    _locality_matches,
    _parent_evidence,
    _resolved_named_status,
    classify_candidates,
)
from atlanticbridge.sources.gleif import GLEIFCandidate


def candidate(
    *,
    lei: str,
    legal_name: str,
    legal_city: str = "",
    hq_city: str = "",
    exact: bool = True,
    relationship_links: dict | None = None,
):
    return GLEIFCandidate(
        rank=1,
        lei=lei,
        legal_name=legal_name,
        jurisdiction="NL",
        entity_status="ACTIVE",
        entity_category="GENERAL",
        registered_as="123",
        registration_authority_id="RA000000",
        legal_address_city=legal_city,
        legal_address_country="NL",
        headquarters_city=hq_city,
        headquarters_country="NL",
        name_similarity=1.0 if exact else 0.8,
        exact_normalized_name=exact,
        jurisdiction_match=False,
        match_class="EXACT_NAME" if exact else "CANDIDATE",
        relationship_links_json=json.dumps(
            relationship_links or {},
            sort_keys=True,
        ),
        record_json="{}",
    )


class ForeignIdentityTests(unittest.TestCase):
    def test_exact_name_and_locality_confirms_named_entity(self):
        row = candidate(
            lei="LEI1",
            legal_name="Example B.V.",
            legal_city="Amsterdam",
        )
        status, selected, exact_count, locality_count = classify_candidates(
            (row,),
            "Amsterdam",
        )
        self.assertEqual(status, "CONFIRMED_NAMED_ENTITY")
        self.assertEqual(selected.lei, "LEI1")
        self.assertEqual(exact_count, 1)
        self.assertEqual(locality_count, 1)

    def test_exact_name_without_locality_is_review_only(self):
        row = candidate(
            lei="LEI1",
            legal_name="Example B.V.",
            legal_city="Rotterdam",
        )
        status, selected, exact_count, locality_count = classify_candidates(
            (row,),
            "Amsterdam",
        )
        self.assertEqual(status, "REVIEW_READY_EXACT_NAME")
        self.assertEqual(selected.lei, "LEI1")
        self.assertEqual(exact_count, 1)
        self.assertEqual(locality_count, 0)

    def test_multiple_exact_names_are_ambiguous_without_unique_locality(self):
        first = candidate(
            lei="LEI1",
            legal_name="Example B.V.",
            legal_city="Amsterdam",
        )
        second = candidate(
            lei="LEI2",
            legal_name="Example B.V.",
            legal_city="Amsterdam",
        )
        status, selected, exact_count, locality_count = classify_candidates(
            (first, second),
            "Amsterdam",
        )
        self.assertEqual(status, "AMBIGUOUS_EXACT")
        self.assertIsNone(selected)
        self.assertEqual(exact_count, 2)
        self.assertEqual(locality_count, 2)

    def test_locality_normalizes_diacritics(self):
        row = candidate(
            lei="LEI1",
            legal_name="Example A/S",
            legal_city="Montréal",
        )
        self.assertTrue(_locality_matches(row, "Montreal"))



    def test_confirmed_named_entity_is_not_foreign_when_gleif_entity_is_canadian(self):
        row = GLEIFCandidate(
            rank=1,
            lei="CANADA-LEI",
            legal_name="Example Holdings Inc.",
            jurisdiction="CA-AB",
            entity_status="ACTIVE",
            entity_category="GENERAL",
            registered_as="123",
            registration_authority_id="RA-CA",
            legal_address_city="Calgary",
            legal_address_country="CA",
            headquarters_city="Calgary",
            headquarters_country="CA",
            name_similarity=1.0,
            exact_normalized_name=True,
            jurisdiction_match=False,
            match_class="EXACT_NAME",
            relationship_links_json="{}",
            record_json="{}",
        )
        self.assertEqual(
            _resolved_named_status("CONFIRMED_NAMED_ENTITY", row),
            "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED",
        )

    def test_confirmed_named_entity_is_foreign_when_gleif_entity_is_non_canadian(self):
        row = candidate(
            lei="NL-LEI",
            legal_name="Example B.V.",
            legal_city="Amsterdam",
        )
        self.assertEqual(
            _resolved_named_status("CONFIRMED_NAMED_ENTITY", row),
            "CONFIRMED_FOREIGN_NAMED_ENTITY",
        )

    @patch("atlanticbridge.foreign_identity.fetch_api_resource")
    @patch("atlanticbridge.foreign_identity.fetch_lei_record")
    def test_parent_relationship_uses_end_node_parent(
        self,
        fetch_lei_record,
        fetch_api_resource,
    ):
        row = candidate(
            lei="CHILD",
            legal_name="Child B.V.",
            relationship_links={
                "ultimate-parent": {
                    "links": {
                        "related": "https://api.gleif.org/api/v1/relationships/1"
                    }
                }
            },
        )
        fetch_api_resource.return_value = {
            "data": {
                "attributes": {
                    "relationship": {
                        "startNode": {"id": "CHILD", "type": "LEI"},
                        "endNode": {"id": "PARENT", "type": "LEI"},
                        "type": "IS_ULTIMATELY_CONSOLIDATED_BY",
                    }
                }
            }
        }
        fetch_lei_record.return_value = {
            "data": {
                "attributes": {
                    "entity": {
                        "legalName": {"name": "Parent N.V."}
                    }
                }
            }
        }

        result = _parent_evidence(row, "ultimate-parent")
        self.assertEqual(result["status"], "PARENT_LEI")
        self.assertEqual(result["lei"], "PARENT")
        self.assertEqual(result["legal_name"], "Parent N.V.")
        self.assertEqual(
            result["relationship_type"],
            "IS_ULTIMATELY_CONSOLIDATED_BY",
        )

    @patch("atlanticbridge.foreign_identity.fetch_api_resource")
    def test_reporting_exception_is_preserved(self, fetch_api_resource):
        row = candidate(
            lei="CHILD",
            legal_name="Child A/S",
            relationship_links={
                "direct-parent": {
                    "links": {
                        "reporting-exception":
                            "https://api.gleif.org/api/v1/lei-records/CHILD/"
                            "direct-parent-reporting-exception"
                    }
                }
            },
        )
        fetch_api_resource.return_value = {
            "data": {
                "attributes": {
                    "category": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT",
                    "reason": "NO_LEI",
                }
            }
        }
        result = _parent_evidence(row, "direct-parent")
        self.assertEqual(result["status"], "REPORTING_EXCEPTION")
        self.assertEqual(result["exception_reason"], "NO_LEI")


if __name__ == "__main__":
    unittest.main()
