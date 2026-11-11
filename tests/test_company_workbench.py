"""In-process company API/privacy/persistence checks; no server or sockets."""
from concurrent.futures import ThreadPoolExecutor
import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from atlanticbridge.automation import company_workspace as W
from atlanticbridge.automation.company_workbench import CompanyWorkbench
from atlanticbridge.automation import company_workbench as app_module
from atlanticbridge.automation.workbench import MAX_BODY, LocalHandler, SECURITY_HEADERS
from atlanticbridge.automation.store import Store

FIXTURE=Path(__file__).parent/'fixtures/company_workspace/browser-export.json'
NOW='2026-11-06T13:00:00Z'


class CompanyWorkbenchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'private-companies.sqlite'
        self.backup=json.loads(FIXTURE.read_text())
        W.initialize(self.db)
        self.import_backup(self.backup)
        self.app=CompanyWorkbench(self.db)
        self.route='/api/companies/'+'a'*64

    def import_backup(self,backup):
        plan=W.plan_import(self.db,backup)
        return W.import_backup(self.db,backup,expected_state=plan['state_token'],expected_backup=plan['backup_token'],actor='test',at=NOW)

    def request(self,path='/api/companies',method='GET',data=None,raw=None,overrides=None,app=None):
        body=raw if raw is not None else json.dumps(data).encode() if data is not None else b''
        env=dict(REMOTE_ADDR='127.0.0.1',HTTP_HOST='127.0.0.1:8766',HTTP_ORIGIN='http://127.0.0.1:8766',
            HTTP_SEC_FETCH_SITE='same-origin',REQUEST_METHOD=method,PATH_INFO=path,QUERY_STRING='',
            CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(body)))
        env.update({'wsgi.url_scheme':'http','wsgi.input':io.BytesIO(body)})
        for k,v in (overrides or {}).items():
            if v is None:env.pop(k,None)
            else:env[k]=v
        response=[]
        body=b''.join((app or self.app)(env,lambda status,headers:response.append((int(status.split()[0]),dict(headers)))))
        status,headers=response[0]
        return status,json.loads(body) if headers['Content-Type']=='application/json' else body,headers

    def fields(self,**extra):
        return dict(expected_revision=1,status='follow_up',notes='Private saved note 🦞',next_action='Review source, no outreach',due_date='2026-11-30',**extra)

    def test_detail_preserves_company_namespace_and_declared_metadata(self):
        status,data,_=self.request(self.route)
        self.assertEqual(status,200)
        expected={**self.backup['entries'][0],'revision':1,'evidence_verified':False,'identity_mapping_performed':False}
        self.assertEqual(data['company'],expected)
        self.assertNotIn('work_item_id',data['company'])

    def test_save_and_reopen_preserve_metadata_and_all_edit_fields(self):
        before=self.request(self.route)[1]['company']
        status,result,_=self.request(self.route,'POST',self.fields())
        self.assertEqual(status,200)
        self.assertEqual(result['company']['revision'],2)
        for field in W.EDIT_FIELDS:self.assertEqual(result['company'][field],self.fields()[field])
        for field in set(before)-W.EDIT_FIELDS-{'updated_at','revision'}:
            self.assertEqual(result['company'][field],before[field])
        self.assertEqual(self.request(self.route,app=CompanyWorkbench(self.db))[1],result)
        with W.snapshot(self.db) as db:
            self.assertEqual(db.execute("SELECT actor FROM analyst_history WHERE operation='SAVE'").fetchone()[0],'local-company-workbench')

    def test_list_is_bounded_and_excludes_notes_actions_and_paths(self):
        status,data,_=self.request()
        self.assertEqual(status,200);self.assertEqual(data['total'],5);self.assertEqual(data['page_size'],25)
        for c in data['companies']:
            self.assertEqual(set(c),{'id','company_name','country','status','due_date','revision'})
        raw=json.dumps(data)
        for value in ('Private invented note','Review, do not contact',str(self.db),'source_sha256'):
            self.assertNotIn(value,raw)
        self.assertEqual(data['mode'],W.MODE);self.assertFalse(data['evidence_verified'])

    def test_status_filter_retains_original_vocabulary(self):
        for status in W.STATUSES:
            code,data,_=self.request(overrides={'QUERY_STRING':'status='+status+'&page=1'})
            self.assertEqual(code,200);self.assertEqual(data['total'],1);self.assertEqual(data['companies'][0]['status'],status)
        self.assertEqual(self.request(overrides={'QUERY_STRING':'status=ACTIVE'})[0],400)

    def test_pagination_stable_total_and_empty_page(self):
        more=copy.deepcopy(self.backup)
        more['entries']=[{**more['entries'][0],'id':format(n,'064x')} for n in range(51)]
        self.import_backup(more)
        _,first,_=self.request();_,second,_=self.request(overrides={'QUERY_STRING':'page=2'})
        self.assertEqual(first['total'],56);self.assertEqual(len(first['companies']),25);self.assertEqual(len(second['companies']),25)
        self.assertFalse({c['id'] for c in first['companies']} & {c['id'] for c in second['companies']})
        self.assertEqual(self.request(overrides={'QUERY_STRING':'page=4'})[1]['companies'],[])

    def test_exact_host_loopback_scheme_and_origin_enforced_on_reads_and_writes(self):
        cases=[{'REMOTE_ADDR':'8.8.8.8'},{'REMOTE_ADDR':'bad'},{'HTTP_HOST':'localhost:8766'},
            {'HTTP_HOST':'127.0.0.1:8765'},{'HTTP_HOST':'127.0.0.1:8766,evil'},
            {'wsgi.url_scheme':'https'},{'HTTP_ORIGIN':'null'},{'HTTP_ORIGIN':'https://127.0.0.1:8766'},
            {'HTTP_ORIGIN':'http://evil.example'},{'HTTP_SEC_FETCH_SITE':'cross-site'},{'HTTP_SEC_FETCH_SITE':None}]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(self.request(overrides=case)[0],403)
                self.assertEqual(self.request(self.route,'POST',self.fields(),overrides=case)[0],403)
        self.assertEqual(self.request(overrides={'HTTP_ORIGIN':None})[0],200)
        self.assertEqual(self.request(self.route,'POST',self.fields(),overrides={'HTTP_ORIGIN':None})[0],403)

    def test_no_cors_or_unapproved_api_routes(self):
        for route in ('/api/import','/api/export','/api/init','/api/backup','/api/items','/api/sources','/api/previews',
                      '/api/tick','/api/companies/../private.sqlite',self.route+'/', '/style.css/../private.sqlite'):
            self.assertEqual(self.request(route)[0],404)
        for method in ('OPTIONS','HEAD','DELETE','PUT','PATCH'):
            self.assertEqual(self.request(self.route,method)[0],405)
        for key in self.request()[2]:self.assertFalse(key.lower().startswith('access-control'))

    def test_query_allowlist_and_bounds(self):
        for query in ('path=/tmp/private','page=1&page=2','page=0','page=-1','page=1.5','status=HOLD',
                      'page=1&status=new&extra=x','page='+'9'*8,'x'*1025):
            self.assertEqual(self.request(overrides={'QUERY_STRING':query})[0],400)
        self.assertEqual(self.request(self.route,overrides={'QUERY_STRING':'page=1'})[0],400)
        self.assertEqual(self.request(self.route,'POST',self.fields(),overrides={'QUERY_STRING':'page=1'})[0],404)

    def test_json_content_bounds_and_duplicate_fields(self):
        cases=[({'CONTENT_TYPE':'text/plain'},415),({'CONTENT_LENGTH':None},400),({'CONTENT_LENGTH':'-1'},400),
            ({'CONTENT_LENGTH':str(MAX_BODY+1)},413),({'CONTENT_LENGTH':'50000'},400),
            ({'HTTP_TRANSFER_ENCODING':'chunked'},400),({'HTTP_CONTENT_ENCODING':'gzip'},400)]
        for headers,expected in cases:
            self.assertEqual(self.request(self.route,'POST',self.fields(),overrides=headers)[0],expected)
        for raw in (b'{"notes":"one","notes":"two"}',b'{"notes":NaN}',b'\xff',b'['*2000):
            self.assertEqual(self.request(self.route,'POST',raw=raw)[0],400)

    def test_exact_write_fields_types_calendar_and_utf16_limits(self):
        for key,value in [('expected_revision',True),('expected_revision',0),('status','ACTIVE'),('notes',None),
            ('notes','x'*4001),('notes','🦞'*2001),('notes','\ud800'),('next_action','x'*501),('due_date',None),
            ('due_date','2026-02-30'),('source_url','https://example.org/other'),('id','f'*64),('actor','intruder')]:
            fields=self.fields();fields[key]=value
            with self.subTest(key=key,value=str(value)[:20]):
                self.assertEqual(self.request(self.route,'POST',fields)[0],400)
        self.assertEqual(self.request(self.route)[1]['company']['revision'],1)

    def test_empty_due_date_and_maximum_unicode_save_without_truncation(self):
        fields=self.fields();fields.update(due_date='',notes='🦞'*2000,next_action='x'*500)
        status,data,_=self.request(self.route,'POST',fields)
        self.assertEqual(status,200);self.assertEqual(data['company']['notes'],fields['notes']);self.assertEqual(data['company']['due_date'],'')

    def test_conflicting_clients_preserve_winner(self):
        second=CompanyWorkbench(self.db)
        self.assertEqual(self.request(self.route,'POST',self.fields())[0],200)
        fields=self.fields();fields['notes']='Loser'
        self.assertEqual(self.request(self.route,'POST',fields,app=second)[0],409)
        self.assertEqual(self.request(self.route)[1]['company']['notes'],'Private saved note 🦞')

    def test_concurrent_saves_exactly_one_wins(self):
        def submit(note):
            fields=self.fields();fields['notes']=note
            return self.request(self.route,'POST',fields)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,['first','second']))
        self.assertEqual(sorted(r[0] for r in results),[200,409])

    def test_commit_then_lost_response_returns_uncertain_and_readback_recovers(self):
        original=W.save
        def lost(*args,**kwargs):original(*args,**kwargs);raise RuntimeError('private path or note must not leak')
        with patch.object(W,'save',side_effect=lost):status,data,_=self.request(self.route,'POST',self.fields())
        self.assertEqual(status,503);self.assertNotIn('private path',json.dumps(data))
        self.assertEqual(self.request(self.route)[1]['company']['revision'],2)
        self.assertEqual(self.request(self.route,'POST',self.fields())[0],409)

    def test_response_confirms_own_save_not_another_later_writer(self):
        original=W.save
        def race(*args,**kwargs):
            result=original(*args,**kwargs)
            later={**kwargs,'expected_revision':2,'fields':{**kwargs['fields'],'notes':'Later writer'}}
            original(*args,**later)
            return result
        with patch.object(W,'save',side_effect=race):status,data,_=self.request(self.route,'POST',self.fields())
        self.assertEqual(status,200);self.assertEqual(data['company']['revision'],2);self.assertEqual(data['company']['notes'],self.fields()['notes'])
        self.assertEqual(self.request(self.route)[1]['company']['revision'],3)

    def test_missing_or_replaced_database_not_created(self):
        self.db.unlink()
        self.assertEqual(self.request()[0],503);self.assertEqual(self.request(self.route,'POST',self.fields())[0],503)
        self.assertFalse(self.db.exists())
        self.db.touch(mode=0o600)
        self.assertEqual(self.request(self.route,'POST',self.fields())[0],503)
        with sqlite3.connect(self.db) as db:self.assertEqual(db.execute('SELECT name FROM sqlite_master').fetchall(),[])

    def test_unsafe_files_and_wrong_store_rejected(self):
        self.db.chmod(0o644)
        self.assertEqual(self.request()[0],503)
        with self.assertRaises(ValueError):CompanyWorkbench(self.db)
        self.db.chmod(0o600)
        other=Path(self.temp.name)/'source-evidence.sqlite'
        with Store(other):pass
        with self.assertRaises(ValueError):CompanyWorkbench(other)

    def test_hardened_assets_responses_and_shared_raw_header_policy(self):
        self.assertIs(app_module.LocalHandler,LocalHandler)
        for asset in ('/','/app.js','/controller.js','/style.css'):
            status,data,headers=self.request(asset,overrides={'HTTP_SEC_FETCH_SITE':None,'HTTP_ORIGIN':None})
            self.assertEqual(status,200);self.assertTrue(data)
            for key,value in SECURITY_HEADERS:self.assertEqual(headers[key],value)
            self.assertNotIn(str(self.db).encode(),data);self.assertNotIn(b'Private invented note',data)
        self.assertEqual(self.request('/',overrides={'HTTP_HOST':'evil.example'})[0],403)
        self.assertEqual(self.request('/controller.js',overrides={'QUERY_STRING':'path=/tmp'})[0],404)

    def test_unknown_id_is_404_and_post_cannot_create_a_company(self):
        route='/api/companies/'+'f'*64
        self.assertEqual(self.request(route)[0],404)
        self.assertEqual(self.request(route,'POST',self.fields())[0],409)
        self.assertEqual(len(W.entries(self.db)),5)

    def test_port_validation_and_startup_has_no_side_effects(self):
        before=self.db.read_bytes()
        for port in (True,0,80,65536,'8766'):
            with self.assertRaises(ValueError):CompanyWorkbench(self.db,port=port)
        CompanyWorkbench(self.db,port=9000)
        self.assertEqual(self.db.read_bytes(),before)


if __name__=='__main__':unittest.main()
