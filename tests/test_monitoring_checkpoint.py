import copy
import json
from pathlib import Path
import tempfile
import unittest
from atlanticbridge.company_sources import Ledger, digest, record
from atlanticbridge.monitoring_checkpoint import checkpoint, restore, validate, save, health

SOURCE={'id':'fixture','kind':'article','company':'Fixture','url':'https://example.org/news'}
NOW='2026-09-22T20:00:00+00:00'
LATER='2026-09-22T21:00:00+00:00'

class MonitoringCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.ledger=Ledger(':memory:')
        self.rows=[record(SOURCE,'one','Canada fixture title','https://example.org/one',body='SECRET_TEST_BODY_NOT_FOR_PUBLIC_STATE')]
        self.ledger.apply(SOURCE,self.rows,NOW,'a'*64)
    def tearDown(self):self.ledger.close()
    def rehash(self,value):
        value['checksum']=digest({k:v for k,v in value.items() if k!='checksum'});return value
    def restored(self):
        ledger=Ledger(':memory:');restore(ledger,checkpoint(self.ledger));self.addCleanup(ledger.close);return ledger
    def test_public_state_contains_no_source_body_or_title(self):
        value=checkpoint(self.ledger);text=json.dumps(value)
        self.assertNotIn('SECRET_TEST_BODY',text);self.assertNotIn('Canada fixture title',text)
        self.assertNotIn('evidence_text',text);validate(value)
    def test_no_false_event_after_metadata_only_restore(self):
        self.assertEqual(self.restored().apply(SOURCE,self.rows,LATER,'a'*64),[])
    def test_actual_change_survives_process_restart(self):
        ledger=self.restored();changed=[dict(self.rows[0],title='Actually revised source')]
        events=ledger.apply(SOURCE,changed,LATER,'b'*64)
        self.assertEqual(len(events),1);self.assertEqual(events[0]['kind'],'RECORD_CHANGED')
        self.assertFalse(events[0]['public_alert_allowed'])
    def test_event_checkpoint_retains_no_text(self):
        ledger=self.restored();ledger.apply(SOURCE,[dict(self.rows[0],title='changed')],LATER,'b'*64)
        value=checkpoint(ledger);validate(value)
        self.assertNotIn('SECRET_TEST_BODY',json.dumps(value))
    def test_initial_observation_is_preserved_after_round_trip(self):
        ledger=self.restored();ledger.apply(SOURCE,self.rows,LATER,'a'*64)
        self.assertEqual(ledger.db.execute('SELECT first_seen FROM company_observations').fetchone()[0],NOW)
    def test_new_record_after_restart_requires_review(self):
        rows=self.rows+[record(SOURCE,'two','Another Canada record','https://example.org/two')]
        event=self.restored().apply(SOURCE,rows,LATER,'b'*64)[0]
        self.assertTrue(event['review_required']);self.assertEqual(event['kind'],'NEWLY_OBSERVED_RECORD')
    def test_missing_window_and_restart_do_not_reissue_old_record(self):
        ledger=self.restored();ledger.apply(SOURCE,[],LATER,'a'*64)
        other=Ledger(':memory:');self.addCleanup(other.close);restore(other,checkpoint(ledger))
        self.assertEqual(other.apply(SOURCE,self.rows,'2026-09-23T20:00:00Z','a'*64),[])
    def test_failed_source_leaves_accepted_state_intact(self):
        before=checkpoint(self.ledger)
        with self.assertRaises(ValueError):self.ledger.apply(SOURCE,self.rows,LATER,'b'*64,complete=False)
        self.assertEqual(checkpoint(self.ledger),before)
    def test_corrupt_checksum_rejected_before_restore(self):
        value=checkpoint(self.ledger);value['tables']['company_observations'][0]['first_seen']=LATER
        other=Ledger(':memory:');self.addCleanup(other.close)
        with self.assertRaises(ValueError):restore(other,value)
        self.assertEqual(other.db.execute('SELECT COUNT(*) FROM company_observations').fetchone()[0],0)
    def test_nonempty_database_never_overwritten(self):
        with self.assertRaises(ValueError):restore(self.ledger,checkpoint(self.ledger))
    def test_body_injection_rejected_even_with_valid_checksum(self):
        value=checkpoint(self.ledger);row=value['tables']['company_observations'][0]
        payload=json.loads(row['payload']);payload['evidence_text']='unexpected source text';row['payload']=json.dumps(payload)
        with self.assertRaises(ValueError):validate(self.rehash(value))
    def test_unknown_table_rejected(self):
        value=checkpoint(self.ledger);value['tables']['arbitrary']=[]
        with self.assertRaises(ValueError):validate(self.rehash(value))
    def test_backtest_promotion_rejected(self):
        value=checkpoint(self.ledger);value['historical_backtest_eligible']=True
        with self.assertRaises(ValueError):validate(self.rehash(value))
    def test_atomic_file_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'checkpoint.json';value=checkpoint(self.ledger);save(path,value)
            self.assertEqual(json.loads(path.read_text()),value);self.assertFalse(path.with_suffix('.tmp').exists())
    def test_repeated_same_day_runs_not_fourteen_successful_days(self):
        runs=[{'id':str(i),'finished_at':LATER,'sources':[{'id':'fixture','status':'OBSERVED'}]} for i in range(14)]
        result=health(checkpoint(self.ledger,runs=runs))
        self.assertEqual(result['successful_days'],1);self.assertFalse(result['operational_target_met'])
    def test_source_failure_is_degraded_not_zero(self):
        runs=[{'id':'failed','finished_at':LATER,'sources':[{'id':'fixture','status':'UNVERIFIED_SOURCE_FAILURE','records':None}]}]
        result=health(checkpoint(self.ledger,runs=runs))
        self.assertEqual(result['status'],'DEGRADED');self.assertIsNone(result['sources'][0]['records'])
        self.assertEqual(result['sources'][0]['last_success_at'],NOW)
    def test_baseline_is_not_live_monitoring(self):
        result=health(checkpoint(self.ledger));self.assertEqual(result['status'],'BASELINE_ONLY');self.assertIsNone(result['last_attempt_at'])
    def test_duplicate_run_identity_rejected(self):
        run={'id':'one','finished_at':LATER,'sources':[]}
        with self.assertRaises(ValueError):validate(checkpoint(self.ledger,runs=[run,run]))
