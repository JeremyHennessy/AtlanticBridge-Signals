"""Same-origin private company worklist for one trusted local OS operator.

No authentication for other local processes, public hosting, evidence ingestion,
backup import/export API, source mutation, delivery, credentials or scheduling.
"""
import argparse
from importlib.resources import files
import json
from pathlib import Path
import re
from urllib.parse import parse_qsl

from . import company_workspace as workspace
from .models import integer
from .scheduler import utc_now
from .store import Conflict
from .workbench import Workbench, LocalHandler, RequestError, local_request, same_origin, read_json_body

PAGE_SIZE = 25
ASSETS = {'/':('index.html','text/html; charset=utf-8'),
          '/app.js':('app.js','text/javascript; charset=utf-8'),
          '/controller.js':('controller.js','text/javascript; charset=utf-8')}


def company_view(row):
    return {**json.loads(row['payload']), 'revision':row['revision'],
            'evidence_verified':False, 'identity_mapping_performed':False}


class CompanyWorkbench(Workbench):
    """Reuse hardened responses, not the source-record routing or database."""
    def __init__(self, company_db, *, port=8766):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('Port must be an integer from 1024 to 65535')
        self.company_db = Path(company_db).absolute()
        self.host = f'127.0.0.1:{port}'
        self.origin = f'http://{self.host}'
        with workspace.snapshot(self.company_db):
            pass

    def dispatch(self, e):
        method, path, query = local_request(e, self.host)
        if path in ASSETS and method == 'GET' and not query:
            name, kind = ASSETS[path]
            return 200, kind, files('atlanticbridge.automation').joinpath('company_workbench_assets', name).read_bytes()
        if path == '/style.css' and method == 'GET' and not query:
            return 200, 'text/css; charset=utf-8', files('atlanticbridge.automation').joinpath('workbench_assets','style.css').read_bytes()
        if not path.startswith('/api/'):
            raise RequestError(404, 'Route not found.')
        same_origin(e, self.origin, write=method == 'POST')
        match = re.fullmatch(r'/api/companies/([0-9a-f]{64})', path)
        if method == 'POST':
            if not match or query:
                raise RequestError(404, 'Route not found.')
            data = read_json_body(e)
            try:
                if type(data) is not dict or set(data) != {'expected_revision', *workspace.EDIT_FIELDS}:
                    raise ValueError('Invalid save fields')
                revision = integer(data['expected_revision'], 'revision', 1, 2147483646)
                fields = workspace.validate_fields({key:data[key] for key in workspace.EDIT_FIELDS})
            except (ValueError, TypeError, UnicodeError):
                raise RequestError(400, 'Invalid company analyst fields.') from None
            try:
                result = workspace.save(self.company_db,match[1],expected_revision=revision,
                    fields=fields,actor='local-company-workbench',at=utc_now())
            except Conflict:
                raise RequestError(409, 'Company changed or no longer available. Keep your draft and reload before retrying.') from None
            # Confirm the exact committed version returned by save, never a later
            # read that could be another client's edit. No database path exposed.
            return 200, 'application/json', {'company':{**result['entry'],'revision':result['revision'],
                'evidence_verified':False,'identity_mapping_performed':False}}
        if path != '/api/companies' and not match:
            raise RequestError(404, 'Route not found.')
        try:
            if len(query) > 1024:
                raise ValueError('Oversized query')
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True, max_num_fields=2)
            params = dict(pairs)
            if len(params) != len(pairs) or not set(params) <= ({'status','page'} if not match else set()):
                raise ValueError('Invalid query')
            if not re.fullmatch('[1-9][0-9]{0,6}',params.get('page','1')):
                raise ValueError('Invalid page')
            if params.get('status') and params['status'] not in workspace.STATUSES:
                raise ValueError('Invalid status')
            page = int(params.get('page','1'))
        except ValueError:
            raise RequestError(400, 'Invalid query parameters.') from None
        with workspace.snapshot(self.company_db) as db:
            if match:
                row = db.execute('SELECT * FROM company_entries WHERE company_id=?',(match[1],)).fetchone()
                if row is None:
                    raise RequestError(404, 'Company not found.')
                result = {'company':company_view(row)}
            else:
                # Existing store is bounded to 500 companies. A single verified
                # snapshot is authoritative for both filtering and total count.
                values = [company_view(row) for row in db.execute('SELECT * FROM company_entries ORDER BY company_id')]
                if params.get('status'):
                    values = [value for value in values if value['status'] == params['status']]
                offset = (page-1)*PAGE_SIZE
                summaries = [{key:value[key] for key in ('id','company_name','country','status','due_date','revision')}
                             for value in values[offset:offset+PAGE_SIZE]]
                result = dict(companies=summaries,page=page,total=len(values),page_size=PAGE_SIZE,
                    mode=workspace.MODE,evidence_verified=False,identity_mapping_performed=False)
        return 200, 'application/json', result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private local company worklist. Never proxy or publicly host.')
    parser.add_argument('--company-db', required=True)
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args(argv)
    try:
        app = CompanyWorkbench(args.company_db, port=args.port)
    except Exception:
        parser.exit(2, 'Cannot open verified existing private company workspace or invalid port.\n')
    from wsgiref.simple_server import make_server
    with make_server('127.0.0.1', args.port, app, handler_class=LocalHandler) as server:
        server.serve_forever()


if __name__ == '__main__':
    main()
