"""Offline in-process coordinator integration and interrupted-phase coverage."""
import contextlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from atlanticbridge.automation.models import decode_batch
from atlanticbridge.automation.local_cycle import run_cycle, main, readback
from atlanticbridge.automation.review_notifications import ReviewJournal, snapshot
from atlanticbridge.automation.scheduler import OfflineScheduler
from atlanticbridge.automation.store import Store
from atlanticbridge.automation.workbench import Workbench
from test_automation_foundation import contract, body, NOW, LATER, THIRD


class LocalCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.foundation = self.root / 'foundation.sqlite'
        self.journal = self.root / 'review.sqlite'
        self.input = self.root / 'local.json'
        self.c = contract()
        self.input.write_bytes(body(self.c))
        with Store(self.foundation) as store:
            earlier = '2026-11-05T12:00:00Z'
            store.register(self.c, at=earlier, input_path=self.input)
            store.set_source_state('fixture', 'READY', at=earlier, actor='test')
            run = store.claim('fixture', at=earlier)
            store.complete(run, decode_batch(body(self.c, rows=[]), self.c), at=earlier)
        with ReviewJournal.initialize(self.journal) as review:
            review.register(self.foundation, plan_id='review', sources=['fixture'], since=NOW)

    def run_cycle(self, at=NOW, **kwargs):
        return run_cycle(self.foundation, self.journal, plan_id='review', clock=lambda: at, **kwargs)

    def counts(self):
        return readback(self.foundation, self.journal, 'review')

    def wsgi_get(self, route):
        app = Workbench(self.foundation, journal=self.journal)
        environ = dict(REMOTE_ADDR='127.0.0.1', HTTP_HOST='127.0.0.1:8765',
                       REQUEST_METHOD='GET', PATH_INFO=route, QUERY_STRING='',
                       HTTP_SEC_FETCH_SITE='same-origin')
        environ['wsgi.url_scheme'] = 'http'
        response=[]
        result=b''.join(app(environ,lambda status, headers: response.append(status)))
        self.assertTrue(response[0].startswith('200'), response)
        return json.loads(result)

    def test_updated_input_durable_work_history_and_wsgi_readback(self):
        first = self.run_cycle()
        self.assertEqual(first['status'], 'BOUNDED_PASS_COMPLETE')
        self.assertEqual(first['staging']['staged'], 1)
        item = self.wsgi_get('/api/items')['items'][0]
        with Store(self.foundation) as store:
            store.update_work_item(item['work_item_id'], expected_revision=1, status='ACTIVE',
                notes='Preserve analyst notes', due_date=None, needs_review=False, at=NOW, actor='test')
        self.input.write_bytes(body(self.c, rows=[dict(record_id='one', facts={'title':'Changed local fixture'},
                                                      event_date='2023-08-03', published_date='2023-08-04')]))
        second = self.run_cycle(LATER)
        self.assertEqual(second['status'], 'BOUNDED_PASS_COMPLETE')
        updated = self.wsgi_get('/api/items/' + item['work_item_id'])['item']
        self.assertEqual(updated['title'], 'Changed local fixture')
        self.assertEqual(updated['notes'], 'Preserve analyst notes')
        self.assertEqual(updated['status'], 'ACTIVE')
        self.assertTrue(updated['needs_review'])
        self.assertEqual(updated['origin'], 'INVENTED_FIXTURE')
        previews = self.wsgi_get('/api/previews')['previews']
        self.assertEqual(len(previews), 2)
        self.assertTrue(all(not p['lead_eligible'] and not p['delivered'] for p in previews))
        self.assertEqual(previews[-1]['event_kind'], 'RECORD_CONTENT_CHANGED')
        replay = self.run_cycle(LATER)
        self.assertEqual(replay['imports'], [])
        self.assertEqual(replay['staging']['staged'], 0)
        same = self.run_cycle(THIRD)
        self.assertEqual(same['readback']['evidence_events'], 2)
        self.assertEqual(same['readback']['review_packets'], 2)
        self.assertEqual(same['readback']['work_items'], 1)

    def test_invalid_request_rejected_before_writes(self):
        before = self.counts()
        for kwargs in ({'max_jobs':0},{'max_jobs':True},{'max_scan':1001},{'max_scan':False}):
            self.assertEqual(self.run_cycle(**kwargs)['status'],'REJECTED')
        self.assertEqual(run_cycle(self.foundation,self.journal,plan_id='missing',clock=lambda:NOW)['status'],'REJECTED')
        self.assertEqual(run_cycle(self.foundation,self.foundation,plan_id='review',clock=lambda:NOW)['status'],'REJECTED')
        self.assertEqual(self.counts(), before)

    def test_missing_files_never_created(self):
        missing = self.root/'secret-missing.sqlite'
        for foundation,journal in ((missing,self.journal),(self.foundation,missing)):
            result=run_cycle(foundation,journal,plan_id='review',clock=lambda:NOW)
            self.assertEqual(result['status'],'REJECTED')
            self.assertNotIn('secret-missing',json.dumps(result))
            self.assertFalse(missing.exists())
        self.assertEqual(self.counts()['runs'],1)

    def test_invalid_journal_prevents_import(self):
        with sqlite3.connect(self.journal) as db: db.execute('CREATE TABLE unexpected(x)')
        self.assertEqual(self.run_cycle()['status'],'REJECTED')
        with snapshot(self.foundation,foundation=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],1)

    def test_symlink_and_hardlink_rejected(self):
        link=self.root/'alias.sqlite'; link.symlink_to(self.journal)
        self.assertEqual(run_cycle(self.foundation,link,plan_id='review',clock=lambda:NOW)['status'],'REJECTED')
        link.unlink(); link.hardlink_to(self.journal)
        self.assertEqual(self.run_cycle()['status'],'REJECTED')

    def test_plan_scope_never_imports_unrelated_ready_source(self):
        with Store(self.foundation) as store:
            store.register(contract('other'),at=NOW,input_path=self.root/'missing.json')
            store.set_source_state('other','READY',at=NOW,actor='test')
        result=self.run_cycle()
        self.assertEqual([r['source_id'] for r in result['imports']],['fixture'])
        with snapshot(self.foundation,foundation=True) as db:
            self.assertEqual(db.execute("SELECT last_attempt_at FROM sources WHERE source_id='other'").fetchone()[0],None)

    def test_paused_source_not_resumed_or_imported(self):
        with Store(self.foundation) as store: store.set_source_state('fixture','PAUSED',at=NOW,actor='test')
        result=self.run_cycle()
        self.assertEqual(result['imports'],[])
        self.assertEqual(result['readback']['work_items'],0)

    def test_staging_failure_keeps_import_and_retry_catches_up(self):
        with patch.object(ReviewJournal,'stage',side_effect=OSError('/private/secret')):
            failed=self.run_cycle()
        self.assertEqual(failed['status'],'PARTIAL')
        self.assertEqual(failed['phase'],'STAGING')
        self.assertNotIn('secret',json.dumps(failed))
        self.assertEqual(failed['readback']['work_items'],1)
        self.assertEqual(failed['readback']['review_packets'],0)
        result=self.run_cycle()
        self.assertEqual(result['imports'],[])
        self.assertEqual(result['staging']['staged'],1)

    def test_readback_failure_does_not_rollback_stage(self):
        with patch('atlanticbridge.automation.local_cycle.readback',side_effect=OSError('secret')):
            result=self.run_cycle()
        self.assertEqual(result['phase'],'READBACK')
        self.assertEqual(result['status'],'PARTIAL')
        self.assertIsNone(result['readback'])
        self.assertEqual(self.counts()['review_packets'],1)
        self.assertEqual(self.run_cycle()['staging']['staged'],0)

    def test_interrupt_after_import_is_durable_and_recoverable(self):
        with patch.object(ReviewJournal,'stage',side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.run_cycle()
        self.assertEqual(self.counts()['work_items'],1)
        self.assertEqual(self.run_cycle()['staging']['staged'],1)

    def test_bounds_and_review_backlog(self):
        self.input.write_bytes(body(self.c,rows=[dict(record_id=str(n),facts={'title':str(n)}) for n in range(3)]))
        first=self.run_cycle(max_scan=1,max_jobs=1)
        self.assertEqual(first['staging']['staged'],1)
        self.assertTrue(first['staging']['has_more'])
        self.assertEqual(self.run_cycle(max_scan=1)['readback']['review_packets'],2)
        last=self.run_cycle(max_scan=1)
        self.assertEqual(last['readback']['review_packets'],3)
        self.assertFalse(last['staging']['has_more'])

    def test_source_failure_does_not_block_another_plan_source(self):
        with Store(self.foundation) as store:
            store.register(contract('broken'),at=NOW,input_path=self.root/'missing')
            store.set_source_state('broken','READY',at=NOW,actor='test')
        with ReviewJournal(self.journal) as review:
            review.register(self.foundation,plan_id='both',sources=['fixture','broken'],since=NOW)
        result=run_cycle(self.foundation,self.journal,plan_id='both',clock=lambda:NOW)
        self.assertEqual(result['status'],'PARTIAL')
        self.assertEqual(result['staging']['staged'],1)
        self.assertEqual({r['status'] for r in result['imports']},{'FAILED','SUCCESS'})

    def test_claim_exception_is_uncertain_not_invented_rollback(self):
        with patch.object(OfflineScheduler,'run_one',side_effect=OSError('private')):
            result=self.run_cycle()
        self.assertEqual(result['imports'][0]['status'],'UNKNOWN')
        self.assertEqual(result['status'],'PARTIAL')
        self.assertNotIn('private',json.dumps(result))

    def test_expired_lease_recovered_without_new_activation(self):
        with Store(self.foundation) as store: store.claim('fixture',at=NOW)
        held=self.run_cycle()
        self.assertEqual(held['imports'],[])
        self.assertEqual(held['readback']['running_runs'],1)
        expired=self.run_cycle(LATER)
        self.assertEqual(expired['status'],'PARTIAL')
        self.assertEqual(expired['imports'][0]['error_code'],'LEASE_EXPIRED')
        self.assertEqual(self.run_cycle(THIRD)['readback']['work_items'],1)

    def test_backward_time_rejected_without_import(self):
        self.run_cycle(LATER)
        before=self.counts()
        self.assertEqual(self.run_cycle(NOW)['status'],'REJECTED')
        self.assertEqual(self.counts(),before)

    def test_cli_success_failure_and_redaction(self):
        for plan, expected in [('review',0),('missing',1)]:
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                code=main(['--foundation',str(self.foundation),'--journal',str(self.journal),'--plan-id',plan])
            self.assertEqual(code,expected)
            self.assertNotIn(str(self.root),output.getvalue())
            self.assertEqual(json.loads(output.getvalue())['delivered'],0)

    def test_first_baseline_still_emits_no_review_event(self):
        fresh = self.root / 'fresh.sqlite'
        journal = self.root / 'fresh-review.sqlite'
        with Store(fresh) as store:
            store.register(self.c, at=NOW, input_path=self.input)
            store.set_source_state('fixture', 'READY', at=NOW, actor='test')
        with ReviewJournal.initialize(journal) as review:
            review.register(fresh, plan_id='review', sources=['fixture'], since=NOW)
        result = run_cycle(fresh, journal, plan_id='review', clock=lambda: NOW)
        self.assertEqual(result['status'], 'BOUNDED_PASS_COMPLETE')
        self.assertEqual(result['readback']['work_items'], 1)
        self.assertEqual(result['readback']['evidence_events'], 0)
        self.assertEqual(result['staging']['staged'], 0)

    def test_staging_commit_then_lost_result_is_partial_and_idempotent(self):
        original = ReviewJournal.stage
        def commit_then_fail(review, *args, **kwargs):
            original(review, *args, **kwargs)
            raise OSError('private path must not leak')
        with patch.object(ReviewJournal, 'stage', commit_then_fail):
            result = self.run_cycle()
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertIsNone(result['staging'])
        self.assertEqual(result['readback']['review_packets'], 1)
        self.assertEqual(self.run_cycle()['staging']['staged'], 0)

    def test_preflight_deleted_foundation_is_not_recreated(self):
        from atlanticbridge.automation.workbench import ExistingStore
        def removed(path):
            Path(path).unlink()
            return ExistingStore(path)
        with patch('atlanticbridge.automation.local_cycle.ExistingStore', side_effect=removed):
            result = self.run_cycle()
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['phase'], 'IMPORTS')
        self.assertFalse(self.foundation.exists())

    def test_concurrent_cycles_have_one_import_and_packet(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_cycle(), range(2)))
        self.assertTrue(all(r['status'] == 'BOUNDED_PASS_COMPLETE' for r in results),results)
        counts = self.counts()
        self.assertEqual(counts['runs'], 2)  # setup baseline plus exactly one import
        self.assertEqual(counts['review_packets'], 1)

    def test_job_limit_and_invalid_scheduler_scope(self):
        other = contract('second')
        input_path = self.root / 'second.json'; input_path.write_bytes(body(other))
        with Store(self.foundation) as store:
            store.register(other, at=NOW, input_path=input_path)
            store.set_source_state('second', 'READY', at=NOW, actor='test')
            for scope in ([], ['fixture','fixture'], ['../x'], 'fixture'):
                with self.assertRaises(ValueError):
                    OfflineScheduler(store, clock=lambda:NOW).run_due(source_ids=scope)
        with ReviewJournal(self.journal) as review:
            review.register(self.foundation, plan_id='both', sources=['fixture','second'], since=NOW)
        first = run_cycle(self.foundation,self.journal,plan_id='both',max_jobs=1,clock=lambda:NOW)
        self.assertEqual(len(first['imports']),1)
        second = run_cycle(self.foundation,self.journal,plan_id='both',max_jobs=1,clock=lambda:NOW)
        self.assertEqual(len(second['imports']),1)
        self.assertNotEqual(first['imports'][0]['source_id'],second['imports'][0]['source_id'])

    def test_plan_contract_mismatch_rejected_before_imports(self):
        alternate = self.root / 'alternate.sqlite'
        with Store(alternate) as store:
            store.register(contract(parser_version='different'), at=NOW, input_path=self.input)
            store.set_source_state('fixture','READY',at=NOW,actor='test')
        result = run_cycle(alternate,self.journal,plan_id='review',clock=lambda:NOW)
        self.assertEqual(result['status'],'REJECTED')
        with snapshot(alternate,foundation=True) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],0)
