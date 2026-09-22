import copy
import json
from pathlib import Path
import unittest

from atlanticbridge.outcome_qualification import qualify

ROOT=Path(__file__).resolve().parents[1]
MANIFEST=ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json'

class QualificationRound2Tests(unittest.TestCase):
    def setUp(self):
        self.manifest=json.loads(MANIFEST.read_text());self.discovery=[];self.evidence={}
        for case in self.manifest['cases']:
            self.discovery.append(dict(case['expected_discovery'],source_record_id=case['discovery_record_id'],
                source_id='investcanada-investment-cards-20260922',legal_identity_confirmed=False,
                first_entry_confirmed=False,independent_holdout=False,backtest_eligible=False,public_alert_allowed=False))
        for source in self.manifest['sources']:
            anchors=list(source['required_text'])
            for case in self.manifest['cases']:
                for event in case['events']:
                    if event['source_id']==source['id']:anchors.extend(event['required_text'])
                p=case.get('prior_presence_evidence')
                if p and p['source_id']==source['id']:anchors.extend(p['required_text'])
                n=case.get('named_entity_evidence')
                if n and n['source_id']==source['id']:anchors.append(n['name'])
            self.evidence[source['id']]=dict(source_id=source['id'],source_url=source['url'],evidence_text=' '.join(anchors),
                source_publication_date=source['reviewed_publication_date'],raw_sha256='b'*64,
                first_observed_at='2026-09-22T22:10:00Z',last_observed_at='2026-09-22T22:10:00Z')
    def run_review(self):return qualify(self.discovery,self.manifest,self.evidence)
    def test_nine_projects_are_documentary_only(self):
        r=self.run_review();self.assertEqual(r['summary']['documentary_reviewed_projects'],9)
        self.assertEqual(r['summary']['first_entry_training_labels'],0);self.assertEqual(r['summary']['new_public_alerts'],0)
        self.assertFalse(r['summary']['expansion_score_publication_allowed'])
    def test_all_are_eu_label_triage_not_control_proof(self):
        r=self.run_review();self.assertEqual(r['summary']['source_origin_triage'],{'EU27_SOURCE_LABEL_NOT_CONTROL_PROOF':9})
    def test_existing_presence_cases_are_not_first_entry(self):
        r=self.run_review();by={x['source_record_id']:x for x in r['records']}
        for key in ['investment-154','investment-177','investment-208','investment-176','investment-202']:
            self.assertEqual(by[key]['documentary_review']['prior_presence_status'],'SOURCE_REPORTS_EXISTING_PRESENCE')
            self.assertFalse(by[key]['documentary_review']['first_entry_confirmed'])
    def test_nature_control_change_does_not_rewrite_card_origin(self):
        r=self.run_review();row=next(x for x in r['records'] if x['source_record_id']=='investment-150')
        self.assertEqual(row['source_country_as_published'],'Denmark');self.assertFalse(row['legal_identity_confirmed'])
        self.assertIn('United Kingdom',row['documentary_review']['interpretation'])
    def test_roquette_card_facility_characterization_remains_qualified(self):
        r=self.run_review();row=next(x for x in r['records'] if x['source_record_id']=='investment-168')
        self.assertIn('does not independently establish',row['documentary_review']['interpretation'])
    def test_completed_by_is_not_exact_operation(self):
        r=self.run_review();row=next(x for x in r['records'] if x['source_record_id']=='investment-146')
        e=row['documentary_review']['events'][0];self.assertEqual(e['kind'],'PROJECT_COMPLETED_BY_DATE')
        self.assertEqual(e['date_basis'],'UPPER_BOUND_DAY');self.assertIsNone(e['first_operation_date'])
    def test_enel_operating_bound_not_first_entry(self):
        r=self.run_review();row=next(x for x in r['records'] if x['source_record_id']=='investment-148')
        self.assertEqual(row['documentary_review']['events'][0]['kind'],'OPERATING_BY_DATE')
        self.assertFalse(row['documentary_review']['first_entry_confirmed'])
    def test_missing_identity_document_blocks_nature_case(self):
        self.evidence.pop('nature-farnham-ised-20230320')
        with self.assertRaises(ValueError):self.run_review()
    def test_wrong_card_binding_requires_re_review(self):
        self.discovery[0]['location_text']='Vancouver, BC'
        with self.assertRaises(ValueError):self.run_review()
    def test_completed_event_cannot_claim_exact_first_operation(self):
        case=next(x for x in self.manifest['cases'] if x['id']=='siemens-greenview')
        case['events'][0]['first_operation_date']='2022-12-01'
        with self.assertRaises(ValueError):self.run_review()

if __name__=='__main__':unittest.main()
