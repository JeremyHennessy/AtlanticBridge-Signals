from __future__ import annotations
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from atlanticbridge.analyst_review import build_review_packet
from atlanticbridge.sources import nl_environmental_assessments as nl

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/nl_environmental_assessments/synthetic-projects.html"

class NLAssessmentTests(unittest.TestCase):
    def raw(self):
        return FIXTURE.read_bytes()

    def parsed(self, raw=None):
        return nl.parse_project_list(self.raw() if raw is None else raw)

    def collection(self, ids=None):
        return nl.build_fixture_collection(self.raw(), ids or ["009901", "9902", "9903", "9904", "9905", "9906", "9907", "9908"])

    def test_snapshot_binding_and_omitted_td_structure(self):
        p = self.parsed()
        self.assertEqual(p["rows_parsed"], 9)
        self.assertEqual(p["response_sha256"], hashlib.sha256(self.raw()).hexdigest())
        self.assertEqual(p["response_sha256"], nl.SYNTHETIC_FIXTURE_SHA256)
        self.assertTrue(p["synthetic_marker_reported"])
        self.assertEqual(p["source_bytes"], len(self.raw()))

    def test_leading_zero_registration_and_observed_url_are_preserved(self):
        r = self.parsed()["records"][0]
        self.assertEqual(r["registration_number"], "009901")
        self.assertEqual(r["record_id"], "https://www.gov.nl.ca/eccc/projects/project_009901/")
        self.assertEqual(r["project_url"], r["record_id"])
        observed = "https://WWW.GOV.NL.CA:443/eccc/projects/project_009901/"
        self.assertEqual(nl.approved_project_url(observed), observed)

    def test_six_stages_remain_assessment_specific(self):
        rows = self.parsed()["records"]
        for row in rows[:6]:
            self.assertEqual((row["stage_code"], row["stage_label"]), nl.STAGES[row["status_as_published"]])
        self.assertIn("not operational", rows[0]["stage_label"])
        self.assertIn("not construction completion", rows[1]["stage_label"])

    def test_unknown_stage_is_preserved_not_promoted(self):
        r = self.parsed()["records"][6]
        self.assertEqual(r["status_as_published"], "New source wording")
        self.assertEqual(r["stage_code"], "UNRECOGNIZED_ASSESSMENT_STATUS")
        self.assertIn("UNKNOWN_STATUS_PRESERVED", r["issues"])

    def test_missing_proponent_and_optional_prefix_are_not_guessed(self):
        rows = self.parsed()["records"]
        self.assertEqual(rows[1]["proponent_as_published"], "Invented North Example Inc.")
        self.assertIsNone(rows[3]["proponent_as_published"])
        self.assertIn("PROPONENT_NOT_STATED", rows[3]["issues"])
        self.assertIn("Énergie", rows[4]["proponent_as_published"])

    def test_multiple_or_missing_proponent_elements_fail(self):
        for changed in [
            self.raw().replace(b"<em>Proponent: Invented Example Works Ltd.</em>", b"<em>Invented A</em><em>Invented B</em>", 1),
            self.raw().replace(b"<em>Proponent: Invented Example Works Ltd.</em>", b"", 1),
        ]:
            with self.assertRaisesRegex(ValueError, "one proponent"):
                self.parsed(changed)

    def test_release_date_is_independent_of_current_stage(self):
        rows = self.parsed()["records"]
        self.assertEqual(rows[2]["status_as_published"], "Withdrawn")
        self.assertEqual(rows[2]["release_date"], "2026-06-01")
        self.assertEqual(rows[3]["release_date"], "2025-03-01")
        self.assertIsNone(rows[7]["release_date"])
        self.assertIn("RELEASE_DATE_MISSING", rows[7]["issues"])

    def test_conflicting_dates_are_retained_and_flagged(self):
        r = self.parsed(self.raw().replace(b"2026-10-01", b"2020-01-01"))["records"][1]
        self.assertEqual(r["release_date"], "2020-01-01")
        self.assertIn("RELEASE_PRECEDES_REGISTRATION_REVIEW_REQUIRED", r["issues"])

    def test_invalid_dates_do_not_silently_become_unknown(self):
        for bad in ["2026-02-30", "09/01/2026", "2026-9-01", "1899-01-01"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.parsed(self.raw().replace(b"2026-09-01", bad.encode()))
        for bad in [False, 0, [], {}]:
            with self.assertRaises(ValueError):
                nl.parse_source_date(bad)

    def test_registration_collisions_keep_both_url_identities(self):
        p = self.parsed()
        self.assertEqual(p["duplicate_registration_numbers"], ["9908"])
        rows = [r for r in p["records"] if r["registration_number"] == "9908"]
        self.assertEqual(len({r["record_id"] for r in rows}), 2)
        self.assertTrue(all("REGISTRATION_NUMBER_COLLISION_USE_OBSERVED_URL" in r["issues"] for r in rows))
        packet = build_review_packet([self.collection(["9908"])])
        self.assertEqual(len(packet["findings"]), 2)
        self.assertEqual(len({f["finding_id"] for f in packet["findings"]}), 2)

    def test_repeated_observed_url_is_rejected_not_deduplicated(self):
        with self.assertRaisesRegex(ValueError, "Duplicate NL observed"):
            self.parsed(self.raw().replace(b"project-9908-2/", b"project-9908/"))

    def test_url_is_identity_when_registration_number_is_corrected(self):
        before = self.parsed()["records"][0]
        after = self.parsed(self.raw().replace(b"<td>009901<td>", b"<td>009902<td>"))["records"][0]
        self.assertEqual(before["record_id"], after["record_id"])
        self.assertNotEqual(before["registration_number"], after["registration_number"])

    def test_unknown_absence_and_schema_drift_fail_closed(self):
        for raw in [b"<html>403 Forbidden</html>", b"<table class='dataTable'></table>",
                    self.raw().replace(b"Date Registered", b"Publication Date"),
                    self.raw()+self.raw()]:
            with self.assertRaises(ValueError):
                self.parsed(raw)

    def test_no_url_synthesis_or_unsafe_navigation(self):
        for url in ["http://www.gov.nl.ca/eccc/projects/project-1/", "https://user@www.gov.nl.ca/eccc/projects/project-1/",
                    "https://www.gov.nl.ca.evil.test/eccc/projects/project-1/", "https://www.gov.nl.ca/eccc/projects/project-1/?redirect=x",
                    "https://www.gov.nl.ca/eccc/projects/project-1/#x", "https://www.gov.nl.ca/other/", "javascript:alert(1)",
                    "https://www.gov.nl.ca/eccc/projects/%2e%2e/"]:
            self.assertIsNone(nl.approved_project_url(url))
        with self.assertRaisesRegex(ValueError, "Unsupported NL project link"):
            self.parsed(self.raw().replace(b"https://www.gov.nl.ca/eccc/projects/project_009901/", b"https://evil.test/project/"))

    def test_snapshot_and_field_bounds(self):
        for raw in [b"", "not bytes", b"x"*(nl.MAX_HTML_BYTES+1)]:
            with self.assertRaises(ValueError):
                self.parsed(raw)
        with self.assertRaises(ValueError):
            self.parsed(self.raw().replace(b"Invented recycling facility proposal", b"x"*4001))

    def test_only_pinned_invented_html_can_create_a_collection(self):
        for raw in [self.raw().replace(b'SYNTHETIC_NOT_REAL_SOURCE',b'LIVE'),
                    self.raw().replace(b"Invented recycling facility proposal",b"Real company claim")]:
            with self.assertRaisesRegex(ValueError, "reuse is gated"):
                nl.build_fixture_collection(raw, ["009901"])

    def test_record_and_metadata_forgery_cannot_keep_a_valid_hash(self):
        changes = [
            lambda c: c["records"][0].update(title="Real entity claim"),
            lambda c: c["records"][0].update(stage_label="Operating European-owned facility"),
            lambda c: c["records"][0]["issues"].clear(),
            lambda c: c.update(coverage="COMPLETE_VERIFIED_COVERAGE"),
            lambda c: c.update(source_license="Unconditional permission"),
            lambda c: c.update(retrieved_at="2026-11-06T12:00:00Z"),
        ]
        for change in changes:
            c = self.collection(["9908"]);change(c)
            with self.assertRaisesRegex(ValueError, "pinned invented"):
                build_review_packet([c])

    def test_origin_rights_and_identifier_gates(self):
        for key, value in [("fixture_only", False),("rights_status","AUTHORIZED"),
                           ("collection_execution","LIVE_HTTP_RESPONSE"),("response_sha256","a"*64)]:
            c = self.collection();c[key]=value
            with self.assertRaises(ValueError):
                build_review_packet([c])
        for ids in [[],[9902],[" 9902"],["9902","9902"],["x"],["1"]*21]:
            with self.assertRaises(ValueError):
                nl.build_fixture_collection(self.raw(),ids)

    def test_review_clocks_and_limits_are_not_expansion_claims(self):
        c = self.collection();before = deepcopy(c)
        p = build_review_packet([c],generated_at="2026-11-06T00:00:00Z")
        self.assertEqual(c,before)
        for f in p["findings"]:
            self.assertFalse(f["lead_eligible"]);self.assertFalse(f["lead_promotion_allowed"])
            self.assertEqual(f["evidence_class"],"FIXTURE_DEMONSTRATION_NOT_LIVE")
            self.assertEqual(f["source_record_date_kind"],"PROJECT_REGISTRATION_DATE")
            self.assertEqual(f["source_record_date"],f["event_date"])
            self.assertIsNone(f["published_date"]);self.assertIsNone(f["retrieved_at"])
            self.assertIn("indemnity",f["interpretation_limit"])
            self.assertEqual(f["source_facts"]["replacement relationship"],"Not inferred from the project table")
        self.assertFalse(p["lead_promotion_allowed"])

    def test_nl_provenance_cannot_be_relabelled_as_another_source(self):
        c = self.collection()
        c["source"] = "nova_scotia_awarded_public_tenders"
        for row in c["records"]:
            row.update(tender_id="invented", vendor="Invented", entity="Invented buyer")
        with self.assertRaisesRegex(ValueError, "relabelled"):
            build_review_packet([c])

    def test_unknown_selection_is_not_an_absence_proof(self):
        c = self.collection(["00000001"])
        self.assertEqual(c["records"],[])
        self.assertIn("NO_ABSENCE_PROOF",c["coverage"])
        self.assertIsNone(c["page_may_be_truncated"])

    def test_fixed_generator_uses_no_live_input_and_never_overwrites(self):
        spec=importlib.util.spec_from_file_location("nl_fixture_cli",ROOT/"scripts/build_nl_assessment_fixture.py")
        cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/"fixture.json"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["--output",str(p),"--registration","9908"]),0)
            self.assertEqual(len(json.loads(p.read_text())["findings"]),2)
            before=p.read_bytes()
            with self.assertRaises(FileExistsError), redirect_stdout(io.StringIO()):
                cli.main(["--output",str(p)])
            self.assertEqual(p.read_bytes(),before)

    def test_shipped_review_fixture_matches_current_builder(self):
        expected = json.loads((FIXTURE.parent/"synthetic-review-packet.json").read_text())
        actual = build_review_packet([self.collection()], generated_at="2026-11-06T00:00:00Z")
        self.assertEqual(actual, expected)

    def test_pinned_record_resource_is_packaged_and_matches_parser(self):
        self.assertEqual(nl._pinned_records(),self.parsed()["records"])
        self.assertIn('sources/nl_assessment_fixture_records.json',(ROOT/"pyproject.toml").read_text())

if __name__=="__main__":
    unittest.main()
