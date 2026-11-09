import copy
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from atlanticbridge.cordis_research import HORIZON_ARCHIVE_URL, build_research_payload, main


def organisation(pic="900000001", name="EU Company", country="FR", activity="PRC", **attrs):
    return {"contenttype": "organization", "id": pic, "legalName": name,
            "vatNumber": "DO-NOT-EXPORT-VAT", "address": {"country": country, "street": "DO-NOT-EXPORT-ADDRESS"},
            "contactForm": "DO-NOT-EXPORT-CONTACT",
            "attributes": {"type": "participant", "terminated": "false", "active": "false", **attrs},
            "relations": {"categories": [{"code": "/" + activity, "attributes": {"classification": "organizationActivityType", "type": "relatedOrganizationActivityType"}}]}}


def project(identifier="101000001", **extra):
    return {"contenttype": "project", "language": "en", "id": identifier, "rcn": identifier,
            "acronym": "EXAMPLE", "title": "Clean energy research", "objective": "DO-NOT-EXPORT-OBJECTIVE",
            "status": "SIGNED", "startDate": "2025-01-01", "endDate": "2028-12-31",
            "contentUpdateDate": "2026-10-01 12:00:00", "contentCreationDate": "2021-01-01 00:00:00",
            "relations": {"associations": [organisation(), organisation("900000002", "Canadian University", "CA", "HES")]}, **extra}


class CordisResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "source.zip"

    def archive(self, rows=None, raw=None, extra=None):
        with zipfile.ZipFile(self.path, "w") as archive:
            for row in rows if rows is not None else [project()]:
                archive.writestr(f"project-rcn-{row['rcn']}_en.json", json.dumps(row) if raw is None else raw)
            for name, content in (extra or {}).items():
                archive.writestr(name, content)
        data = self.path.read_bytes()
        self.receipt = {"source_url": HORIZON_ARCHIVE_URL, "final_url": HORIZON_ARCHIVE_URL, "http_status": 200,
                        "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data), "retrieved_at": "2026-11-09T12:00:00Z",
                        "last_modified": "Thu, 08 Oct 2026 15:52:57 GMT", "catalogue_modified": "2026-10-15"}
        return self.receipt

    def build(self):
        return build_research_payload(self.path, self.receipt, as_of_date=date(2026, 11, 9))

    def test_research_only_source_identity_clocks_and_privacy(self):
        self.archive()
        output = self.build()
        self.assertEqual(output["summary"]["project_count"], 1)
        self.assertEqual(output["summary"]["qualified_lead_count"], 0)
        self.assertEqual(output["audit"]["archive_organisation_rows"], 2)
        self.assertEqual(output["source"]["sha256"], self.receipt["sha256"])
        self.assertEqual(output["source"]["retrieved_at"], "2026-11-09T12:00:00+00:00")
        self.assertNotEqual(output["source"]["retrieved_at"], output["source"]["catalogue_modified"])
        record = output["projects"][0]
        self.assertFalse(record["model_eligible"])
        self.assertFalse(record["expansion_inferred"])
        self.assertEqual(record["qualification_status"], "RESEARCH_ONLY_NOT_QUALIFIED")
        self.assertEqual(record["source_url"], "https://cordis.europa.eu/project/id/101000001")
        self.assertTrue(record["unended_canada_and_eu_prc_participants_listed"])
        self.assertFalse(record["project_end_date_is_past"])
        self.assertEqual(record["eu_prc_participants"][0]["active_fpa_raw"], "false")
        encoded = json.dumps(output)
        for sensitive in ["DO-NOT-EXPORT", "contentCreationDate", "vatNumber", "contactForm", "street"]:
            self.assertNotIn(sensitive, encoded)

    def test_country_and_activity_scope_are_not_ultimate_parentage(self):
        rows = []
        for i, country, activity, canada in [(1, "FR", "PRC", True), (2, "GB", "PRC", True), (3, "FR", "HES", True), (4, "FR", "PRC", False)]:
            orgs = [organisation(country=country, activity=activity)]
            if canada:
                orgs.append(organisation("900000002", "Canada", "CA", "HES"))
            rows.append(project(str(i), relations={"associations": orgs}))
        self.archive(rows)
        output = self.build()
        self.assertEqual([p["project_id"] for p in output["projects"]], ["1"])
        self.assertEqual(output["audit"]["canada_projects"], 3)
        self.assertEqual(output["audit"]["canada_eu_any_activity_projects"], 2)

    def test_greek_source_alias_is_preserved_and_included(self):
        p = project()
        p["relations"]["associations"][0]["address"]["country"] = "EL"
        self.archive([p])
        output = self.build()
        self.assertEqual(output["summary"]["project_count"], 1)
        org = output["projects"][0]["eu_prc_participants"][0]
        self.assertEqual(org["country_raw"], "EL")
        self.assertEqual(org["country"], "GR")

    def test_military_and_ambiguous_scope_are_held_not_qualified(self):
        self.archive([project("1", objective="Military systems"), project("2", objective="Dual-use technologies"), project("3")])
        output = self.build()
        self.assertEqual([p["project_id"] for p in output["projects"]], ["3"])
        self.assertEqual(output["audit"]["scope_held_projects"], [{"project_id": "1", "reason": "EXPLICIT_MILITARY_MARKER"}, {"project_id": "2", "reason": "AMBIGUOUS_CIVILIAN_SCOPE"}])
        self.assertEqual(output["summary"]["qualified_lead_count"], 0)

    def test_missing_end_date_or_ended_participation_never_infers_active(self):
        p = project(endDate="not-a-date")
        p["relations"]["associations"][0]["attributes"].update(terminated="true", active="true")
        self.archive([p])
        r = self.build()["projects"][0]
        self.assertIsNone(r["project_end_date_is_past"])
        self.assertFalse(r["unended_canada_and_eu_prc_participants_listed"])
        self.assertFalse(r["expansion_inferred"])

    def test_missing_pic_stays_unresolved_not_name_merged(self):
        p = project()
        del p["relations"]["associations"][0]["id"]
        self.archive([p])
        o = self.build()
        self.assertEqual(o["summary"]["missing_organisation_id_rows"], 1)
        self.assertEqual(o["summary"]["eu_prc_source_organisation_ids"], 0)

    def test_receipt_exact_source_status_size_hash_and_time_required(self):
        self.archive()
        good = copy.deepcopy(self.receipt)
        for field, bad in [("source_url", "https://example.com/source.zip"), ("final_url", "https://example.com/source.zip"), ("http_status", 206), ("http_status", True), ("bytes", 1), ("bytes", True), ("sha256", "0"*64), ("retrieved_at", "2026-11-09T12:00:00"), ("retrieved_at", "2026-11-10T00:00:00Z")]:
            with self.subTest(field=field, bad=bad):
                self.receipt = {**good, field: bad}
                with self.assertRaises((ValueError, TypeError)):
                    self.build()

    def test_duplicate_json_keys_and_nonfinite_values_fail_closed(self):
        for raw in ['{"id":"1","id":"2"}', '{"id":NaN}']:
            self.archive(raw=raw)
            with self.assertRaises(ValueError):
                self.build()

    def test_schema_member_identity_and_unknown_archive_members_fail_closed(self):
        for changed in [dict(contenttype="other"), dict(language="fr"), dict(relations={}), dict(id="bad/url")]:
            self.archive([project(**changed)])
            with self.assertRaises(ValueError):
                self.build()
        self.archive(extra={"../outside.json": "{}"})
        with self.assertRaises(ValueError):
            self.build()

    def test_duplicate_project_and_organisation_rows_fail_closed(self):
        p = project("1")
        second = project("1", rcn="2")
        self.archive([p, second])
        with self.assertRaisesRegex(ValueError, "duplicate CORDIS project"):
            self.build()
        p["relations"]["associations"].append(copy.deepcopy(p["relations"]["associations"][0]))
        self.archive([p])
        with self.assertRaisesRegex(ValueError, "Duplicate CORDIS organisation"):
            self.build()

    def test_conflicting_activity_schema_and_missing_relevant_name_fail_closed(self):
        p = project()
        o = p["relations"]["associations"][0]
        o["relations"]["categories"].append({"code": "/HES", "attributes": {"classification": "organizationActivityType", "type": "relatedOrganizationActivityType"}})
        self.archive([p])
        with self.assertRaises(ValueError):
            self.build()
        o["relations"]["categories"].pop()
        o["legalName"] = ""
        self.archive([p])
        with self.assertRaises(ValueError):
            self.build()

    def test_missing_activity_role_and_termination_schema_fail_closed(self):
        for field in ["category_attributes", "type", "terminated"]:
            p = project()
            org = p["relations"]["associations"][0]
            if field == "category_attributes":
                org["relations"]["categories"][0].pop("attributes")
            else:
                org["attributes"].pop(field)
            self.archive([p])
            with self.assertRaises(ValueError):
                self.build()

    def test_unknown_association_type_cannot_hide_participation(self):
        p = project()
        p["relations"]["associations"][0]["contenttype"] = "organisation"
        self.archive([p])
        with self.assertRaisesRegex(ValueError, "Unknown CORDIS association"):
            self.build()

    def test_missing_country_cannot_silently_remove_scope(self):
        for changed in [None, ""]:
            p = project()
            address = p["relations"]["associations"][0]["address"]
            if changed is None:
                address.pop("country")
            else:
                address["country"] = changed
            self.archive([p])
            with self.assertRaisesRegex(ValueError, "Invalid country code"):
                self.build()

    def test_member_and_expanded_size_limits(self):
        self.archive()
        for limit in ["MAX_MEMBER_BYTES", "MAX_EXPANDED_BYTES", "MAX_ARCHIVE_BYTES"]:
            with patch("atlanticbridge.cordis_research." + limit, 1):
                with self.assertRaises(ValueError):
                    self.build()

    def test_project_member_limit_does_not_require_documentation_member(self):
        for extra in [None, {"documentation.zip": "ignored"}]:
            self.archive(extra=extra)
            with patch("atlanticbridge.cordis_research.MAX_ROWS", 0):
                with self.assertRaises(ValueError):
                    self.build()
            with patch("atlanticbridge.cordis_research.MAX_ROWS", 1):
                self.assertEqual(self.build()["summary"]["project_count"], 1)

    def test_deterministic_output_independent_of_member_order(self):
        self.archive([project("1"), project("2")])
        a = self.build()
        self.archive([project("2"), project("1")])
        b = self.build()
        # Byte-level ZIP identity changes, source-local project records do not.
        self.assertEqual(a["projects"], b["projects"])
        self.assertEqual(a["summary"], b["summary"])
        self.assertEqual(b, self.build())

    def test_cli_preserves_previous_output_on_failure_and_source_evidence(self):
        self.archive()
        receipt = self.root / "receipt.json"
        receipt.write_text(json.dumps(self.receipt))
        output = self.root / "output.json"
        output.write_text("previous")
        self.receipt["sha256"] = "0" * 64
        receipt.write_text(json.dumps(self.receipt))
        with self.assertRaises(ValueError):
            main(["--archive", str(self.path), "--receipt", str(receipt), "--output", str(output), "--as-of-date", "2026-11-09"])
        self.assertEqual(output.read_text(), "previous")
        self.archive()
        receipt.write_text(json.dumps(self.receipt))
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            main(["--archive", str(self.path), "--receipt", str(receipt), "--output", str(self.path), "--as-of-date", "2026-11-09"])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
