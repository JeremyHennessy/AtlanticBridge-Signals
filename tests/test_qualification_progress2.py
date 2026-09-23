import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('q2',ROOT/'scripts/qualification_progress2.py')
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)
def load():return json.loads((ROOT/'ui/data/company-reviews.json').read_text())
class QualificationProgressTwoTests(unittest.TestCase):
    def setUp(self):self.data=load();self.rows={r['company_name']:r for r in self.data['decisions']}
    def test_remaining_sixteen_decisions_are_unchanged(self):
        rows=[r for r in self.data['decisions'] if r['company_name'] not in ('Cellcentric','Roquette','Sanofi','Nature Energy')]
        raw=json.dumps(rows,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'ddc66ba3d1c99c74d491564ab0700abaf5c0cab6344147b3ee8e062b7a1433ed')
    def test_cellcentric_entity_is_source_bound_not_parent_guess(self):
        r=self.rows['Cellcentric'];self.assertEqual(r['checks']['legal_identity'],'SUPPORTED')
        self.assertEqual(set(r['check_sources']['legal_identity']),{'cellcentric-contact-current','cellcentric-ised-importer-current'})
        self.assertEqual(r['checks']['corporate_group'],'UNKNOWN')
    def test_undated_burnaby_page_not_a_new_public_date(self):
        r=self.rows['Cellcentric'];self.assertEqual(r['checks']['current_status'],'SUPPORTED')
        self.assertIsNone(r['current_status_date']);self.assertIsNone(r['current_status_source_id'])
    def test_supplier_route_not_burnaby_contract(self):
        r=self.rows['Cellcentric'];self.assertIn('company-wide',r['reason']);self.assertIn('not proof of a Burnaby purchase',r['reason'])
    def test_dataset_licence_not_transferred(self):
        r=self.rows['Cellcentric'];self.assertEqual(r['checks']['source_reuse'],'UNKNOWN')
        self.assertIn('2023 CID dataset licence',r['reason']);self.assertIn('2024 table',r['reason'])
    def test_portage_does_not_qualify_winnipeg(self):
        r=self.rows['Roquette'];self.assertEqual(r['checks']['current_status'],'UNKNOWN')
        self.assertEqual(r['checks']['legal_identity'],'UNKNOWN');self.assertIsNone(r['current_status_date'])
        e=next(e for e in r['evidence'] if e['source_id']=='roquette-job-portage-20260904')
        self.assertEqual(e['source_publication_date'],'2026-09-04')
        self.assertNotIn(e['source_id'],r['check_sources']['current_status'])
    def test_reuse_restriction_has_its_own_source(self):
        r=self.rows['Roquette'];self.assertEqual(r['checks']['source_reuse'],'CONTRADICTED')
        self.assertEqual(r['check_sources']['source_reuse'],['roquette-legal-current'])
    def test_no_score_or_entry_or_qualification_promotion(self):
        self.assertEqual(self.data['decision_count'],20)
        for r in self.data['decisions']:
            self.assertEqual(r['decision'],'HOLD');self.assertFalse(r['first_entry_confirmed'])
            self.assertFalse(r['predictive_score_allowed']);self.assertFalse(r['independent_holdout'])
    def test_exact_proof_pinned(self):
        self.assertIn({'artifact_id':q.PROOF_ID,'archive_sha256':q.PROOF_SHA},self.data['proofs'])
    def test_wrong_proof_rejected_before_decision_mutation(self):
        spec=importlib.util.spec_from_file_location('builder',ROOT/'scripts/build_pilot_release.py')
        build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.zip';p.write_bytes(b'not accepted')
            with self.assertRaises(ValueError):q.apply(({},self.data,{}),p,build.archive,build.checked_report)
