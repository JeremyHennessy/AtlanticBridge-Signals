import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pilot_build',ROOT/'scripts/build_pilot_release.py')
build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
def load(name):return json.loads((ROOT/name).read_text())
class PilotReleaseTests(unittest.TestCase):
    def test_original_six_project_objects_are_exactly_preserved(self):
        d=load('ui/data/reviewed-evidence.json')
        raw=json.dumps(d['projects'][:6],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),build.SIX_SHA)
        self.assertEqual(d['project_count'],15)
    def test_fifteen_dossiers_remain_non_predictive_source_local_history(self):
        d=load('ui/data/reviewed-evidence.json')
        self.assertEqual(len({p['id'] for p in d['projects']}),15)
        for p in d['projects']:
            self.assertFalse(p['first_entry_confirmed']);self.assertFalse(p['legal_identity_confirmed']);self.assertFalse(p['public_alert_allowed'])
            byid={e['source_id']:e for e in p['evidence']}
            for event in p['events']:
                self.assertEqual(event['source_url'],byid[event['source_id']]['source_url'])
                self.assertEqual(event['raw_sha256'],byid[event['source_id']]['raw_sha256'])
    def test_twenty_triage_decisions_are_not_twenty_qualified_leads(self):
        d=load('ui/data/company-reviews.json');self.assertEqual(d['decision_count'],20)
        self.assertTrue(all(r['decision']=='HOLD' for r in d['decisions']))
        self.assertFalse(d['qualification_completed'])
        self.assertEqual(len({r['id'] for r in d['decisions']}),20)
        for r in d['decisions']:
            sources={e['source_id'] for e in r['evidence']}
            for k,v in r['checks'].items():
                self.assertTrue(set(r['check_sources'][k])<=sources)
                if v=='SUPPORTED':self.assertTrue(r['check_sources'][k])
    def test_fifty_source_local_targets_are_not_enrolled_or_a_holdout(self):
        d=load('reviews/pilot/operational-cohort-2026-09-22.json')
        self.assertEqual(d['target_count'],50);self.assertEqual(len(d['targets']),50)
        self.assertEqual(d['operational_monitoring_qualified_count'],0)
        self.assertIsNone(d['identity_qualified_current_company_count']);self.assertFalse(d['independent_holdout'])
        self.assertEqual(len({r['id'] for r in d['targets']}),50)
        for r in d['targets']:self.assertFalse(r['current_monitoring_qualified']);self.assertTrue(r['source_references'])
    def test_current_qualification_progress_is_source_bound_and_still_held(self):
        d=load('ui/data/company-reviews.json');by={r['company_name']:r for r in d['decisions']}
        adyen=by['Adyen Canada Ltd.']
        self.assertEqual(sum(v=='SUPPORTED' for v in adyen['checks'].values()),5)
        self.assertEqual(adyen['checks']['source_reuse'],'UNKNOWN')
        self.assertEqual(adyen['current_status_date'],'2026-07-01')
        self.assertEqual(adyen['current_status_source_id'],'adyen-current-affiliate-20260701')
        self.assertEqual(adyen['decision'],'HOLD')
        for name in ('Ubisoft','Accenture'):
            self.assertEqual(by[name]['checks']['current_status'],'SUPPORTED')
            self.assertEqual(by[name]['checks']['civilian_scope'],'SUPPORTED')
            self.assertIsNone(by[name]['current_status_date'])
            self.assertEqual(by[name]['decision'],'HOLD')
        self.assertEqual(by['Sanofi']['current_status_date'],'2026-09-16')
        self.assertEqual(by['Sanofi']['current_status_source_id'],'sanofi-flu-inauguration-20260916')
        gd=by['Giesecke+Devrient']
        self.assertEqual(gd['checks']['current_status'],'SUPPORTED')
        self.assertEqual(gd['checks']['civilian_scope'],'UNKNOWN')
        self.assertEqual(gd['current_status_date'],'2026-06-16')
        self.assertEqual(gd['decision'],'HOLD')
        self.assertEqual({p['artifact_id'] for p in d['proofs']},{build.DOC_ID,build.MON_ID,build.QUAL_ID,10729682735,10718724645,10724109813})

    def test_wrong_artifact_cannot_build_data(self):
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'wrong.zip';p.write_bytes(b'not an accepted source')
            with self.assertRaises(ValueError):build.archive(p,build.DOC_SHA)
