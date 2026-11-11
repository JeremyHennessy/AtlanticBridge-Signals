import io
import json
from pathlib import Path
import sys
import unittest
import urllib.request
import zipfile
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import archive_evidence as a
from atlanticbridge.company_sources import Ledger
from atlanticbridge.monitoring_checkpoint import checkpoint,health

class ArchiveTests(unittest.TestCase):
    def test_invalid_api_json_reports_endpoint_without_exposing_body(self):
        from unittest.mock import MagicMock
        client=a.Client('TEST-SECRET-TOKEN')
        response=MagicMock()
        response.__enter__.return_value=response
        response.status=200
        response.read.return_value=b'<html>PRIVATE-RESPONSE-BODY</html>'
        client.opener.open=MagicMock(return_value=response)

        with self.assertRaises(ValueError) as caught:
            client.json(a.API+'/actions/artifacts/123')

        message=str(caught.exception)
        self.assertIn('GitHub API GET /repos/JeremyHennessy/AtlanticBridge-Signals/actions/artifacts/123',message)
        self.assertIn('line 1, column',message)
        self.assertNotIn('PRIVATE-RESPONSE-BODY',message)
        self.assertNotIn('TEST-SECRET-TOKEN',message)

    def test_invalid_encoding_json_reports_safe_context(self):
        with self.assertRaises(ValueError) as caught:
            a.parse_json(b'\xffPRIVATE-RESPONSE-BODY', 'retained checkpoint.json')
        self.assertEqual(str(caught.exception), 'retained checkpoint.json was not valid JSON (invalid text encoding)')
        self.assertIsNone(caught.exception.__cause__)

    def raw_zip(self,content=b'evidence',name=None):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr(name or 'raw/'+a.sha(content)+'.bin',content)
        return out.getvalue()
    def test_exact_raw_response_hash(self):
        raw=self.raw_zip();self.assertEqual(a.inspect_zip(raw,a.sha(raw))[1],1)
    def test_artifact_digest_mismatch(self):
        with self.assertRaises(ValueError):a.inspect_zip(self.raw_zip(),'0'*64)
    def test_raw_body_tamper(self):
        raw=self.raw_zip(name='raw/'+'0'*64+'.bin')
        with self.assertRaises(ValueError):a.inspect_zip(raw,a.sha(raw))
    def test_unsafe_zip(self):
        for name in ('../x','/x','raw\\x'):
            raw=self.raw_zip(name=name)
            with self.assertRaises(ValueError):a.inspect_zip(raw,a.sha(raw))
    def test_no_raw_documents_cannot_claim_archive(self):
        raw=self.raw_zip(name='metadata.json')
        with self.assertRaises(ValueError):a.inspect_zip(raw,a.sha(raw))
    def test_published_releases_never_accepted(self):
        for release in ({'draft':False},{'draft':True,'published_at':'today'},{}):
            with self.assertRaises(ValueError):a.require_draft(release)
        a.require_draft({'draft':True,'published_at':None})
    def test_restore_checkpoint_exact(self):
        ledger=Ledger(':memory:');value=checkpoint(ledger);ledger.db.close()
        result=a.inspect_checkpoint(json.dumps(value).encode(),health(value))
        self.assertTrue(result['exact_state_restore']);self.assertEqual(result['observations'],0)
    def test_restore_bound_to_actual_health(self):
        ledger=Ledger(':memory:');value=checkpoint(ledger);ledger.db.close()
        with self.assertRaises(ValueError):a.inspect_checkpoint(json.dumps(value).encode(),{})
    def test_restore_accepts_only_explicit_legacy_additive_health_omissions(self):
        ledger=Ledger(':memory:');value=checkpoint(ledger);ledger.db.close()
        observed=health(value)
        observed.pop('operational_source_count')
        observed.pop('reliability_scope')
        result=a.inspect_checkpoint(json.dumps(value).encode(),observed)
        self.assertTrue(result['exact_state_restore'])
    def test_restore_rejects_legacy_snapshot_with_real_mismatch(self):
        ledger=Ledger(':memory:');value=checkpoint(ledger);ledger.db.close()
        observed=health(value)
        observed.pop('operational_source_count')
        observed.pop('reliability_scope')
        observed['public_alert_count']=1
        with self.assertRaises(ValueError):a.inspect_checkpoint(json.dumps(value).encode(),observed)
    def test_restore_corrupt_checkpoint(self):
        ledger=Ledger(':memory:');value=checkpoint(ledger);ledger.db.close();value['checksum']='bad'
        with self.assertRaises(ValueError):a.inspect_checkpoint(json.dumps(value).encode(),{})
    def test_auth_removed_on_cross_host_redirect(self):
        req=urllib.request.Request('https://api.github.com/a',headers={'Authorization':'Bearer TEST'})
        new=a.SafeRedirect().redirect_request(req,None,302,'',{},'https://example.org/asset')
        self.assertIsNone(new.get_header('Authorization'))
        same=a.SafeRedirect().redirect_request(req,None,302,'',{},'https://api.github.com/b')
        self.assertEqual(same.get_header('Authorization'),'Bearer TEST')
        with self.assertRaises(ValueError):a.SafeRedirect().redirect_request(req,None,302,'',{},'http://example.org/asset')
    def test_unapproved_endpoint(self):
        with self.assertRaises(ValueError):a.Client('TEST').request('https://example.org/steal')
    def test_unknown_proof_cannot_be_used(self):
        with self.assertRaises(ValueError):a.accepted_proof(None,999)
    def test_idempotent_existing_asset(self):
        class Client:
            def json(self,url,*args):return {'draft':True,'published_at':None}
            def pages(self,path):return [{'id':7,'name':'x','browser_download_url':'https://github.com/a/x'}]
            def request(self,url,*args,**kw):return 200,b'evidence'
            def verify_private(self,url):pass
        meta,raw=a.store_asset(Client(),{'id':1},'x',b'evidence')
        self.assertTrue(meta['byte_restore_verified']);self.assertEqual(raw,b'evidence')
        self.assertEqual(meta['privacy_verification_method'],a.PRIVACY_METHOD)
    def test_existing_asset_never_overwritten(self):
        class Client:
            def json(self,url,*args):return {'draft':True,'published_at':None}
            def pages(self,path):return [{'id':7,'name':'x'}]
            def request(self,*args,**kw):return 200,b'different'
        with self.assertRaises(ValueError):a.store_asset(Client(),{'id':1},'x',b'evidence')
    def test_public_or_inconclusive_access_fails(self):
        class Client:
            def json(self,url,*args):return {'draft':True,'published_at':None}
            def pages(self,path):return [{'id':7,'name':'x','browser_download_url':'https://github.com/a/x'}]
            def request(self,*args,**kw):return 200,b'evidence'
            def verify_private(self,url):raise a.PrivacyCheckError({'status':403})
        with self.assertRaises(ValueError):a.store_asset(Client(),{'id':1},'x',b'evidence')
    def test_archive_pin_fallback_requires_exact_bytes(self):
        expected=a.PINS[10724340100]
        class Client:
            def request(self,url,*args,**kw):return (200,b'BAD') if '/releases/assets/' in url else (404,b'')
            def pages(self,path):
                if path=='/releases':return [{'id':1,'tag_name':'evidence-v1-2026-09','draft':True,'published_at':None}]
                return [{'id':7,'name':f'artifact-10724340100-{expected[:16]}.zip'}]
        with self.assertRaises(ValueError):a.accepted_proof(Client(),10724340100)

    def test_download_accept_header_matches_endpoint_contract(self):
        from unittest.mock import MagicMock
        client=a.Client('TEST')
        response=MagicMock();response.__enter__.return_value=response
        response.status=200;response.read.return_value=b'bytes'
        client.opener.open=MagicMock(return_value=response)
        for suffix,expected in [('/actions/artifacts/1/zip','application/vnd.github+json'),('/releases/assets/1','application/octet-stream'),('/releases/1','application/vnd.github+json'),('/contents/checkpoint.json?ref='+'a'*40,'application/vnd.github.raw+json')]:
            client.request(a.API+suffix,binary=True)
            req=client.opener.open.call_args.args[0]
            self.assertEqual(req.get_header('Accept'),expected)

    def test_invalid_api_json_has_safe_endpoint_diagnostic(self):
        client=a.Client('TEST')
        client.request=lambda url,*args,**kwargs:(200,b'<html>not json</html>')
        target=a.API+'/actions/workflows/company-monitor.yml/runs?token=do-not-log'
        with self.assertRaises(ValueError) as caught:
            client.json(target)
        message=str(caught.exception)
        self.assertIn('/actions/workflows/company-monitor.yml/runs',message)
        self.assertIn('HTTP 200',message)
        self.assertNotIn('token',message)
        self.assertNotIn('do-not-log',message)

    def monitoring_archive_fixture(self):
        ledger=Ledger(':memory:')
        value=checkpoint(ledger,runs=[{'id':'42-1','finished_at':'2026-11-06T12:00:00+00:00','sources':[]}])
        ledger.db.close()
        observed=health(value)
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            z.writestr('raw/'+a.sha(b'evidence')+'.bin',b'evidence')
            z.writestr('data-commit.txt','a'*40)
            z.writestr('health.json',json.dumps(observed))
        raw=out.getvalue()
        artifact={'id':17,'workflow_run':{'id':42},'digest':'sha256:'+a.sha(raw)}
        return artifact,raw,value,observed

    def test_monitor_archive_retains_exact_large_raw_checkpoint(self):
        from unittest.mock import Mock
        artifact,raw,value,observed=self.monitoring_archive_fixture()
        original=json.dumps(value).encode()+b' '*(1024*1024+1)
        client=Mock()
        client.request.return_value=(200,original)
        client.json.side_effect=AssertionError('Must not request inline base64 contents')
        with patch.object(a,'store_asset',side_effect=lambda c,r,n,b:({'name':n},b)) as store:
            result=a.archive_one(client,artifact,a.sha(raw),{'id':1},monitoring=True,raw_override=raw)
        client.request.assert_called_once_with(a.API+'/contents/checkpoint.json?ref='+'a'*40,binary=True)
        self.assertEqual(store.call_count,2)
        self.assertEqual(store.call_args_list[0].args[3],raw)
        self.assertEqual(store.call_args_list[1].args[3],original)
        self.assertIn(a.sha(original)[:16],store.call_args_list[1].args[2])
        self.assertTrue(result['restore']['exact_state_restore'])
        self.assertEqual(result['restore']['data_commit'],'a'*40)
        self.assertEqual(result['restore']['checkpoint_checksum'],value['checksum'])

    def test_monitor_archive_rejects_download_errors_before_any_write(self):
        from unittest.mock import Mock
        artifact,raw,value,observed=self.monitoring_archive_fixture()
        for status,body in [(403,b'private response'),(404,b''),(500,b'private response'),(200,b''),(200,b'not json'),(200,b'\xffprivate response')]:
            with self.subTest(status=status,body_length=len(body)):
                client=Mock();client.request.return_value=(status,body)
                with patch.object(a,'store_asset') as store:
                    with self.assertRaises(ValueError) as caught:
                        a.archive_one(client,artifact,a.sha(raw),{'id':1},monitoring=True,raw_override=raw)
                    store.assert_not_called()
                self.assertNotIn('private response',str(caught.exception))
                client.request.assert_called_once()

    def test_monitor_archive_rejects_oversized_checkpoint_before_any_write(self):
        from unittest.mock import Mock
        artifact,raw,value,observed=self.monitoring_archive_fixture()
        client=Mock();client.request.return_value=(200,b'X'*11)
        with patch.object(a,'MAX_CHECKPOINT_BYTES',10),patch.object(a,'store_asset') as store:
            with self.assertRaisesRegex(ValueError,'size limit'):
                a.archive_one(client,artifact,a.sha(raw),{'id':1},monitoring=True,raw_override=raw)
            store.assert_not_called()

    def test_monitor_archive_rejects_corrupt_or_wrong_health_before_any_write(self):
        from unittest.mock import Mock
        artifact,raw,value,observed=self.monitoring_archive_fixture()
        corrupt=dict(value,checksum='bad')
        ledger=Ledger(':memory:');different=checkpoint(ledger);ledger.db.close()
        for data in [corrupt,different]:
            with self.subTest(checksum=data['checksum']):
                client=Mock();client.request.return_value=(200,json.dumps(data).encode())
                with patch.object(a,'store_asset') as store:
                    with self.assertRaises(ValueError):
                        a.archive_one(client,artifact,a.sha(raw),{'id':1},monitoring=True,raw_override=raw)
                    store.assert_not_called()
