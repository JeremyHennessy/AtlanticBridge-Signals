"""No server/socket: in-process WSGI adversarial and durable-state tests."""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, Mock

from atlanticbridge.automation.store import Store
from atlanticbridge.automation.models import decode_batch
from atlanticbridge.automation.workbench import Workbench, MAX_BODY, valid_raw_headers
from test_automation_foundation import contract, body, NOW


class WorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'private.sqlite'
        with Store(self.path) as store:
            c = contract()
            store.register(c, at=NOW)
            store.set_source_state(c.source_id, 'READY', at=NOW, actor='test')
            run = store.claim(c.source_id, at=NOW)
            store.complete(run, decode_batch(body(c), c), at=NOW)
            self.item_id = store.work_items()[0]['item_id']
        self.app = Workbench(self.path)
        self.route = '/api/items/' + self.item_id

    def request(self, path='/api/items', method='GET', data=None, overrides=None, raw=None, app=None):
        payload = raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        e = dict(REMOTE_ADDR='127.0.0.1', HTTP_HOST='127.0.0.1:8765', REQUEST_METHOD=method,
                 PATH_INFO=path, QUERY_STRING='', HTTP_SEC_FETCH_SITE='same-origin',
                 HTTP_ORIGIN='http://127.0.0.1:8765', CONTENT_TYPE='application/json',
                 CONTENT_LENGTH=str(len(payload)))
        e.update({'wsgi.url_scheme': 'http', 'wsgi.input': io.BytesIO(payload)})
        for k, v in (overrides or {}).items():
            if v is None:
                e.pop(k, None)
            else:
                e[k] = v
        response = []
        result = b''.join((app or self.app)(e, lambda status, headers: response.append((status, dict(headers)))))
        return int(response[0][0].split()[0]), json.loads(result) if response[0][1]['Content-Type'] == 'application/json' else result, response[0][1]

    def fields(self, **extra):
        result = dict(expected_revision=1, status='ACTIVE', notes='Private analyst notes <script>alert(1)</script>', due_date='2026-11-30', needs_review=False)
        result.update(extra)
        return result

    def test_save_reopen_persistence_clocks_and_source_immutability(self):
        before = sqlite3.connect(self.path)
        tables = ('sources', 'records', 'record_versions', 'evidence_events', 'evidence_blobs')
        original = {t: before.execute('SELECT * FROM ' + t).fetchall() for t in tables}
        before.close()
        status, data, headers = self.request(self.route, 'POST', self.fields())
        self.assertEqual(status, 200); self.assertEqual(data['item']['revision'], 2)
        reopened = Workbench(self.path)
        status, data, _ = self.request(self.route, app=reopened)
        self.assertEqual(data['item']['notes'], self.fields()['notes'])
        self.assertEqual(data['item']['published_date'], '2023-08-04')
        self.assertTrue(data['item']['imported_at'].startswith('2026-11-06'))
        self.assertEqual(data['item']['origin'], 'INVENTED_FIXTURE')
        with sqlite3.connect(self.path) as db:
            self.assertEqual(original, {t: db.execute('SELECT * FROM ' + t).fetchall() for t in tables})
            self.assertEqual(db.execute("SELECT actor FROM audit_log WHERE action='USER_SAVED'").fetchone()[0], 'local-workbench')
        for name in ('Cache-Control', 'X-Content-Type-Options', 'Referrer-Policy', 'Content-Security-Policy', 'X-Frame-Options', 'Cross-Origin-Resource-Policy'):
            self.assertIn(name, headers)

    def test_concurrent_client_revision_conflict(self):
        second = Workbench(self.path)
        self.assertEqual(self.request(self.route, 'POST', self.fields())[0], 200)
        self.assertEqual(self.request(self.route, 'POST', self.fields(notes='lost update'), app=second)[0], 409)
        self.assertEqual(self.request(self.route)[1]['item']['notes'], self.fields()['notes'])

    def test_browser_origin_dns_rebinding_and_host(self):
        cases = [dict(HTTP_HOST='evil.example:8765'), dict(HTTP_HOST='localhost:8765'), dict(HTTP_HOST='127.0.0.1:8766'),
                 dict(HTTP_HOST='127.0.0.1:8765,evil'), dict(REMOTE_ADDR='8.8.8.8'), dict(REMOTE_ADDR='garbage'),
                 dict(HTTP_ORIGIN='null'), dict(HTTP_ORIGIN='https://127.0.0.1:8765'), dict(HTTP_ORIGIN='http://evil.example'),
                 dict(HTTP_SEC_FETCH_SITE=None), dict(HTTP_SEC_FETCH_SITE='cross-site'), {'wsgi.url_scheme': 'https'}]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(self.request(overrides=case)[0], 403)
                self.assertEqual(self.request(self.route, 'POST', self.fields(), overrides=case)[0], 403)
        self.assertEqual(self.request(overrides={'HTTP_ORIGIN': None})[0], 200)
        self.assertEqual(self.request(self.route, 'POST', self.fields(), overrides={'HTTP_ORIGIN': None})[0], 403)

    def test_allowlist_no_mutation_routes_and_queries(self):
        for route in ('/api/register', '/api/tick', '/api/export', '/api/backup', '/api/items/../../private.sqlite', '/%2e%2e/private.sqlite', '/style.css/..', '/api/items/' + self.item_id + '/'):
            self.assertEqual(self.request(route)[0], 404)
        for query in ('path=/tmp/x', 'page=0', 'page=1&page=2', 'status=BOGUS', 'source=../x', 'page=NaN'):
            self.assertEqual(self.request(overrides={'QUERY_STRING': query})[0], 400)
        self.assertEqual(self.request(overrides={'QUERY_STRING': 'source=fixture&status=TRIAGE&page=1'})[1]['total'], 1)
        self.assertEqual(self.request(overrides={'QUERY_STRING': 'page=2'})[1]['items'], [])
        self.assertEqual(self.request(method='DELETE')[0], 405)
        self.assertEqual(self.request(self.route, 'POST', self.fields(), overrides={'QUERY_STRING': 'path=/tmp/x'})[0], 404)

    def test_strict_json_exact_fields_and_types(self):
        bad = [self.fields(expected_revision=True), self.fields(expected_revision=0), self.fields(status=[]),
               self.fields(notes='x'*16001), self.fields(notes=None), self.fields(notes='a\x00b'), self.fields(needs_review=1),
               self.fields(due_date='2026-02-30'), self.fields(due_date=5), self.fields(actor='intruder'),
               self.fields(source_id='other'), self.fields(facts={'title': 'changed'}), [], None]
        for data in bad:
            with self.subTest(data=str(data)[:80]):
                self.assertEqual(self.request(self.route, 'POST', data)[0], 400)
        for raw in (b'{"notes":"a","notes":"b"}', b'{"notes":NaN}', b'\xff', b'['*2000):
            self.assertEqual(self.request(self.route, 'POST', raw=raw)[0], 400)
        self.assertEqual(self.request(self.route)[1]['item']['revision'], 1)

    def test_content_limits_and_encoding(self):
        for overrides, expected in [({'CONTENT_TYPE': 'text/plain'},415), ({'CONTENT_TYPE':'application/json; charset=utf-8'},415),
              ({'CONTENT_LENGTH':str(MAX_BODY+1)},413), ({'CONTENT_LENGTH':None},400), ({'CONTENT_LENGTH':'-1'},400),
              ({'CONTENT_LENGTH':'10,10'},400), ({'HTTP_TRANSFER_ENCODING':'chunked'},400), ({'HTTP_CONTENT_ENCODING':'gzip'},400),
              ({'CONTENT_LENGTH':'69999'},400)]:
            self.assertEqual(self.request(self.route,'POST',self.fields(),overrides=overrides)[0],expected)

    def test_raw_duplicate_headers_before_normalization(self):
        for name in ('Host','Origin','Sec-Fetch-Site','Content-Type','Content-Length','Content-Encoding','Transfer-Encoding'):
            self.assertFalse(valid_raw_headers([(name,'a'),(name.lower(),'b')]))
        self.assertFalse(valid_raw_headers([('Transfer-Encoding','identity')]))
        self.assertFalse(valid_raw_headers([('X-Any','a\r\nb')]))
        self.assertTrue(valid_raw_headers([('Host','127.0.0.1:8765'),('Origin','http://127.0.0.1:8765')]))

    def test_health_preview_no_sensitive_internals(self):
        status, data, _ = self.request('/api/sources')
        self.assertEqual(status, 200)
        raw = json.dumps(data)
        for excluded in ('input_path', 'lease_token', 'lease_until', str(self.path), 'evidence_blobs'):
            self.assertNotIn(excluded, raw)
        self.assertEqual(self.request('/api/previews')[1]['configured'], False)

    def test_missing_replaced_empty_foundation_never_created(self):
        self.path.unlink()
        self.assertEqual(self.request(self.route, 'POST', self.fields())[0], 503)
        self.assertFalse(self.path.exists())
        self.path.touch(mode=0o600)
        self.assertEqual(self.request(self.route, 'POST', self.fields())[0], 503)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT name FROM sqlite_master').fetchall(), [])
        with self.assertRaises(Exception):
            Workbench(self.path)

    def test_simultaneous_saves_exactly_one_wins(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.request, self.route, 'POST', self.fields(notes=note)) for note in ('first', 'second')]
            responses = [future.result() for future in futures]
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        winner = next(r[1]['item'] for r in responses if r[0] == 200)
        self.assertEqual(self.request(self.route)[1]['item']['notes'], winner['notes'])

    def test_summary_is_bounded_and_source_filter_uses_canonical_id(self):
        result = self.request()[1]['items'][0]
        self.assertNotIn('notes', result); self.assertNotIn('facts', result)
        self.assertLessEqual(len(result['title']), 512)
        self.assertEqual(self.request(overrides={'QUERY_STRING': 'source=a:b'})[0], 200)
        self.assertEqual(self.request(overrides={'QUERY_STRING': 'source=' + 'a'*100})[0], 200)
        self.assertEqual(self.request(overrides={'QUERY_STRING': 'source=' + 'a'*101})[0], 400)
        detail = self.request(self.route)[1]['item']
        self.assertIn('last_imported_at', detail)

    def test_staged_preview_is_read_only_and_paginated(self):
        from atlanticbridge.automation.review_notifications import ReviewJournal
        journal = Path(self.temp.name) / 'review.sqlite'
        with ReviewJournal.initialize(journal) as j:
            j.register(self.path, plan_id='test', sources=['fixture'], since=NOW)
            j.stage(self.path, plan_id='test', at=NOW)
        app = Workbench(self.path, journal=journal)
        before = journal.read_bytes()
        response = self.request('/api/previews', app=app)
        self.assertEqual(response[0], 200); self.assertTrue(response[1]['configured'])
        self.assertEqual(journal.read_bytes(), before)
        self.assertEqual(self.request('/api/previews', 'POST', {}, app=app)[0], 404)

    def test_existing_store_cannot_create_after_snapshot_race(self):
        from atlanticbridge.automation.workbench import ExistingStore
        original = ExistingStore.__init__
        def remove_then_open(store, path):
            Path(path).unlink()
            original(store, path)
        with patch.object(ExistingStore, '__init__', remove_then_open):
            self.assertEqual(self.request(self.route, 'POST', self.fields())[0], 503)
        self.assertFalse(self.path.exists())

    def test_static_shell_allowlist_and_headers(self):
        for route in ('/', '/app.js', '/controller.js', '/style.css'):
            status, data, headers = self.request(route, overrides={'HTTP_SEC_FETCH_SITE': None, 'HTTP_ORIGIN': None})
            self.assertEqual(status, 200); self.assertTrue(data)
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request('/index.html')[0], 404)

    def test_raw_handler_parser_fake_stream_rejects_duplicate_before_wsgi(self):
        from atlanticbridge.automation.workbench import LocalHandler
        for headers in (b'Host: 127.0.0.1:8765\r\nHost: evil\r\n', b'Host: 127.0.0.1:8765\r\nTransfer-Encoding: chunked\r\n'):
            handler = LocalHandler.__new__(LocalHandler)
            handler.raw_requestline = b'POST /api/items HTTP/1.1\r\n'
            handler.rfile = io.BytesIO(headers + b'\r\n')
            handler.wfile = io.BytesIO()
            self.assertFalse(handler.parse_request())
            result = handler.wfile.getvalue()
            self.assertIn(b'400', result)
            self.assertIn(b'Cache-Control: no-store', result)
            self.assertIn(b'X-Frame-Options: DENY', result)

    def test_handler_timeout_with_fake_connection_no_socket(self):
        from atlanticbridge.automation.workbench import LocalHandler
        handler = LocalHandler.__new__(LocalHandler)
        handler.request = Mock()
        handler.request.makefile.return_value = io.BytesIO()
        handler.setup()
        handler.request.settimeout.assert_called_once_with(10)
        handler.finish()

    def test_scalar_source_title_is_safe_presentation_text(self):
        from test_automation_foundation import LATER
        with Store(self.path) as store:
            c = contract()
            run = store.claim(c.source_id, at=LATER)
            store.complete(run, decode_batch(body(c, [{'record_id':'one', 'facts':{'title':42}}]), c), at=LATER)
        data = self.request(self.route)[1]['item']
        self.assertEqual(data['title'], '42')
        self.assertEqual(data['facts']['title'], 42)

    def test_astral_notes_codepoint_limit_with_bounded_utf8_body(self):
        notes = '\U0001f680' * 16000
        raw = json.dumps(self.fields(notes=notes), ensure_ascii=False).encode('utf-8')
        self.assertLess(len(raw), MAX_BODY)
        self.assertEqual(self.request(self.route, 'POST', raw=raw)[0], 200)
        self.assertEqual(self.request(self.route)[1]['item']['notes'], notes)

    def test_control_notes_browser_json_wire_limit_and_status_only_save(self):
        notes = '\u0001' * 16000
        # JSON.stringify emits six-byte escapes for these controls, as json.dumps does.
        raw = json.dumps(self.fields(notes=notes), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertGreater(len(raw), 96000)
        self.assertLessEqual(len(raw), MAX_BODY)
        self.assertEqual(self.request(self.route, 'POST', raw=raw)[0], 200)
        raw = json.dumps(self.fields(expected_revision=2, status='HOLD', notes=notes), ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        self.assertEqual(self.request(self.route, 'POST', raw=raw)[0], 200)
        item = self.request(self.route)[1]['item']
        self.assertEqual(item['notes'], notes); self.assertEqual(item['status'], 'HOLD')
        self.assertEqual(item['revision'], 3)

    def test_sanitized_errors(self):
        with patch('atlanticbridge.automation.workbench.snapshot', side_effect=ValueError('/private/db secret notes')):
            status, data, _ = self.request()
        self.assertEqual(status, 503)
        self.assertNotIn('/private', json.dumps(data)); self.assertNotIn('secret notes', json.dumps(data))
        for port in (True, 0, 80, 65536, '8765'):
            with self.assertRaises(ValueError): Workbench(self.path, port=port)


if __name__ == '__main__': unittest.main()
