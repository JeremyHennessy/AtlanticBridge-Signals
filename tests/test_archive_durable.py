"""Synthetic GraphQL server model. No sockets, subprocesses, or GitHub writes."""
import base64
from copy import deepcopy
import io
import json
from pathlib import Path
import re
import sys
import threading
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import archive_durable as d
import archive_evidence as archive


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


class DurableTests(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.store = d.Store(self.server)
        self.runner = d.ArchiveRun(self.store, '1-1', lambda: 101)
        self.events = []

    def factory(self):
        self.events.append('factory')
        self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'reserved')
        self.assertEqual(len(self.server.calls), 3)  # load, CAS, independent readback
        return object()

    def work(self, client):
        self.events.extend(['inventory', 'create', 'download', 'upload', 'privacy'])
        return {'status': 'VERIFIED_DRAFT_COPY', 'items': ['synthetic']}

    def test_success_atomic_finalization_and_once_only(self):
        result = self.runner.execute(self.factory, self.work)
        self.assertEqual(self.server.counter, 2)
        self.assertEqual(self.server.files['checkpoint.json'], 'UNRELATED')
        self.assertEqual(self.server.files['archive-manifests/old.json'], 'HISTORY')
        self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'ready')
        self.assertEqual(json.loads(self.server.files['archive-health.json']), result)
        self.assertEqual(self.server.files['archive-health.json'], self.server.files['archive-manifests/1-1.json'])
        writes = [v['input'] for q, v in self.server.calls if q.startswith('mutation')]
        self.assertEqual(writes[1]['expectedHeadOid'], format(1, '040x'))
        self.assertEqual(len(writes[1]['fileChanges']['additions']), 5)
        self.assertEqual(writes[0]['branch'], {'repositoryNameWithOwner': d.gate.REPOSITORY, 'branchName': d.BRANCH})
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, self.work)
        # Process restart with same owner still fails even after cooldown.
        with self.assertRaises(d.gate.AdmissionError):
            d.ArchiveRun(self.store, '1-1', lambda: 100000).execute(self.factory, self.work)
        self.assertEqual(self.events.count('factory'), 1)

    def test_missing_bad_held_and_historical_denial_block_before_factory(self):
        for state in (None, '{}', d.encode(dict(ready(), status='review_hold', owner='2-1', spent=48)),
                      d.encode(dict(ready(), status='reserved', owner='2-1', spent=48)), '{"schema":1,"schema":1}'):
            self.server.files[d.STATE] = state
            with self.assertRaises(d.gate.AdmissionError):
                d.ArchiveRun(self.store, '1-1', lambda: 99999).execute(self.factory, self.work)
        self.server.files[d.STATE] = d.encode(ready())
        self.server.files['archive-attempt.json'] = d.encode({'status': 'FAILED', 'privacy_check': {'status': 403}})
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, self.work)
        self.assertEqual(self.events, [])
        self.assertEqual(self.server.counter, 0)

    def test_denied_uncertain_stale_mismatch_no_archive(self):
        for mode in ('denied', 'uncertain', 'stale', 'mismatch'):
            self.setUp()
            self.server.mode = mode
            with self.assertRaises(d.gate.AdmissionError):
                self.runner.execute(self.factory, self.work)
            self.assertEqual(self.events, [])
            self.assertLessEqual(self.server.counter, 1)

    def test_archive_failure_preserves_health_and_holds_forever(self):
        def fail(client):
            raise ValueError('SECRET_URL')
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, fail)
        self.assertEqual(self.server.files['archive-health.json'], 'OLD_HEALTH')
        self.assertNotIn('archive-manifests/1-1.json', self.server.files)
        self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'review_hold')
        with self.assertRaises(d.gate.AdmissionError):
            d.ArchiveRun(self.store, '2-1', lambda: 100000).execute(self.factory, self.work)

    def test_cancellation_keeps_reserved_no_finalization(self):
        for point in ('factory', 'work'):
            self.setUp()
            def die(*args):
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                self.runner.execute(die if point == 'factory' else self.factory,
                                    die if point == 'work' else self.work)
            self.assertEqual(self.server.counter, 1)
            self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'reserved')

    def test_concurrent_writer_during_archive_rejects_finalization(self):
        def work(client):
            self.server.head = 'c' * 40
            self.server.files['checkpoint.json'] = 'CONCURRENT'
            return self.work(client)
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, work)
        self.assertEqual(self.server.files['checkpoint.json'], 'CONCURRENT')
        self.assertEqual(self.server.files['archive-health.json'], 'OLD_HEALTH')
        self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'reserved')

    def test_uncertain_final_commit_never_retried_or_reported_success(self):
        def work(client):
            self.server.mode = 'uncertain'
            return self.work(client)
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, work)
        self.assertEqual(self.server.counter, 2)
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, self.work)
        self.assertEqual(self.server.counter, 2)

    def test_two_readers_same_head_only_one_enters(self):
        from concurrent.futures import ThreadPoolExecutor
        barrier = threading.Barrier(2)
        local = threading.local()
        def transport(query, variables):
            result = self.server(query, variables)
            if not query.startswith('mutation') and not getattr(local, 'first', False):
                local.first = True
                barrier.wait(timeout=5)
            return result
        def run(owner):
            try:
                return d.ArchiveRun(d.Store(transport), owner, lambda: 101).execute(
                    lambda: object(), lambda client: {'status': 'VERIFIED_DRAFT_COPY'})
            except d.gate.AdmissionError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, ['1-1', '2-1']))
        self.assertEqual(sum(item is not None for item in results), 1)
        self.assertEqual(self.server.counter, 2)

    def test_transport_errors_partial_data_redirects_and_bounds_sanitized(self):
        for payload in ({'errors': [{'message': 'SECRET'}], 'data': {}}, {'data': None},
                        {'data': {}, 'errors': ['SECRET']}):
            transport = d.GraphQL('fake-token')
            response = io.BytesIO(json.dumps(payload).encode())
            response.status = 200
            response.geturl = lambda: d.ENDPOINT
            with patch.object(transport.opener, 'open', return_value=response):
                with self.assertRaises(d.gate.AdmissionError) as error:
                    transport('query{}', {})
            self.assertNotIn('SECRET', str(error.exception))
        for status, url, raw in ((403, d.ENDPOINT, b'SECRET'), (200, 'https://elsewhere.test', b'{}'),
                                 (200, d.ENDPOINT, b'x' * (d.LIMIT + 1)),
                                 (200, d.ENDPOINT, b'{"data":{},"data":{}}')):
            transport = d.GraphQL('fake-token')
            response = io.BytesIO(raw); response.status = status; response.geturl = lambda: url
            with patch.object(transport.opener, 'open', return_value=response):
                with self.assertRaises(d.gate.AdmissionError): transport('query{}', {})
        with self.assertRaises(d.gate.AdmissionError): d.NoRedirect().redirect_request(None)

    def test_path_restriction_and_oversize_no_transport(self):
        for files in ({'checkpoint.json': 'overwrite'}, {d.STATE: 'x' * (d.LIMIT + 1)}):
            with self.assertRaises(d.gate.AdmissionError): self.store.commit('a' * 40, files)
        self.assertEqual(self.server.calls, [])

    def test_cli_has_no_legacy_unguarded_route_or_pr_execution(self):
        source = Path(archive.__file__).read_text().split('def main():')[1]
        self.assertIn('runner.execute(lambda: Client(token), run)', source)
        self.assertNotIn('--state-dir', source)
        workflow = (Path(archive.__file__).parents[1] / '.github/workflows/evidence-retention.yml').read_text()
        self.assertNotIn('git push', workflow)
        self.assertNotIn('git worktree', workflow)
        self.assertNotIn('feature/evidence-retention-20260922', workflow)
        self.assertIn("github.event_name != 'pull_request'", workflow)

    def test_lost_final_ack_new_run_requires_complete_bundle_and_cooldown(self):
        def work(client):
            self.server.mode = 'uncertain'
            return self.work(client)
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, work)
        self.server.mode = None
        with self.assertRaises(d.gate.AdmissionError):
            d.ArchiveRun(self.store, '2-1', lambda: 3700).execute(lambda: object(), self.work)
        result = d.ArchiveRun(self.store, '2-1', lambda: 3701).execute(lambda: object(), self.work)
        self.assertEqual(result['status'], 'VERIFIED_DRAFT_COPY')
        self.assertEqual(self.server.counter, 4)

    def test_corrupt_previous_final_bundle_never_admits(self):
        self.runner.execute(self.factory, self.work)
        initial = deepcopy(self.server.files)
        for path in ('archive-health.json', 'archive-manifests/1-1.json',
                     'archive-runs/1-1.json', d.STATE):
            self.server.files = deepcopy(initial)
            # Valid JSON alteration, not merely malformed input.
            document = json.loads(self.server.files[path])
            document['extra'] = 'tampered'
            self.server.files[path] = d.encode(document)
            with self.assertRaises(d.gate.AdmissionError):
                d.ArchiveRun(self.store, '2-1', lambda: 99999).execute(lambda: self.fail('admitted'), self.work)
        self.assertEqual(self.server.counter, 2)

    def test_final_readback_loss_never_retries(self):
        def work(client):
            self.server.mode = 'stale'
            return self.work(client)
        with self.assertRaises(d.gate.AdmissionError):
            self.runner.execute(self.factory, work)
        self.assertEqual(self.server.counter, 2)
        self.assertEqual(json.loads(self.server.files[d.STATE])['status'], 'ready')
        self.server.mode = None
        d.ArchiveRun(self.store, '2-1', lambda: 3701).execute(lambda: object(), self.work)
        self.assertEqual(self.server.counter, 4)

    def test_cli_output_reuse_and_symlink_rejected_before_state_transport(self):
        import tempfile
        import os
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            existing = root / 'existing'; existing.mkdir()
            link = root / 'link'; link.symlink_to(existing, target_is_directory=True)
            for destination in (existing, link / 'new'):
                with patch.object(sys, 'argv', ['archive', '--report-dir', str(destination)]), \
                     patch.object(d, 'GraphQL', side_effect=AssertionError('no transport')):
                    with self.assertRaises((RuntimeError, FileExistsError)):
                        archive.main()
            self.assertFalse((existing / 'new').exists())

    def test_wrong_tree_mode_and_partial_or_truncated_reads_deny(self):
        for change in ('mode', 'type', 'truncated', 'null'):
            def transport(query, variables):
                result = self.server(query, variables)
                entry = result['repository']['ref']['target']['f0']
                if change == 'mode': entry['mode'] = 40960
                if change == 'type': entry['type'] = 'tree'
                if change == 'truncated': entry['object']['isTruncated'] = True
                if change == 'null': entry['object']['text'] = None
                return result
            with self.assertRaises(d.gate.AdmissionError):
                d.Store(transport).read([d.STATE])

    def test_missing_prior_attempt_or_contradictory_success_denies(self):
        self.runner.execute(self.factory, self.work)
        original = self.server.files['archive-attempt.json']
        for raw in (None, d.encode(dict(json.loads(original), privacy_check={'status': 403})),
                    d.encode(dict(json.loads(original), error_type='PrivacyCheckError'))):
            self.server.files['archive-attempt.json'] = raw
            with self.assertRaises(d.gate.AdmissionError):
                d.ArchiveRun(self.store, '2-1', lambda: 99999).execute(lambda: self.fail('admitted'), self.work)
        self.assertEqual(self.server.counter, 2)
