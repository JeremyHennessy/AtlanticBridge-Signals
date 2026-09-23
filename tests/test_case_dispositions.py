import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def load(path):return json.loads((ROOT/path).read_text())
class CaseDispositionTests(unittest.TestCase):
    def setUp(self):
        self.briefs=load('ui/data/case-briefs.json');self.b={b['company_name']:b for b in self.briefs['briefs']}
        self.r={r['company_name']:r for r in load('ui/data/company-reviews.json')['decisions']}
    def test_five_explicit_dispositions_are_not_five_leads(self):
        self.assertEqual(self.briefs['brief_count'],5);self.assertEqual(len(self.b),5)
        for b in self.b.values():
            self.assertFalse(b['qualified']);self.assertFalse(b['public_alert_allowed']);self.assertFalse(b['predictive_score_allowed']);self.assertIsNone(b['market_fit_score'])
    def test_each_brief_joins_its_exact_review_and_sources(self):
        for name,b in self.b.items():
            r=self.r[name];self.assertEqual(b['id'],r['id']);self.assertEqual(b['company_id'],r['project_id'] or r['id'])
            refs={e['source_id']:e for e in r['evidence']}
            for e in b['evidence']:self.assertEqual(e,refs[e['source_id']])
    def test_sanofi_production_is_not_inferred_from_inauguration(self):
        b=self.b['Sanofi'];r=self.r['Sanofi']
        self.assertEqual(b['disposition'],'INAUGURATED_PRODUCTION_PENDING');self.assertIn('early 2027',b['summary']);self.assertIn('regulatory approval',b['summary'])
        self.assertEqual(r['current_status_date'],'2026-09-16');self.assertEqual(r['current_status_source_id'],'sanofi-flu-inauguration-20260916');self.assertEqual(r['decision'],'HOLD')
    def test_nature_fiscal_period_not_invented_publication_date(self):
        b=self.b['Nature Energy'];e=b['evidence'][0]
        self.assertEqual(b['disposition'],'PARTNER_WITHDRAWAL_PROJECT_CONTINUATION');self.assertIsNone(b['latest_source_publication_date'])
        self.assertEqual(e['page'],52);self.assertIsNone(e['source_publication_date']);self.assertEqual(e['event_period'],'Fiscal year 2025')
        self.assertEqual(self.r['Nature Energy']['checks']['current_status'],'UNKNOWN');self.assertIsNone(self.r['Nature Energy']['current_status_date'])
    def test_nature_original_plan_and_acquisition_evidence_preserved(self):
        ids={e['source_id'] for e in self.r['Nature Energy']['evidence']}
        self.assertTrue({'nature-farnham-plan-20220315','nature-farnham-ised-20230320'}<=ids)
    def test_portage_stays_separate_and_source_use_restriction_remains(self):
        b=self.b['Roquette'];self.assertEqual(b['disposition'],'DIFFERENT_PROJECT_EVIDENCE');self.assertIn('separate',b['summary'])
        self.assertEqual(b['source_use_state'],'CONTRADICTED');self.assertEqual(self.r['Roquette']['checks']['current_status'],'UNKNOWN')
    def test_adyen_membership_is_not_first_entry_or_demand(self):
        b=self.b['Adyen Canada Ltd.'];self.assertEqual(b['disposition'],'MEMBERSHIP_NOT_ENTRY');self.assertEqual(b['source_use_state'],'UNKNOWN')
        self.assertFalse(self.r['Adyen Canada Ltd.']['first_entry_confirmed']);self.assertIn('commercial requirement',b['summary'])
    def test_cellcentric_global_supplier_route_is_not_local_contract(self):
        b=self.b['Cellcentric'];self.assertIn('company-wide',b['summary']);self.assertIn('not a Burnaby contract',b['summary']);self.assertIsNone(b['latest_source_publication_date'])
    def test_all_fifteen_historical_objects_unchanged(self):
        catalog=load('ui/data/reviewed-evidence.json')
        old=json.loads((ROOT/'ui/data/reviewed-evidence.json').read_text())
        self.assertEqual(catalog['project_count'],15)
        raw=json.dumps(catalog['projects'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'fc41103d68d5f218e3ace4cad626bf3ecd5daced695e72447102a54293a8577a')
    def test_two_new_archive_pins_are_required(self):
        spec=importlib.util.spec_from_file_location('archive',ROOT/'scripts/archive_evidence.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        self.assertEqual(mod.PINS[10718724645],'46f6e0853b6848cc10d5982e54bebeac2bf810e6e3ede19062b470e6c39a75a6')
        self.assertEqual(mod.PINS[10724109813],'6f5f5b169681f0bbc0b01d116f97cb3ee0a254385619f094cd101d8c98c415cc')
