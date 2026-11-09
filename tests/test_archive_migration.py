"""Offline history migration protocol, synthetic exact-head store."""
from copy import deepcopy
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import archive_durable as d
import archive_migration as m
import base64
import json
import re

def ready():
    return dict(schema=1, repository=d.gate.REPOSITORY, status='ready', updated_at=100,
                window_start=100, spent=0, owner=None)


class Server:
    def __init__(self):
        self.head = 'a' * 40
        self.files = {d.STATE: d.encode(ready()), 'checkpoint.json': 'UNRELATED',
                      'archive-health.json': 'OLD_HEALTH', 'archive-manifests/old.json': 'HISTORY'}
        self.calls = []
        self.counter = 0
        self.mode = None
        self.lock = threading.Lock()

    def __call__(self, query, variables):
        with self.lock:
            self.calls.append((query, deepcopy(variables)))
            if query.startswith('mutation'):
                request = variables['input']
                if self.mode == 'denied':
                    raise RuntimeError('SECRET')
                if request['expectedHeadOid'] != self.head:
                    raise RuntimeError('CONFLICT_SECRET')
                self.counter += 1
                self.head = format(self.counter, '040x')
                for row in request['fileChanges']['additions']:
                    self.files[row['path']] = base64.b64decode(row['contents']).decode()
                if self.mode == 'uncertain':
                    raise RuntimeError('SECRET_COMMITTED')
                return {'createCommitOnBranch': {'commit': {'oid': self.head}}}
            fields = re.findall(r'(f\d+):file\(path:("[^"]+")\)', query)
            target = {'oid': self.head}
            for alias, path in fields:
                raw = self.files.get(json.loads(path))
                target[alias] = None if raw is None else {'mode': 33188, 'type': 'blob', 'object': {'text': raw, 'isTruncated': False}}
            if self.counter and self.mode == 'stale':
                target['oid'] = 'a' * 40
            if self.counter and self.mode == 'mismatch':
                target['f0']['object']['text'] += ' '
            return {'repository': {'ref': {'target': target}}}





class HistoryServer(Server):
    def __init__(self):
        super().__init__()
        self.files.pop(d.STATE)
        self.files['archive-attempt.json'] = d.encode({'status': 'FAILED', 'privacy_check': {'status': 403}})
        self.history = {}
        self.after_read = None

    def __call__(self, query, variables):
        if query.startswith('mutation'):
            self.history[self.head] = deepcopy(self.files)
            result = super().__call__(query, variables)
            self.history[self.head] = deepcopy(self.files)
            return result
        if 'object(expression:' in query:
            import json, re
            revision = json.loads(re.search(r'object\(expression:("[^"]+")\)', query)[1])
            old_head, old_files = self.head, self.files
            try:
                self.head, self.files = revision, self.history[revision]
                result = super().__call__(query, variables)
                return {'repository': {'object': result['repository']['ref']['target']}}
            finally:
                self.head, self.files = old_head, old_files
        result = super().__call__(query, variables)
        if self.after_read:
            callback, self.after_read = self.after_read, None
            callback()
        return result


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.server = HistoryServer()
        self.store = d.Store(self.server)
        self.proposal = m.plan(self.store, self.server.head, ['checkpoint.json', 'archive-manifests/old.json'])
        self.resolution = dict(schema='restriction-resolution-v1', repository=d.gate.REPOSITORY,
            expected_head=self.server.head, evidence_sha256=self.proposal['evidence_sha256'],
            restriction_resolved=True, stale_jobs_drained=True, reviewer='SYNTHETIC ONLY',
            evidence_reference='offline-fixture-not-live-resolution', resolved_at=3600, drained_at=0)
        self.approval = dict(schema='migration-approval-v1', repository=d.gate.REPOSITORY,
            expected_head=self.server.head, plan_sha256=m.digest(self.proposal),
            resolution_sha256=m.digest(self.resolution), scope=m.SCOPE, first_owner='22-1',
            approved_by='SYNTHETIC ONLY', authorization_reference='offline-fixture-not-live-approval',
            issued_at=3601, expires_at=4500)
        self.events = []

    def apply(self):
        return m.apply(self.store, self.proposal, self.resolution, self.approval, 3602)

    def run_archive(self, receipt=None, owner='22-1', now=3603, fail=False):
        def factory():
            self.events.append('factory')
            self.assertEqual(d.decode(self.server.files[d.STATE])['status'], 'reserved')
            return object()
        def work(client):
            self.events.append('archive')
            if fail:
                raise RuntimeError('403')
            return {'status': 'VERIFIED_DRAFT_COPY', 'items': []}
        return d.ArchiveRun(self.store, owner, lambda: now, migration_receipt=receipt).execute(factory, work)

    def test_preserves_exact_history_and_never_claims_privacy(self):
        before = deepcopy(self.server.files)
        receipt = self.apply()
        self.assertEqual(self.events, [])
        self.assertEqual(d.decode(self.server.files[d.STATE])['status'], 'migration_pending')
        for path, raw in before.items():
            self.assertEqual(self.server.files[path], raw)
        cert = d.decode(self.server.files[m.CERT])
        self.assertEqual(cert['plan'], self.proposal)
        self.run_archive(receipt)
        self.assertEqual(self.server.history[self.proposal['expected_head']], before)
        self.assertEqual(d.decode(self.server.files[m.CERT]), cert)
        self.assertEqual(self.events, ['factory', 'archive'])

    def test_missing_receipt_wrong_owner_expiry_and_replay(self):
        receipt = self.apply()
        for value, owner, now in [(None, '22-1',3603),(receipt,'23-1',3603),(receipt,'22-1',4500)]:
            with self.assertRaises(d.gate.AdmissionError):
                self.run_archive(value, owner, now)
        self.assertEqual(self.events, [])
        self.run_archive(receipt)
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive(receipt, now=999999)
        # Later normal success path retains prior adapter semantics.
        self.run_archive(None, '24-1', 8000)

    def test_altered_evidence_decisions_stale_head_and_no_authorization(self):
        cases = [
            lambda: self.proposal['evidence'].__setitem__('archive-attempt.json', '{}'),
            lambda: self.approval.__setitem__('plan_sha256', '0'*64),
            lambda: self.approval.__setitem__('expires_at',3602),
            lambda: self.approval.__setitem__('approved_by',''),
            lambda: self.approval.clear(),
            lambda: self.resolution.__setitem__('restriction_resolved',False),
            lambda: self.resolution.__setitem__('stale_jobs_drained',False),
            lambda: setattr(self.server,'head','b'*40),
            lambda: self.server.files.__setitem__('archive-attempt.json','TAMPER'),
        ]
        for change in cases:
            self.setUp(); change()
            with self.assertRaises(d.gate.AdmissionError):
                self.apply()
            self.assertEqual(self.server.counter, 0)

    def test_unknown_write_denial_and_readback_mismatch_never_return_receipt(self):
        for mode in ('denied','uncertain','stale','mismatch'):
            self.setUp(); self.server.mode = mode
            with self.assertRaises(d.gate.AdmissionError):
                self.apply()
            self.server.mode = None
            with self.assertRaises(d.gate.AdmissionError):
                self.run_archive()
            self.assertEqual(self.events, [])
            self.assertLessEqual(self.server.counter, 1)

    def test_reapplication_concurrency_and_pinned_tamper(self):
        receipt = self.apply()
        with self.assertRaises(d.gate.AdmissionError):
            self.apply()
        self.server.history[self.proposal['expected_head']]['archive-attempt.json'] = 'changed'
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive(receipt)
        self.setUp()
        self.server.after_read = lambda: setattr(self.server, 'head', 'c'*40)
        with self.assertRaises(d.gate.AdmissionError):
            self.apply()
        self.assertEqual(self.server.counter, 0)

    def test_legacy_success_missing_and_failure_states_are_preserved(self):
        for raw in (None, d.encode({'status':'VERIFIED_DRAFT_COPY'}), d.encode({'status':'FAILED'})):
            self.setUp()
            self.server.files['archive-attempt.json'] = raw
            self.proposal = m.plan(self.store,self.server.head)
            self.approval['plan_sha256'] = m.digest(self.proposal)
            self.resolution['evidence_sha256'] = self.proposal['evidence_sha256']
            self.approval['resolution_sha256'] = m.digest(self.resolution)
            receipt = self.apply()
            self.assertEqual(self.server.files['archive-attempt.json'],raw)
            self.run_archive(receipt)

    def test_crash_and_first_failure_do_not_unlock_on_timer(self):
        receipt = self.apply()
        runner = d.ArchiveRun(self.store,'22-1',lambda:3603,migration_receipt=receipt)
        def crash():
            raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            runner.execute(crash,lambda _:self.fail())
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive(receipt, now=999999)
        self.setUp(); receipt=self.apply()
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive(receipt,fail=True)
        self.assertIn(d.decode(self.server.files[d.STATE])['status'], ('review_hold', 'reserved'))
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive(None,'23-1',999999)

    def test_bounded_inputs_and_concise_audit_references(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'oversized'
            path.write_bytes(b' ' * 8193)
            with self.assertRaises(d.gate.AdmissionError):
                m.load_json(path, 8192)
        for value in ('x' * 513, 'secret\ntranscript'):
            self.approval['authorization_reference'] = value
            with self.assertRaises(d.gate.AdmissionError):
                self.apply()
        self.assertEqual(self.server.counter, 0)

    def test_clock_does_not_release_unresolved_restriction(self):
        self.resolution['drained_at'] = 100
        self.approval['resolution_sha256'] = m.digest(self.resolution)
        with self.assertRaises(d.gate.AdmissionError):
            self.apply()
        self.assertEqual(self.server.counter, 0)

    def test_two_migrators_one_cas_and_no_overwrite(self):
        outcomes = []
        def attempt():
            try:
                outcomes.append(self.apply())
            except d.gate.AdmissionError:
                outcomes.append(None)
        workers = [threading.Thread(target=attempt) for _ in range(2)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sum(x is not None for x in outcomes), 1)
        self.assertEqual(self.server.counter, 1)

    def test_crash_after_commit_has_no_ordinary_recovery(self):
        commit = self.store.commit
        def crash(*args):
            commit(*args)
            raise KeyboardInterrupt()
        self.store.commit = crash
        with self.assertRaises(KeyboardInterrupt):
            self.apply()
        self.store.commit = commit
        with self.assertRaises(d.gate.AdmissionError):
            self.run_archive()
        with self.assertRaises(d.gate.AdmissionError):
            self.apply()
        self.assertEqual(self.events, [])

    def test_receipt_and_current_evidence_tampering(self):
        for change in ('receipt', 'head', 'evidence'):
            self.setUp()
            receipt = self.apply()
            if change == 'receipt':
                receipt['certificate_sha256'] = '0' * 64
            elif change == 'head':
                self.server.head = 'd' * 40
            else:
                self.server.files['archive-health.json'] = 'ALTERED'
            with self.assertRaises(d.gate.AdmissionError):
                self.run_archive(receipt)
            self.assertEqual(self.events, [])

    def test_cli_exclusive_receipt_no_archive_callbacks(self):
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name, value in [('plan', self.proposal), ('resolution', self.resolution),
                                ('approval', self.approval)]:
                (directory / name).write_text(d.encode(value))
            output = directory / 'receipt'
            argv = ['archive_migration.py', 'apply']
            for name in ('plan', 'resolution', 'approval'):
                argv += ['--' + name, str(directory / name)]
            argv += ['--output', str(output)]
            with patch.object(sys, 'argv', argv), patch.object(d, 'GraphQL', return_value=self.server), patch.object(m.time, 'time', return_value=3602):
                m.main()
                self.assertEqual(d.decode(output.read_text())['first_owner'], '22-1')
                with self.assertRaises(FileExistsError):
                    m.main()
            self.assertEqual(self.server.counter, 1)
            self.assertEqual(self.events, [])

    def test_lost_success_ack_still_reconciles_only_complete_bundle(self):
        receipt = self.apply()
        def factory():
            self.server.mode = 'uncertain'
            return object()
        with self.assertRaises(d.gate.AdmissionError):
            d.ArchiveRun(self.store,'22-1',lambda:3603,migration_receipt=receipt).execute(
                factory,lambda _: {'status':'VERIFIED_DRAFT_COPY'})
        self.server.mode=None
        self.run_archive(None,'23-1',8000)


if __name__ == '__main__':
    unittest.main()
