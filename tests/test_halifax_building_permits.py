from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from atlanticbridge.sources import halifax_building_permits as h
from atlanticbridge.analyst_review import build_review_packet

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/halifax_building_permits/invented-response.json"

class HalifaxPermitTests(unittest.TestCase):
    def response(self):
        return json.loads(FIXTURE.read_bytes())

    def parse(self, value=None):
        return h.parse_arcgis_response(json.dumps(self.response() if value is None else value).encode())

    def packet(self, kind="ui_observed"):
        return build_review_packet([h.build_pinned_collection(kind)],generated_at="2026-11-06T12:00:00Z")

    def test_pinned_ui_dates_amount_and_origin(self):
        packet=self.packet(); row=packet["findings"][0]; facts=row["source_facts"]
        self.assertEqual(row["source_record_id"],"BPCOM-2021-14795")
        self.assertEqual(row["event_date"],"2023-08-03")
        self.assertEqual(row["source_record_date_kind"],"PERMIT_ISSUANCE_DATE")
        self.assertEqual(row["evidence_class"],"UI_OBSERVED_NOT_API_VERIFIED")
        self.assertEqual(facts["observation date"],"2026-11-06")
        self.assertEqual(facts["estimated project value"],9331109)
        self.assertIsNone(facts["completion date"])
        self.assertIsNone(facts["currency"])
        self.assertIsNone(row["retrieved_at"])
        self.assertIsNone(row["published_date"])
        self.assertIsNone(row["api_query_url"])
        self.assertFalse(row["lead_eligible"])
        self.assertFalse(row["lead_promotion_allowed"])
        self.assertEqual(row["attribution"],h.ATTRIBUTION)
        self.assertEqual(row["license_url"],h.LICENSE_URL)

    def test_invented_origin_not_live(self):
        self.assertEqual(self.packet("invented")["findings"][0]["evidence_class"],"FIXTURE_DEMONSTRATION_NOT_LIVE")

    def test_every_envelope_field_bound(self):
        original=h.build_pinned_collection()
        for key in original:
            with self.subTest(key=key):
                changed=deepcopy(original);changed[key]="changed"
                with self.assertRaises((ValueError,TypeError)):
                    build_review_packet([changed])
        changed=deepcopy(original);changed["unexpected"]="arbitrary metadata"
        with self.assertRaises(ValueError): build_review_packet([changed])

    def test_every_record_field_bound(self):
        original=h.build_pinned_collection()
        for key in original["records"][0]:
            with self.subTest(key=key):
                changed=deepcopy(original);changed["records"][0][key]="changed"
                with self.assertRaises(ValueError): build_review_packet([changed])

    def test_relabelling_provenance_rejected(self):
        for clue in (h.DATASET_URL,h.LICENSE_URL,h.PINNED_SHA256,"BPCOM-2021-14795"):
            with self.subTest(clue=clue):
                with self.assertRaisesRegex(ValueError,"Halifax provenance"):
                    build_review_packet([{"source":"canada_federal_grants_contributions","records":[{"ref_number":clue}]}])

    def test_arbitrary_records_and_live_origin_forbidden(self):
        for kind in ("live",None,{},[]):
            with self.assertRaises((ValueError,TypeError)): h.build_pinned_collection(kind)
        changed=h.build_pinned_collection();changed["collection_execution"]="LIVE_HTTP_RESPONSE"
        with self.assertRaises(ValueError): build_review_packet([changed])

    def test_parser_allowlist_dates_coverage(self):
        obj=self.response();a=obj["features"][0]["attributes"]
        a.update(Civic_Number="999",Street_Name="PRIVATE",PID="123",Work_Description="PERSON",contact="SECRET")
        obj["features"][0]["geometry"]={"x":123,"y":456}
        result=self.parse(obj); row=result["records"][0]
        self.assertIsNone(row["issuance_date"])
        self.assertIn("+00:00",row["issuance_utc_instant"])
        self.assertIn("ASSUMPTION_NOT_LIVE_VERIFIED",row["date_interpretation"])
        self.assertIsNone(row["completion_utc_instant"])
        self.assertIn("NO_ABSENCE_PROOF",result["coverage"])
        self.assertFalse(result["transport_verified"])
        self.assertFalse(result["pagination_verified"])
        text=json.dumps(result)
        for value in ("PRIVATE","PERSON","SECRET","geometry","PID","Civic_Number"):
            self.assertNotIn(value,text)

    def test_errors_and_schema_drift_fail_closed(self):
        cases=[{}, {"error":{"code":400}}, {"features":[]}]
        for key in h.FIELDS:
            obj=self.response();obj["fields"]=[f for f in obj["fields"] if f["name"]!=key];cases.append(obj)
            obj=self.response();del obj["features"][0]["attributes"][key];cases.append(obj)
            obj=self.response();next(f for f in obj["fields"] if f["name"]==key)["type"]="unexpected";cases.append(obj)
        for obj in cases:
            with self.assertRaises(ValueError): self.parse(obj)

    def test_duplicate_and_missing_identities_fail(self):
        for ident in (None,"",12,True,"A"*33,"BPCOM-PERSON-NAME"):
            obj=self.response();obj["features"][0]["attributes"]["Permit_Number"]=ident
            with self.assertRaises(ValueError):self.parse(obj)
        obj=self.response();obj["features"].append(deepcopy(obj["features"][0]))
        with self.assertRaises(ValueError):self.parse(obj)

    def test_noncommercial_unrecognized_and_contradictory_quarantined(self):
        for key,value in (("Permit_Name","Residential"),("Permit_Name",None),("Type_of_Structure","Residential"),("Type_of_Structure",None),("Permit_Status","Complete"),("Permit_Number","BPRES-2099-00001")):
            obj=self.response();obj["features"][0]["attributes"][key]=value
            result=self.parse(obj);self.assertEqual(result["records"],[]);self.assertEqual(result["quarantined_count"],1)
            self.assertIn("NO_ABSENCE_PROOF",result["coverage"])

    def test_bad_numbers_and_dates_fail(self):
        for key in ("Estimated_Project_Value", "Date_of_Permit_Issuance"):
            for value in (True,"2023-08-03",float("inf"),float("nan"),{},[]):
                obj=self.response();obj["features"][0]["attributes"][key]=value
                with self.assertRaises(ValueError):self.parse(obj)
        obj=self.response();obj["features"][0]["attributes"]["Estimated_Project_Value"]=-1
        with self.assertRaises(ValueError):self.parse(obj)

    def test_nullable_dates_and_estimate_preserved(self):
        obj=self.response()
        for field in h.DATE_FIELDS:
            obj["features"][0]["attributes"][field]=None
        obj["features"][0]["attributes"]["Estimated_Project_Value"]=None
        row=self.parse(obj)["records"][0]
        self.assertIsNone(row["estimated_project_value"])
        for name in h.DATE_FIELDS.values():
            self.assertIsNone(row[name+"_date"])
            self.assertIsNone(row[name+"_utc_instant"])

    def test_transfer_flag_never_proves_coverage(self):
        for value in (None,False,True):
            obj=self.response();obj["exceededTransferLimit"]=value
            result=self.parse(obj);self.assertEqual(result["page_may_be_truncated"],value)
            self.assertEqual(result["coverage"],"UNKNOWN_INCOMPLETE_NO_ABSENCE_PROOF")
        obj=self.response();obj["exceededTransferLimit"]="false"
        with self.assertRaises(ValueError):self.parse(obj)
        obj=self.response();obj["features"]=[]
        self.assertIn("NO_ABSENCE_PROOF",self.parse(obj)["coverage"])

    def test_duplicate_json_and_oversized_input_rejected(self):
        for raw in (b'{"features":[],"features":[]}',b'not json',b'\xff',b' '*2000001):
            with self.assertRaises(ValueError):h.parse_arcgis_response(raw)

    def test_cli_new_file_only(self):
        spec=importlib.util.spec_from_file_location("halifax_cli",ROOT/"scripts/build_halifax_permit_pilot.py")
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"packet.json"
            args=["--output",str(out),"--generated-at","2026-11-06T12:00:00Z"]
            self.assertEqual(module.main(args),0)
            before=out.read_bytes()
            with self.assertRaises(FileExistsError):module.main(args)
            self.assertEqual(out.read_bytes(),before)

    def test_pinned_packet_has_no_excluded_fields(self):
        text=json.dumps(self.packet())
        for token in ("Civic_Number","Street_Name","PID","Work_Description","geometry"):
            self.assertNotIn(token,text)


    def test_shipped_review_fixtures_match_current_builder(self):
        for kind,name in (("ui_observed","ui-observed-review-packet.json"),("invented","invented-review-packet.json")):
            with self.subTest(kind=kind):
                expected=json.loads((FIXTURE.parent/name).read_text())
                self.assertEqual(self.packet(kind),expected)

    def test_pinned_json_types_are_strict(self):
        for change in (
            lambda c: c.update(fixture_only=0),
            lambda c: c.update(schema_version=True),
            lambda c: c["records"][0].update(is_new_signal_on_retrieval=0),
            lambda c: c["records"][0].update(estimated_project_value=9331109.0),
        ):
            c=h.build_pinned_collection();change(c)
            with self.assertRaises(ValueError):build_review_packet([c])

if __name__ == "__main__": unittest.main()
