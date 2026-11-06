"""Single-operator loopback workbench. No ingestion, transport, or public hosting.

The callable is testable in process. The optional launcher must not be used behind
proxies: its raw-header checks are part of the security boundary.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from importlib.resources import files
import ipaddress
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import parse_qsl
from wsgiref.simple_server import WSGIRequestHandler

from .models import day, integer, source_id
from .review_notifications import snapshot
from .store import Store, Conflict, _check_private_family, verify_connection

PAGE_SIZE = 25
MAX_BODY = 100000
STATUSES = {'TRIAGE', 'ACTIVE', 'HOLD', 'DONE'}
SECURITY_HEADERS = [
    ('Cache-Control', 'no-store'), ('X-Content-Type-Options', 'nosniff'),
    ('Referrer-Policy', 'no-referrer'), ('X-Frame-Options', 'DENY'),
    ('Cross-Origin-Resource-Policy', 'same-origin'),
    ('Content-Security-Policy', "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; frame-ancestors 'none'; form-action 'none'; base-uri 'none'"),
]
ASSETS = {'/': ('index.html', 'text/html; charset=utf-8'),
          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
          '/controller.js': ('controller.js', 'text/javascript; charset=utf-8'),
          '/style.css': ('style.css', 'text/css; charset=utf-8')}
SENSITIVE_HEADERS = {'host', 'origin', 'sec-fetch-site', 'content-type', 'content-length',
                     'transfer-encoding', 'content-encoding'}


class RequestError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def local_request(e, host):
    """Shared loopback transport gate, before static or private API routing."""
    try:
        loopback = ipaddress.ip_address(e.get('REMOTE_ADDR', '')).is_loopback
    except ValueError:
        loopback = False
    if not loopback or e.get('HTTP_HOST') != host or e.get('wsgi.url_scheme') != 'http':
        raise RequestError(403, 'Loopback origin required.')
    if e.get('HTTP_TRANSFER_ENCODING') is not None or e.get('HTTP_CONTENT_ENCODING') is not None:
        raise RequestError(400, 'Encoded requests are not supported.')
    method, path, query = e.get('REQUEST_METHOD'), e.get('PATH_INFO', ''), e.get('QUERY_STRING', '')
    if method not in {'GET', 'POST'}:
        raise RequestError(405, 'Method not allowed.')
    return method, path, query


def same_origin(e, origin, *, write=False):
    if e.get('HTTP_SEC_FETCH_SITE') != 'same-origin' or e.get('HTTP_ORIGIN', origin) != origin:
        raise RequestError(403, 'Same-origin browser request required.')
    if write and e.get('HTTP_ORIGIN') != origin:
        raise RequestError(403, 'Exact origin required.')


def read_json_body(e):
    if e.get('CONTENT_TYPE') != 'application/json':
        raise RequestError(415, 'JSON required.')
    length = e.get('CONTENT_LENGTH', '')
    if not re.fullmatch(r'[0-9]{1,6}', length):
        raise RequestError(400, 'Bounded content length required.')
    length = int(length)
    if length > MAX_BODY:
        raise RequestError(413, 'Request too large.')
    try:
        raw = e['wsgi.input'].read(length)
        if len(raw) != length:
            raise ValueError('Truncated input')
        return json.loads(raw.decode('utf-8'), object_pairs_hook=json_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise RequestError(400, 'Invalid analyst fields or JSON.') from None


def valid_raw_headers(headers):
    """Called before WSGI normalization; separate pure function for offline QA."""
    seen = set()
    for key, value in headers:
        key = key.lower()
        if '\r' in value or '\n' in value:
            return False
        if key in SENSITIVE_HEADERS:
            if key in seen or key in {'transfer-encoding', 'content-encoding'}:
                return False
            seen.add(key)
    return True


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def save_fields(data):
    if type(data) is not dict or set(data) != {'expected_revision', 'status', 'notes', 'due_date', 'needs_review'}:
        raise ValueError('Invalid save fields')
    integer(data['expected_revision'], 'revision', 1, 2147483647)
    if type(data['status']) is not str or data['status'] not in STATUSES:
        raise ValueError('Invalid status')
    if type(data['notes']) is not str or len(data['notes']) > 16000 or '\x00' in data['notes']:
        raise ValueError('Invalid notes')
    if type(data['needs_review']) is not bool:
        raise ValueError('Invalid review flag')
    if data['due_date'] is not None and type(data['due_date']) is not str:
        raise ValueError('Invalid due date')
    day(data['due_date'])
    return data


class ExistingStore(Store):
    """Use Store's audited save without its create/initialize constructor."""
    def __init__(self, path):
        self.path = str(path)
        _check_private_family(self.path)
        self.db = sqlite3.connect(Path(path).absolute().as_uri() + '?mode=rw', uri=True,
                                  isolation_level=None, timeout=5)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        with super().transaction():
            verify_connection(self.db)
            yield


def item_view(db, item_id):
    row = db.execute('''SELECT w.*,v.content_json,v.origin,v.first_imported_at,
        c.contract_json,r.last_imported_at FROM work_items w JOIN record_versions v ON w.latest_version_id=v.version_id
        JOIN contracts c ON v.contract_id=c.contract_id
        JOIN records r ON w.source_id=r.source_id AND w.record_id=r.record_id WHERE w.item_id=?''', (item_id,)).fetchone()
    if row is None:
        raise RequestError(404, 'Work item not found.')
    content, contract = json.loads(row['content_json']), json.loads(row['contract_json'])
    result = {key: row[key] for key in ('source_id', 'record_id', 'status', 'notes', 'due_date', 'revision')}
    result.update(work_item_id=row['item_id'], needs_review=bool(row['needs_review']),
                  title=str(content['facts'].get('title') or row['record_id'])[:512], origin=row['origin'],
                  imported_at=row['first_imported_at'], last_imported_at=row['last_imported_at'], disposition='CONTEXT_ONLY', lead_eligible=False)
    result.update({key: content.get(key) for key in ('facts', 'source_url', 'published_date', 'event_date')})
    result.update({key: contract[key] for key in ('coverage', 'attribution', 'license_name', 'license_url')})
    return result


class Workbench:
    def __init__(self, foundation, *, port=8765, journal=None):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Port must be an integer from 1024 to 65535')
        self.foundation = Path(foundation).absolute()
        self.journal = Path(journal).absolute() if journal is not None else None
        self.host = f'127.0.0.1:{port}'
        self.origin = f'http://{self.host}'
        # Read/verify existing files only. No fixtures, migrations, or creation.
        with snapshot(self.foundation, foundation=True):
            pass
        if self.journal is not None:
            with snapshot(self.journal):
                pass

    def __call__(self, environ, start_response):
        try:
            status, content_type, body = self.dispatch(environ)
        except RequestError as error:
            status, content_type, body = error.status, 'application/json', {'error': error.message}
        except Exception:
            # Never disclose database paths, notes, SQLite errors, or tracebacks.
            status, content_type, body = 503, 'application/json', {'error': 'Local data unavailable. No save confirmation. Reload to check the current revision.'}
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=True, allow_nan=False).encode('utf-8')
        reason = {200: 'OK', 400: 'Bad Request', 403: 'Forbidden', 404: 'Not Found',
                  405: 'Method Not Allowed', 409: 'Conflict', 413: 'Content Too Large',
                  415: 'Unsupported Media Type', 503: 'Service Unavailable'}[status]
        start_response(f'{status} {reason}', SECURITY_HEADERS + [('Content-Type', content_type), ('Content-Length', str(len(body)))])
        return [body]

    def dispatch(self, e):
        method, path, query = local_request(e, self.host)
        if path in ASSETS and method == 'GET' and not query:
            name, kind = ASSETS[path]
            return 200, kind, files('atlanticbridge.automation').joinpath('workbench_assets', name).read_bytes()
        if not path.startswith('/api/'):
            raise RequestError(404, 'Route not found.')
        same_origin(e, self.origin)
        match = re.fullmatch(r'/api/items/([0-9a-f]{64})', path)
        if method == 'POST':
            if not match or query:
                raise RequestError(404, 'Route not found.')
            same_origin(e, self.origin, write=True)
            try:
                data = save_fields(read_json_body(e))
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise RequestError(400, 'Invalid analyst fields or JSON.') from None
            # Verified backup snapshot before save; locked live verification inside
            # ExistingStore.transaction protects schema/invariants before mutation.
            with snapshot(self.foundation, foundation=True) as db:
                item = item_view(db, match[1])
            try:
                with ExistingStore(self.foundation) as store:
                    revision = store.update_work_item(match[1], **data, at=datetime.now(timezone.utc).isoformat(), actor='local-workbench')
                    # Confirm exactly this save, not another writer's later edit.
                    item.update({key: value for key, value in data.items() if key != 'expected_revision'})
                    item['revision'] = revision
            except Conflict:
                raise RequestError(409, 'Work item changed. Keep your draft and explicitly reload before retrying.') from None
            return 200, 'application/json', {'item': item}
        allowed = {'/api/items', '/api/sources', '/api/previews'}
        if path not in allowed and not match:
            raise RequestError(404, 'Route not found.')
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=3)
            params = dict(pairs)
            keys = {'source', 'status', 'page'} if path == '/api/items' else ({'page'} if path == '/api/previews' else set())
            if len(params) != len(pairs) or not set(params) <= keys:
                raise ValueError('Invalid query')
            if len(query) > 1024 or not re.fullmatch(r'[1-9][0-9]{0,6}', params.get('page', '1')):
                raise ValueError('Invalid page')
            page = int(params.get('page', '1'))
            if params.get('status') and params['status'] not in STATUSES:
                raise ValueError('Invalid status')
            if params.get('source'):
                source_id(params['source'])
        except ValueError:
            raise RequestError(400, 'Invalid query parameters.') from None
        offset = (page - 1) * PAGE_SIZE
        if path == '/api/previews':
            if self.journal is None:
                return 200, 'application/json', dict(previews=[], page=page, total=0, page_size=PAGE_SIZE, configured=False)
            with snapshot(self.journal) as db:
                total = db.execute('SELECT COUNT(*) FROM packets').fetchone()[0]
                previews = [json.loads(r[0]) for r in db.execute('SELECT payload FROM packets ORDER BY event_seq,packet_id LIMIT ? OFFSET ?', (PAGE_SIZE, offset))]
            return 200, 'application/json', dict(previews=previews, page=page, total=total, page_size=PAGE_SIZE, configured=True)
        with snapshot(self.foundation, foundation=True) as db:
            if match:
                result = {'item': item_view(db, match[1])}
            elif path == '/api/sources':
                sources = []
                for row in db.execute('SELECT s.*,c.contract_json FROM sources s JOIN contracts c ON s.contract_id=c.contract_id ORDER BY s.source_id'):
                    contract = json.loads(row['contract_json'])
                    source = {key: row[key] for key in ('source_id', 'state', 'last_success_at', 'last_attempt_at')}
                    source.update(failure_count=row['consecutive_failures'], live_source_freshness='UNVERIFIED_LOCAL_IMPORT_ONLY')
                    source.update({key: contract[key] for key in ('coverage', 'attribution', 'license_name', 'license_url')})
                    sources.append(source)
                result = {'sources': sources}
            else:
                where, args = [], []
                for key in ('source', 'status'):
                    if params.get(key):
                        where.append(('source_id' if key == 'source' else 'status') + '=?')
                        args.append(params[key])
                clause = ' WHERE ' + ' AND '.join(where) if where else ''
                total = db.execute('SELECT COUNT(*) FROM work_items' + clause, args).fetchone()[0]
                ids = db.execute('SELECT item_id FROM work_items' + clause + ' ORDER BY source_id,record_id LIMIT ? OFFSET ?', (*args, PAGE_SIZE, offset)).fetchall()
                summaries = []
                for row in ids:
                    item = item_view(db, row[0])
                    summary = {key: item[key] for key in ('work_item_id', 'source_id', 'record_id', 'status', 'needs_review', 'due_date', 'revision')}
                    summary['title'] = str(item['title'])[:512]
                    summaries.append(summary)
                result = dict(items=summaries, page=page, total=total, page_size=PAGE_SIZE)
        return 200, 'application/json', result


class LocalHandler(WSGIRequestHandler):
    timeout = 10  # Bound incomplete headers/bodies on the single-operator server.
    def parse_request(self):
        if not super().parse_request():
            return False
        if not valid_raw_headers(self.headers.raw_items()):
            self.send_error(400, 'Invalid request headers')
            return False
        return True

    def end_headers(self):
        # Raw-parser rejections occur before the WSGI application. Harden those too.
        for key, value in SECURITY_HEADERS:
            self.send_header(key, value)
        super().end_headers()

    def log_message(self, *args):
        pass  # Never log paths, query strings, notes, or request details.


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private local-only workbench. Never proxy or publicly host.')
    parser.add_argument('--foundation', required=True)
    parser.add_argument('--journal')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args(argv)
    try:
        app = Workbench(args.foundation, port=args.port, journal=args.journal)
    except Exception:
        parser.exit(2, 'Cannot open verified existing private local databases or invalid port.\n')
    from wsgiref.simple_server import make_server

    with make_server('127.0.0.1', args.port, app, handler_class=LocalHandler) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
