import copy
import json
from pathlib import Path
import sys
import unittest

from atlanticbridge.company_sources import Ledger, record
from atlanticbridge.outcome_qualification import qualify, origin_label_bucket
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from probe_outcome_qualification import prove_recovery

ROOT = Path(__file__).resolve().parents[1]


class QualificationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / 'reviews/commercial_validation/discovery-review-2026-09-22.json').read_text())
        self.discovery, self.evidence = [], {}
        for case in self.manifest['cases']:
            self.discovery.append(dict(case['expected_discovery'], source_record_id=case['discovery_record_id'],
                source_id='investcanada-investment-cards-20260922', legal_identity_confirmed=False,
                first_entry_confirmed=False, independent_holdout=False, backtest_eligible=False, public_alert_allowed=False))
        for source in self.manifest['sources']:
            anchors = list(source['required_text'])
            for case in self.manifest['cases']:
                for e in case['events']:
                    if e['source_id'] == source['id']: anchors.extend(e['required_text'])
                p = case.get('prior_presence_evidence')
                if p and p['source_id'] == source['id']: anchors.extend(p['required_text'])
                n = case.get('named_entity_evidence')
                if n and n['source_id'] == source['id']: anchors.append(n['name'])
            body = ' '.join(anchors)
            if source.get('section_anchor'):body = source['section_anchor'] + ' ' + body + ' ' + source['section_end_anchor']
            self.evidence[source['id']] = dict(source_id=source['id'], source_url=source['url'], evidence_text=body,
                source_publication_date=source['reviewed_publication_date'], raw_sha256='a'*64,
                first_observed_at='2026-09-22T20:00:00Z',last_observed_at='2026-09-22T20:00:00Z')

    def run_review(self):return qualify(self.discovery, self.manifest, self.evidence)

    def test_six_projects_documentary_not_training(self):
        result=self.run_review()['summary']
        self.assertEqual(result['documentary_reviewed_projects'],6)
        self.assertEqual(result['primary_documents_used'],8)
        self.assertEqual(result['first_entry_training_labels'],0)
        self.assertFalse(result['expansion_score_publication_allowed'])

    def test_missing_primary_document_blocks(self):
        self.evidence.pop(next(iter(self.evidence)))
        with self.assertRaises(ValueError):self.run_review()

    def test_unknown_discovery_identity_blocks(self):
        self.discovery[0]['company_candidate']='Different legal company'
        with self.assertRaises(ValueError):self.run_review()

    def test_wrong_source_namespace_blocks(self):
        self.discovery[0]['source_id']='lookalike'
        with self.assertRaises(ValueError):self.run_review()

    def test_revised_project_requires_new_review(self):
        self.discovery[1]['investment_type_as_published']='Diphtheria vaccine plant'
        with self.assertRaises(ValueError):self.run_review()

    def test_inauguration_not_production_date(self):
        e=self.manifest['cases'][1]['events'][1]
        e['first_operation_date']=e['date']
        with self.assertRaises(ValueError):self.run_review()

    def test_operating_by_cannot_claim_exact_day(self):
        self.manifest['cases'][2]['events'][0]['date_basis']='SOURCE_ASSERTED_DAY'
        with self.assertRaises(ValueError):self.run_review()

    def test_future_plan_is_not_actual_opening(self):
        self.manifest['cases'][0]['events'][0]['kind']='OPENING_REPORTED'
        with self.assertRaises(ValueError):self.run_review()

    def test_non_boolean_confirmations_block(self):
        self.manifest['cases'][0]['legal_identity_confirmed']='false'
        with self.assertRaises(ValueError):self.run_review()

    def test_calibration_cannot_be_holdout(self):
        self.manifest['cases'][0]['independent_holdout']=True
        with self.assertRaises(ValueError):self.run_review()

    def test_raw_provenance_missing_blocks(self):
        self.evidence[next(iter(self.evidence))]['raw_sha256']=''
        with self.assertRaises(ValueError):self.run_review()

    def test_wrong_document_date_blocks(self):
        self.evidence['sanofi-flu-inauguration-20260916']['source_publication_date']='2024-05-30'
        with self.assertRaises(ValueError):self.run_review()

    def test_wrong_facility_document_blocks(self):
        self.evidence['sanofi-flu-inauguration-20260916']['evidence_text']='Sanofi inaugurated a diphtheria tetanus pertussis facility'
        with self.assertRaises(ValueError):self.run_review()

    def test_changed_url_blocks(self):
        self.evidence['sanofi-flu-inauguration-20260916']['source_url']='https://example.org/other'
        with self.assertRaises(ValueError):self.run_review()

    def test_future_source_record_blocks(self):
        self.evidence['sanofi-flu-inauguration-20260916']['last_observed_at']='2026-01-01T00:00:00Z'
        with self.assertRaises(ValueError):self.run_review()

    def test_annual_page_other_section_cannot_support_claim(self):
        r=self.evidence['avanade-halifax-20220628'];r['evidence_text']='Avanade Canada Inc. has established and will grow a new Halifax office Tuesday June 28, 2022 unrelated text Media contact:'
        with self.assertRaises(ValueError):self.run_review()

    def test_duplicate_cases_block(self):
        self.manifest['cases'].append(copy.deepcopy(self.manifest['cases'][0]))
        with self.assertRaises(ValueError):self.run_review()

    def test_mixed_origin_not_automatic_europe(self):
        self.assertEqual(origin_label_bucket('Netherlands & South Korea'),'MIXED_SOURCE_LABEL_REQUIRES_REVIEW')
        self.assertEqual(origin_label_bucket('South Korea and United States'),'MIXED_SOURCE_LABEL_REQUIRES_REVIEW')
        self.assertEqual(origin_label_bucket('Atlantis'),'UNCLASSIFIED_SOURCE_LABEL')

    def test_unreviewed_rows_preserved(self):
        self.discovery.append(dict(self.discovery[-1], source_record_id='investment-fixture'))
        result=self.run_review()
        self.assertEqual(len(result['records']),7)
        self.assertEqual(result['summary']['unreviewed_projects'],1)

    def test_recovery_does_not_touch_source_ledger(self):
        source={'id':'fixture', 'kind':'article','url':'https://example.org/f','company':'Fixture'}
        rows=[record(source,'fixture','Fixture title','https://example.org/f')]
        ledger=Ledger(':memory:')
        try:
            ledger.apply(source,rows,'2026-01-01T00:00:00Z','a'*64)
            before='\n'.join(ledger.db.iterdump())
            result=prove_recovery(ledger,source,rows,'a'*64)
            self.assertEqual(result['empty_window_restart_recovery_events'],0)
            self.assertEqual('\n'.join(ledger.db.iterdump()),before)
        finally:ledger.close()
