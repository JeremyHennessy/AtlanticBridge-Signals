"""Synthetic-only admission contract and client request-ceiling regressions."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import archive_admission as gate
import archive_evidence as archive
import test_archive_privacy

class Store:
    def __init__(self, state):
        self.state=deepcopy(state);self.revision='a'*40;self.writes=0
    def load(self):return self.revision,deepcopy(self.state)
    def compare_and_swap(self, revision, state):
        self.writes+=1
        if revision != self.revision:raise ValueError('conflict')
        self.state=deepcopy(state);self.revision='b'*40
        return self.revision

class AdmissionTests(unittest.TestCase):
    def ready(self):
        return dict(schema=1,repository=gate.REPOSITORY,status='ready',updated_at=100,
                    window_start=100,spent=0,owner=None)
    def test_reservation_requires_verified_durable_write(self):
        store=Store(self.ready());revision,state=gate.reserve(store,101,'1-1')
        self.assertEqual(revision,'b'*40);self.assertEqual(state,store.state)
        self.assertEqual(state['spent'],48);self.assertEqual(store.writes,1)
    def test_repeated_concurrent_or_crashed_run_cannot_enter(self):
        store=Store(self.ready());gate.reserve(store,101,'1-1')
        for owner in ('1-1','1-2','2-1'):
            for now in (101,3701,1000000):
                with self.assertRaises(gate.AdmissionError):gate.reserve(store,now,owner)
        self.assertEqual(store.writes,1)
    def test_missing_corrupt_stale_rollback_and_unknown_state(self):
        bad=[None,{},'SECRET',dict(self.ready(),schema=True),dict(self.ready(),spent=True),
             dict(self.ready(),status='unknown'),dict(self.ready(),owner='unexpected'),
             dict(self.ready(),window_start=102),dict(self.ready(),updated_at=102),
             dict(self.ready(),repository='other'),dict(self.ready(),spent=49),
             dict(self.ready(),extra='data')]
        for state in bad:
            with self.subTest(state=state),self.assertRaises(gate.AdmissionError):gate.reserve(Store(state),101,'1-1')
        for now in (99,True):
            with self.assertRaises(gate.AdmissionError):gate.reserve(Store(self.ready()),now,'1-1')
    def test_push_conflict_unknown_outcome_and_readback_mismatch_stop(self):
        for mode in ('conflict','unknown','mismatch','unchanged'):
            store=Store(self.ready());original=store.compare_and_swap
            def cas(rev,state):
                if mode=='conflict':raise RuntimeError('SECRET')
                committed=original(rev,state)
                if mode=='unknown':raise RuntimeError('SECRET')
                if mode=='mismatch':store.state['spent']=0
                return rev if mode=='unchanged' else committed
            with patch.object(store,'compare_and_swap',side_effect=cas):
                with self.assertRaises(gate.AdmissionError) as caught:gate.reserve(store,101,'1-1')
            self.assertNotIn('SECRET',str(caught.exception))
            self.assertLessEqual(store.writes,1)
    def test_completion_never_refunds_and_failure_never_expires(self):
        reservation=gate.propose_reservation(self.ready(),101,'1-1')
        held=gate.propose_completion(reservation,200,'1-1',verified=False)
        for now in (200,3800,1000000):
            with self.assertRaises(gate.AdmissionError):gate.propose_reservation(held,now,'2-1')
        ready=gate.propose_completion(reservation,3000,'1-1',verified=True)
        self.assertEqual(ready['spent'],48)
        with self.assertRaises(gate.AdmissionError):gate.propose_reservation(ready,6599,'2-1')
        self.assertEqual(gate.propose_reservation(ready,6600,'2-1')['spent'],48)
        for owner,verified in [('2-1',True),('1-1',1)]:
            with self.assertRaises(gate.AdmissionError):gate.propose_completion(reservation,200,owner,verified=verified)
    def test_json_round_trip_preserves_hold(self):
        reservation=gate.propose_reservation(self.ready(),101,'1-1')
        with self.assertRaises(gate.AdmissionError):gate.reserve(Store(json.loads(json.dumps(reservation))),5000,'2-1')
    def test_client_cap_and_cached_success(self):
        client,seen=test_archive_privacy.PrivacyTests().client()
        for number in range(1,49):client.verify_private(archive.API+f'/releases/assets/{number}')
        client.verify_private(archive.API+'/releases/assets/1')
        self.assertEqual(len(seen),48)
        with self.assertRaises(archive.PrivacyCheckError) as caught:client.verify_private(archive.API+'/releases/assets/49')
        self.assertEqual(caught.exception.diagnostic['outcome'],'privacy_request_budget_exhausted')
        with self.assertRaises(archive.PrivacyCheckError):client.verify_private(archive.API+'/releases/assets/1')
        self.assertEqual(len(seen),48)
    def test_failure_latches_even_after_timer_or_cached_success(self):
        for code in (403,429,500):
            client,seen=test_archive_privacy.PrivacyTests().client(code)
            for url in (archive.API+'/releases/1',archive.API+'/releases/2'):
                with self.assertRaises(archive.PrivacyCheckError):client.verify_private(url)
            self.assertEqual(len(seen),1)
    def test_cancellation_reserves_and_latches(self):
        client,seen=test_archive_privacy.PrivacyTests().client(error=KeyboardInterrupt())
        with self.assertRaises(KeyboardInterrupt):client.verify_private(archive.API+'/releases/1')
        with self.assertRaises(archive.PrivacyCheckError):client.verify_private(archive.API+'/releases/1')
        self.assertEqual(client.privacy_request_count,1);self.assertEqual(len(seen),1)
    def test_matching_budget_is_not_claimed_as_integration(self):
        self.assertEqual(gate.BUDGET,archive.MAX_PRIVACY_REQUESTS)
        self.assertIn('from archive_durable import ArchiveRun',Path(archive.__file__).read_text())
    def test_two_writers_read_same_head_only_one_can_reserve(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        barrier=threading.Barrier(2);lock=threading.Lock();local=threading.local()
        class ConcurrentStore(Store):
            def load(inner):
                with lock:result=super(ConcurrentStore,inner).load()
                if not getattr(local,'read',False):
                    local.read=True;barrier.wait(timeout=5)
                return result
            def compare_and_swap(inner,revision,state):
                with lock:return super(ConcurrentStore,inner).compare_and_swap(revision,state)
        store=ConcurrentStore(self.ready())
        def attempt(owner):
            try:return gate.reserve(store,101,owner)
            except gate.AdmissionError:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(attempt,['1-1','2-1']))
        self.assertEqual(sum(result is not None for result in results),1)
        self.assertEqual(store.state['status'],'reserved')
    def test_concurrent_same_client_reserves_before_transport_and_deduplicates(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        client,seen=test_archive_privacy.PrivacyTests().client();barrier=threading.Barrier(8)
        original=client.privacy_opener.open
        def transport(*args,**kwargs):
            self.assertEqual(client.privacy_request_count,len(seen)+1)
            return original(*args,**kwargs)
        def attempt(_):
            barrier.wait(timeout=5);client.verify_private(archive.API+'/releases/1')
        with patch.object(client.privacy_opener,'open',side_effect=transport):
            with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(attempt,range(8)))
        self.assertEqual(len(seen),1);self.assertEqual(client.privacy_request_count,1)
    def test_unpersisted_commit_and_stale_readback_do_not_admit(self):
        for mode in ('unpersisted','stale'):
            store=Store(self.ready());initial=store.load();original=store.compare_and_swap
            def cas(revision,state):
                if mode=='stale':original(revision,state)
                return 'b'*40
            reads=iter([initial,initial])
            with patch.object(store,'compare_and_swap',side_effect=cas),patch.object(store,'load',side_effect=lambda:next(reads)):
                with self.assertRaises(gate.AdmissionError):gate.reserve(store,101,'1-1')
    def test_reserved_or_held_state_with_no_spend_is_invalid(self):
        for status in ('reserved','review_hold'):
            state=dict(self.ready(),status=status,owner='1-1')
            with self.assertRaises(gate.AdmissionError):gate.propose_completion(state,101,'1-1',verified=True)
    def test_store_exception_traceback_is_sanitized(self):
        import traceback
        store=Store(self.ready())
        with patch.object(store,'load',side_effect=RuntimeError('SECRET_SIGNED_URL')):
            try:gate.reserve(store,101,'1-1')
            except gate.AdmissionError as error:
                rendered=''.join(traceback.format_exception(type(error),error,error.__traceback__))
            else:self.fail('Admission unexpectedly allowed')
        self.assertNotIn('SECRET_SIGNED_URL',rendered)
    def test_completed_state_ages_out_after_delayed_daily_or_multiday_run(self):
        reservation=gate.propose_reservation(self.ready(),101,'1-1')
        completed=gate.propose_completion(reservation,200,'1-1',verified=True)
        for now in (200+86400+600,200+7*86400):
            with self.subTest(now=now):
                receipt=gate.reserve(Store(completed),now,'2-1')
                self.assertEqual(receipt[1]['status'],'reserved')
                self.assertEqual(receipt[1]['window_start'],now)
