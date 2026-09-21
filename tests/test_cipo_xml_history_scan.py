from __future__ import annotations

from xml.etree import ElementTree as ET
import unittest

from scripts.scan_cipo_xml_history import (
    extract_advertised_dates,
    extract_application_number,
    extract_applicant_names,
    inspect_candidate_xml,
    normalize_name,
)


class CIPOFullHistoricalXMLScannerTests(unittest.TestCase):
    def _xml(self) -> bytes:
        return b"""<?xml version="1.0" encoding="UTF-8"?>
<Trademark>
  <ApplicationNumber>1799092</ApplicationNumber>
  <InterestedPartyBag>
    <InterestedParty>
      <InterestedPartyCategory>Applicant</InterestedPartyCategory>
      <EntityName>SIOO WOODPROTECTION AB</EntityName>
    </InterestedParty>
    <InterestedParty>
      <InterestedPartyCategory>Agent</InterestedPartyCategory>
      <EntityName>Example Agent LLP</EntityName>
    </InterestedParty>
  </InterestedPartyBag>
  <Publication>
    <PublicationStatusCategory>Advertised</PublicationStatusCategory>
    <PublicationActionDate>2018-12-12</PublicationActionDate>
  </Publication>
  <MarkEvent>
    <MarkEventDescriptionText>Advertised</MarkEventDescriptionText>
    <MarkEventDate>2018-12-12</MarkEventDate>
  </MarkEvent>
</Trademark>
"""

    def test_extracts_only_applicant_identity(self):
        root = ET.fromstring(self._xml())
        self.assertEqual(
            extract_applicant_names(root),
            ["SIOO WOODPROTECTION AB"],
        )

    def test_extracts_advertised_date_without_duplicates(self):
        root = ET.fromstring(self._xml())
        self.assertEqual(
            extract_advertised_dates(root),
            ["2018-12-12"],
        )

    def test_application_number_prefers_archive_filename(self):
        root = ET.fromstring(self._xml())
        self.assertEqual(
            extract_application_number(root, "folder/1799092-00.xml"),
            "1799092",
        )

    def test_candidate_inspection_requires_exact_reviewed_applicant(self):
        aliases = {
            normalize_name("SIOO WOODPROTECTION AB"): {
                "entrant:sioo"
            }
        }
        matches = inspect_candidate_xml(
            self._xml(),
            archive_entry="1799092-00.xml",
            alias_to_entities=aliases,
        )
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["entity_id"], "entrant:sioo")
        self.assertEqual(matches[0]["application_number"], "1799092")
        self.assertEqual(
            matches[0]["earliest_advertised_date"],
            "2018-12-12",
        )

    def test_agent_name_does_not_create_applicant_match(self):
        aliases = {
            normalize_name("Example Agent LLP"): {
                "control:agent"
            }
        }
        matches = inspect_candidate_xml(
            self._xml(),
            archive_entry="1799092-00.xml",
            alias_to_entities=aliases,
        )
        self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
