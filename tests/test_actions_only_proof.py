"""PR proof reads are exact, fail-closed, and never consult releases."""
import io
import json
from pathlib import Path
import shlex
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import archive_evidence as a
import fetch_accepted_proof as cli


class ActionsOnlyProofTests(unittest.TestCase):
    def setUp(self):
        self.aid = 10724340100
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as z:
            z.writestr('raw/' + a.sha(b'evidence') + '.bin', b'evidence')
        self.raw = out.getvalue()
        self.info = {'id': self.aid, 'expired': False, 'workflow_run': {'id': 42}}
        self.metadata = a.API + f'/actions/artifacts/{self.aid}'
        self.urls = []
        # Test fixture digest only: production pins are never edited.
        self.addCleanup(patch.stopall)
        patch.dict(a.PINS, {self.aid: a.sha(self.raw)}).start()
        self.guards = []
        for target in ('urllib.request.OpenerDirector.open', 'urllib.request.urlopen',
                       'socket.create_connection', 'subprocess.Popen', 'os.system',
                       'archive_evidence.Client.verify_private'):
            guard = patch(target, side_effect=AssertionError('Forbidden network/process/privacy action')).start()
            self.guards.append(guard)

    def tearDown(self):
        for guard in self.guards:
            guard.assert_not_called()

    def client(self, metadata_status=200, metadata=None, zip_status=200, raw=None):
        client = Mock()
        client.pages.side_effect = AssertionError('Release enumeration forbidden')
        client.verify_private.side_effect = AssertionError('Privacy request forbidden')
        def request(url, **kwargs):
            self.urls.append(url)
            if url == self.metadata:
                self.assertEqual(kwargs, {'actions_only': True})
                return metadata_status, json.dumps(self.info if metadata is None else metadata).encode()
            if url == self.metadata + '/zip':
                self.assertEqual(kwargs, {'binary': True, 'actions_only': True})
                return zip_status, self.raw if raw is None else raw
            raise AssertionError('Non-Actions route: ' + url)
        client.request.side_effect = request
        self.addCleanup(client.pages.assert_not_called)
        self.addCleanup(client.verify_private.assert_not_called)
        return client

    def test_valid_original_retains_exact_bytes_and_provenance(self):
        info, raw = a.accepted_proof(self.client(), self.aid, actions_only=True)
        self.assertEqual(info, self.info)
        self.assertEqual(raw, self.raw)
        self.assertEqual(self.urls, [self.metadata, self.metadata + '/zip'])

    def test_expired_and_incomplete_or_mismatched_metadata_fail_before_zip(self):
        bad = [
            {}, [], None, {'id': self.aid}, dict(self.info, expired=True),
            dict(self.info, expired=None), dict(self.info, expired=0),
            dict(self.info, id=self.aid + 1), dict(self.info, id=str(self.aid)),
            dict(self.info, workflow_run=None), dict(self.info, workflow_run={}),
            dict(self.info, workflow_run={'id': None}),
            dict(self.info, workflow_run={'id': True}),
            dict(self.info, workflow_run={'id': 0}),
            {k:v for k,v in self.info.items() if k != 'expired'},
        ]
        for info in bad:
            with self.subTest(info=info):
                client = self.client(metadata=info)
                if info is None:
                    client.request.side_effect = lambda *args, **kwargs: (200, b'null')
                with self.assertRaises(ValueError):
                    a.accepted_proof(client, self.aid, actions_only=True)
                client.request.assert_called_once_with(self.metadata, actions_only=True)

    def test_missing_and_permission_metadata_fail_closed(self):
        for status in (404, 410, 401, 403, 429, 500):
            with self.subTest(status=status):
                client = self.client(metadata_status=status)
                with self.assertRaises(ValueError):
                    a.accepted_proof(client, self.aid, actions_only=True)
                client.request.assert_called_once()

    def test_missing_or_inaccessible_zip_fails_closed(self):
        for status in (404, 410, 401, 403, 429, 500):
            with self.subTest(status=status):
                client = self.client(zip_status=status)
                with self.assertRaises(ValueError):
                    a.accepted_proof(client, self.aid, actions_only=True)
                self.assertEqual(client.request.call_count, 2)

    def test_corrupt_checksum_fails_closed(self):
        with self.assertRaisesRegex(ValueError, 'checksum'):
            a.accepted_proof(self.client(raw=b'corrupt'), self.aid, actions_only=True)

    def test_invalid_zip_with_matching_digest_fails_closed(self):
        with patch.dict(a.PINS, {self.aid: a.sha(b'not a zip')}):
            with self.assertRaises(zipfile.BadZipFile):
                a.accepted_proof(self.client(raw=b'not a zip'), self.aid, actions_only=True)

    def test_unsafe_zip_and_raw_corruption_still_fail(self):
        for name in ('../unsafe', 'raw/' + '0'*64 + '.bin', 'metadata.json'):
            with self.subTest(name=name):
                out = io.BytesIO()
                with zipfile.ZipFile(out, 'w') as z:
                    z.writestr(name, b'evidence')
                raw = out.getvalue()
                with patch.dict(a.PINS, {self.aid: a.sha(raw)}):
                    with self.assertRaises(ValueError):
                        a.accepted_proof(self.client(raw=raw), self.aid, actions_only=True)

    def test_malformed_metadata_fails_closed(self):
        client = self.client()
        client.request.side_effect = lambda *args, **kwargs: (200, b'invalid JSON')
        with self.assertRaises(ValueError):
            a.accepted_proof(client, self.aid, actions_only=True)

    def test_unknown_pin_never_requests(self):
        client = self.client()
        with self.assertRaises(ValueError):
            a.accepted_proof(client, 999, actions_only=True)
        client.request.assert_not_called()

    def test_transport_exception_never_falls_back(self):
        for error in (TimeoutError('timeout'), OSError('unavailable')):
            client = self.client()
            client.request.side_effect = error
            with self.assertRaises(type(error)):
                a.accepted_proof(client, self.aid, actions_only=True)

    def test_default_still_recovers_exact_retained_release_bytes(self):
        client = Mock()
        client.request.side_effect = [(404, b''), (200, self.raw)]
        name = f'artifact-{self.aid}-{a.sha(self.raw)[:16]}.zip'
        client.pages.side_effect = [
            [{'id': 1, 'tag_name': 'evidence-v1-test', 'draft': True, 'published_at': None}],
            [{'id': 7, 'name': name}]]
        info, raw = a.accepted_proof(client, self.aid)
        self.assertEqual(raw, self.raw)
        self.assertIsNone(info['workflow_run']['id'])
        client.request.assert_any_call(a.API + '/releases/assets/7', binary=True)

    def test_cli_forwards_explicit_mode_and_default(self):
        for flag, expected in ((['--actions-only'], True), ([], False)):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'proof.zip'
                with patch.object(sys, 'argv', ['fetch', '--artifact-id', str(self.aid),
                                               '--output', str(path)] + flag), \
                     patch.object(cli, 'Client') as constructor, \
                     patch.object(cli, 'accepted_proof', return_value=(self.info, self.raw)) as fetch:
                    cli.main()
                    fetch.assert_called_once_with(constructor.return_value, self.aid, actions_only=expected)
                    self.assertEqual(path.read_bytes(), self.raw)

    def test_cli_failure_leaves_no_proof_and_existing_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'proof.zip'
            with patch.object(sys, 'argv', ['fetch', '--actions-only', '--artifact-id', str(self.aid),
                                           '--output', str(path)]), \
                 patch.object(cli, 'Client'), \
                 patch.object(cli, 'accepted_proof', side_effect=ValueError('unavailable')) as fetch:
                with self.assertRaises(ValueError): cli.main()
                self.assertFalse(path.exists())
                path.write_bytes(b'existing')
                fetch.reset_mock()
                with self.assertRaises(ValueError): cli.main()
                fetch.assert_not_called()
                self.assertEqual(path.read_bytes(), b'existing')

    def test_all_pilot_downloads_use_actions_only_and_keep_accepted_ids(self):
        workflow = (ROOT / '.github/workflows/pilot-release-proof.yml').read_text()
        calls = [shlex.split(line.strip()) for line in workflow.splitlines()
                 if line.strip().startswith('python scripts/fetch_accepted_proof.py ')]
        self.assertEqual(len(calls), 6)
        ids = []
        for call in calls:
            self.assertEqual(call.count('--actions-only'), 1)
            ids.append(int(call[call.index('--artifact-id') + 1]))
        self.assertEqual(ids, [10724340100, 10720884358, 10729310481,
                               10729682735, 10718724645, 10724109813])
        self.assertIn("'tests/test_actions_only_proof.py'", workflow)

    def test_actions_only_initial_transport_is_exact_read_only_and_authenticated(self):
        client = a.Client('TEST')
        for url, kwargs in [
            (a.API + '/releases', {}),
            (a.API + '/releases/assets/7', {'binary': True}),
            ('https://github.com/repo/releases/download/x', {'binary': True}),
            (self.metadata + '?redirect=release', {}),
            (self.metadata + '#fragment', {}),
            (self.metadata, {'method': 'POST'}),
            (self.metadata, {'body': b'data'}),
            (self.metadata, {'auth': False}),
            (self.metadata, {'binary': True}),
            (self.metadata + '/zip', {}),
        ]:
            with self.subTest(url=url, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    client.request(url, actions_only=True, **kwargs)

    def test_explicit_transport_uses_scoped_opener_only(self):
        from unittest.mock import MagicMock
        client = a.Client('TEST')
        client.opener.open = Mock(side_effect=AssertionError('Default opener forbidden'))
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'fixture'
        for binary in (False, True):
            with patch.object(a.urllib.request, 'build_opener') as build:
                build.return_value.open.return_value = response
                self.assertEqual(client.request(self.metadata + ('/zip' if binary else ''),
                                                binary=binary, actions_only=True), (200, b'fixture'))
                handler = build.call_args.args[0]
                self.assertIsInstance(handler, a.ActionsOnlyRedirect)
                self.assertEqual(handler.binary, binary)
        client.opener.open.assert_not_called()

    def test_redirects_to_release_or_unknown_hosts_are_refused_before_dispatch(self):
        req = a.urllib.request.Request(self.metadata + '/zip',
                                       headers={'Authorization': 'Bearer TEST'})
        targets = [
            a.API + '/releases/assets/7',
            'https://github.com/owner/repo/releases/download/tag/proof.zip',
            'https://release-assets.githubusercontent.com/asset',
            'https://evil.example/proof.zip',
            'https://abc.blob.core.windows.net.evil.example/proof.zip',
            'https://a.b.blob.core.windows.net/proof.zip',
            'https://blob.core.windows.net/proof.zip',
            'https://abc.blob.core.windows.net:444/proof.zip',
            'http://abc.blob.core.windows.net/proof.zip',
            'https://user:pass@abc.blob.core.windows.net/proof.zip',
            'https://abc.blob.core.windows.net/proof.zip#fragment',
        ]
        for binary in (False, True):
            handler = a.ActionsOnlyRedirect(binary=binary)
            handler.parent = Mock()
            for target in targets:
                with self.subTest(binary=binary, target=target):
                    with self.assertRaises(ValueError):
                        handler.http_error_302(req, Mock(), 302, 'Found', {'location': target})
            handler.parent.open.assert_not_called()

    def test_metadata_redirect_to_allowed_storage_still_refused(self):
        req = a.urllib.request.Request(self.metadata)
        handler = a.ActionsOnlyRedirect(binary=False)
        handler.parent = Mock()
        with self.assertRaises(ValueError):
            handler.http_error_302(req, Mock(), 302, 'Found',
                                  {'location': 'https://abc.blob.core.windows.net/proof.zip'})
        handler.parent.open.assert_not_called()

    def test_allowed_zip_redirects_drop_credentials_including_second_hop(self):
        req = a.urllib.request.Request(self.metadata + '/zip',
                                       headers={'Authorization': 'Bearer TEST'})
        handler = a.ActionsOnlyRedirect(binary=True)
        for target in ('https://abc123.blob.core.windows.net/proof.zip?signature=fixture',
                       'https://results-receiver.actions.githubusercontent.com/proof.zip'):
            redirected = handler.redirect_request(req, None, 302, '', {}, target)
            self.assertIsNone(redirected.get_header('Authorization'))
            second = handler.redirect_request(redirected, None, 302, '', {}, target)
            self.assertIsNone(second.get_header('Authorization'))


    def test_malformed_redirect_diagnostics_never_leak_url_secrets(self):
        req = a.urllib.request.Request(self.metadata + '/zip')
        handler = a.ActionsOnlyRedirect(binary=True)
        handler.parent = Mock()
        targets = [
            'https://abc.blob.core.windows.net:SIGNED_SECRET/x?sig=QUERY_SECRET',
            'https://USER:PASSWORD@abc.blob.core.windows.net：443/x',
            'https://[SIGNED_SECRET/x?sig=QUERY_SECRET',
        ]
        for target in targets:
            callbacks = [lambda: handler.redirect_request(req, None, 302, '', {}, target)]
            for code in (301, 302, 303, 307, 308):
                callbacks.append(lambda code=code: getattr(handler, f'http_error_{code}')(
                    req, Mock(), code, 'Found', {'location': target}))
            for callback in callbacks:
                with self.subTest(target=target):
                    with self.assertRaises(ValueError) as caught:
                        callback()
                    self.assertEqual(str(caught.exception), 'Actions-only proof redirect refused')
                    self.assertTrue(caught.exception.__suppress_context__)
        handler.parent.open.assert_not_called()
