from __future__ import annotations

import json
import unittest

from atlanticbridge.entry_identity import (
    _city_match,
    _lead_timing,
    _province_match,
    _role_status,
    normalize_legal_name,
)
from atlanticbridge.sources.corporations_canada import (
    detail_corporation_names,
    first_federal_jurisdiction_event,
)


class EntryIdentityTests(unittest.TestCase):
    def test_legal_name_normalization_preserves_word_content(self):
        self.assertEqual(
            normalize_legal_name("Example Canada Inc."),
            "examplecanadainc",
        )
        self.assertEqual(
            normalize_legal_name("Société Énergie S.A."),
            "societeenergiesa",
        )

    def test_geography_matching_is_conservative(self):
        self.assertTrue(_province_match("NS", "Nova Scotia"))
        self.assertTrue(_province_match("Québec", "Quebec"))
        self.assertFalse(_province_match("", "Ontario"))
        self.assertTrue(_city_match("Montréal", "Montreal"))
        self.assertFalse(_city_match("Halifax", "Dartmouth"))

    def test_detail_names_and_jurisdiction_event(self):
        payload = {
            "corporationNames": [
                {
                    "CorporationName": {
                        "name": "Example Canada Inc.",
                        "current": True,
                        "effectiveDate": "2023-01-10",
                    }
                },
                {
                    "CorporationName": {
                        "name": "Old Example Inc.",
                        "current": False,
                        "effectiveDate": "2022-04-01",
                        "expiryDate": "2023-01-10",
                    }
                },
            ],
            "activities": [
                {"activity": {"activity": "Incorporation", "date": "2022-04-01"}},
                {"activity": {"activity": "Amendment", "date": "2023-01-10"}},
            ],
        }
        self.assertEqual(
            detail_corporation_names(payload),
            ("Example Canada Inc.", "Old Example Inc."),
        )
        self.assertEqual(
            first_federal_jurisdiction_event(payload),
            ("Incorporation", "2022-04-01"),
        )

    def test_pre_entry_timing(self):
        status, days = _lead_timing("2024-03", "2023-08-15")
        self.assertEqual(status, "PRE_ENTRY")
        self.assertGreater(days, 180)

        status, days = _lead_timing("2024-03", "2024-03-15")
        self.assertEqual(status, "SAME_MONTH")
        self.assertLess(days, 0)

        self.assertEqual(_lead_timing("2024-03", ""), ("UNKNOWN", None))

    def test_role_status_does_not_call_vehicle_a_foreign_parent(self):
        row = {
            "investor_name": "Example Canada Inc.",
            "canadian_businesses_json": json.dumps(
                [{"name": "Example Canada Inc."}]
            ),
        }
        self.assertEqual(
            _role_status(row, ("Example Canada Inc.",)),
            "CANADIAN_VEHICLE_CONFIRMED",
        )

        distinct = {
            "investor_name": "Example Europe GmbH",
            "canadian_businesses_json": json.dumps(
                [{"name": "Example Canada Inc."}]
            ),
        }
        self.assertEqual(
            _role_status(distinct, ("Example Canada Inc.",)),
            "DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION",
        )


if __name__ == "__main__":
    unittest.main()
