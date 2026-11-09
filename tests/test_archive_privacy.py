"""Offline regressions using real urllib redirect/error processing, no server."""
import io
import json
from email.message import Message
from pathlib import Path
import sys
import os
import tempfile
import unittest
import urllib.error
import urllib.request
import urllib.response
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import archive_evidence as a

class UnreadableBody(io.BytesIO):
    def read(self, *args):
        raise AssertionError('Privacy verifier must not read response bodies')

class PrivacyTests(unittest.TestCase):
    url = a.API+'/releases/assets/7'

    def client(self, code=404, headers=None, response_url=None, error=None):
        seen = []
        class SyntheticHTTPS(urllib.request.HTTPSHandler):
            def https_open(inner, req):
                seen.append(req)
                if error: raise error
                response = urllib.response.addinfourl(UnreadableBody(b'PRIVATE BODY'), headers or Message(), response_url or req.full_url, code)
                response.msg = 'synthetic'
                return response
        # Preserve production opener composition; replace only the socket transport.
        with patch.object(urllib.request, 'HTTPSHandler', SyntheticHTTPS):
            client = a.Client('SECRET TOKEN')
        return client, seen

    def test_direct_404_success_credential_free_and_cache(self):
        client, seen = self.client()
        client.verify_private(self.url);client.verify_private(self.url)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].get_method(), 'GET')
        self.assertIsNone(seen[0].get_header('Authorization'))
        self.assertIsNone(seen[0].get_header('Cookie'))
        self.assertEqual(seen[0].get_header('Accept'), 'application/octet-stream')
        self.assertIn(self.url, client.direct_privacy_verified)

    def test_redirects_never_followed_or_accepted(self):
        for code in (301,302,303,307,308):
            for target in ('https://unrelated.invalid/private?secret=TOKEN','http://[invalid','https://api.github.com/other'):
                with self.subTest(code=code,target=target):
                    headers=Message();headers['Location']=target
                    client, seen=self.client(code,headers)
                    with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
                    self.assertEqual(caught.exception.diagnostic['status'],code)
                    self.assertEqual(len(seen),1)
                    self.assertNotIn(self.url,client.direct_privacy_verified)
                    self.assertNotIn(target,str(caught.exception))

    def test_all_non404_fail_closed_no_retry(self):
        for code in (200,201,204,300,304,400,401,403,410,429,500,503,404.0):
            with self.subTest(code=code):
                client,seen=self.client(code)
                with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
                self.assertEqual(caught.exception.diagnostic['status'],code if type(code) is int else None)
                self.assertEqual(len(seen),1)
                self.assertFalse(client.direct_privacy_verified)

    def test_bounded_allowlisted_diagnostics(self):
        headers=Message()
        for k,v in {'X-GitHub-Request-Id':'AB12:1234:DEAD:BEEF','X-RateLimit-Limit':'60','X-RateLimit-Remaining':'0','X-RateLimit-Reset':'1794150000','X-RateLimit-Used':'60','Retry-After':'120','X-RateLimit-Resource':'core','Location':'https://secret.invalid/TOKEN','Set-Cookie':'SECRET','Authorization':'Bearer SECRET'}.items():headers[k]=v
        for code in (403,429):
            client,seen=self.client(code,headers)
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
            d=caught.exception.diagnostic
            self.assertEqual(d['x-github-request-id'],'AB12:1234:DEAD:BEEF')
            self.assertEqual(d['retry-after'],'120')
            self.assertEqual(d['endpoint_role'],'asset')
            self.assertEqual(d['endpoint_path'],'/repos/'+a.REPO+'/releases/assets/7')
            self.assertLess(len(json.dumps(d)),900)
            self.assertNotIn('SECRET',str(caught.exception));self.assertNotIn('https://',str(caught.exception))

    def test_malformed_duplicate_oversized_headers_omitted(self):
        for value in ('SECRET URL https://secret.invalid','0\r\nSECRET','9'*129,'-1',' 0','０'):
            headers=Message()
            for name in ('X-GitHub-Request-Id','X-RateLimit-Limit','X-RateLimit-Remaining','X-RateLimit-Reset','X-RateLimit-Used','Retry-After','X-RateLimit-Resource'):headers[name]=value
            client,_=self.client(403,headers)
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
            self.assertEqual(set(caught.exception.diagnostic),{'method','endpoint_role','endpoint_path','status','outcome'})
        headers=Message();headers['X-RateLimit-Remaining']='0';headers['x-ratelimit-remaining']='1'
        self.assertEqual(a.privacy_headers(headers),{})

    def test_response_endpoint_mismatch_rejected(self):
        for target in ('https://unrelated.invalid/missing',self.url+'?secret=TOKEN',self.url+'/',self.url.replace('https:','http:'),self.url.replace('api.github.com','api.github.com:443')):
            client,seen=self.client(response_url=target)
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
            self.assertEqual(caught.exception.diagnostic['outcome'],'response_endpoint_mismatch')
            self.assertNotIn(target,str(caught.exception));self.assertFalse(client.direct_privacy_verified)

    def test_network_and_value_errors_sanitized(self):
        for error in (urllib.error.URLError('https://SECRET.invalid/TOKEN'),TimeoutError('SECRET'),ValueError('SECRET'),urllib.error.HTTPError(self.url,404,'SECRET',Message(),None)):
            client,seen=self.client(error=error)
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
            self.assertEqual(caught.exception.diagnostic['outcome'],'transport_error')
            self.assertNotIn('SECRET',str(caught.exception));self.assertEqual(len(seen),1)

    def test_invalid_endpoint_no_request(self):
        for url in (self.url+'?token=SECRET',self.url.replace('https://','https://user:SECRET@'),self.url.replace('api.github.com','uploads.github.com'),a.API+'/releases/0',a.API+'/releases/'+'1'*21):
            client,seen=self.client()
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(url)
            self.assertEqual(seen,[]);self.assertNotIn('SECRET',str(caught.exception))

    def test_legacy_cache_cannot_promote_old_verification(self):
        client,seen=self.client(403);client.anonymous_verified={self.url}
        with self.assertRaises(a.PrivacyCheckError):client.verify_private(self.url)
        self.assertEqual(len(seen),1)

    def test_failed_attempt_preserves_history_and_health(self):
        client,seen=self.client(403)
        import archive_durable as durable
        from test_archive_durable import Server
        server = Server()
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'out'
            with patch.object(sys, 'argv', ['archive', '--report-dir', str(out)]), \
                 patch.dict(os.environ, {'GH_TOKEN': 'synthetic', 'GITHUB_RUN_ID': '1', 'GITHUB_RUN_ATTEMPT': '1'}), \
                 patch.object(durable, 'GraphQL', return_value=server), \
                 patch.object(a, 'Client', return_value=client), \
                 patch.object(a, 'run', side_effect=lambda c: c.verify_private(self.url)):
                with self.assertRaises(RuntimeError): a.main()
            self.assertEqual(server.files['archive-health.json'], 'OLD_HEALTH')
            self.assertEqual(server.files['archive-manifests/old.json'], 'HISTORY')
            attempt = json.loads(server.files['archive-attempt.json'])
            self.assertEqual(attempt['status'], 'review_hold')
            self.assertEqual(attempt['privacy_check']['method'], a.PRIVACY_METHOD)
            self.assertEqual(attempt['privacy_check']['status'], 403)
            self.assertFalse((out / 'report.json').exists())
            self.assertEqual(json.loads((out / 'attempt.json').read_text())['status'], 'REQUIRES_REVIEW')

    def test_configured_proxy_route_is_preserved(self):
        with patch.object(urllib.request,'getproxies',return_value={'https':'http://proxy.invalid:8080'}):
            client=a.Client('SECRET TOKEN')
        handlers=[h for h in client.privacy_opener.handlers if isinstance(h,urllib.request.ProxyHandler)]
        self.assertEqual(len(handlers),1)
        self.assertEqual(handlers[0].proxies,{'https':'http://proxy.invalid:8080'})

    def test_missing_response_origin_fails_closed(self):
        client,_=self.client()
        class Response:
            code=404
            headers=Message()
            def geturl(self):return None
            def close(self):pass
        with patch.object(client.privacy_opener,'open',return_value=Response()):
            with self.assertRaises(a.PrivacyCheckError) as caught:client.verify_private(self.url)
        self.assertEqual(caught.exception.diagnostic['outcome'],'response_endpoint_mismatch')

    def test_new_success_manifest_identifies_stronger_method(self):
        class Client:
            def json(self,url):
                if '/workflows/' in url:return {'workflow_runs':[{'id':1,'status':'completed','head_branch':'main','event':'schedule'}]}
                return {'total_count':1,'artifacts':[{'id':7,'name':'company-monitor-fixture','digest':'sha256:'+'a'*64}]}
        with patch.object(a,'PINS',{}),patch.object(a,'draft_for',return_value={'id':1,'tag_name':'fixture'}),patch.object(a,'archive_one',return_value={'synthetic':True}):
            result=a.run(Client())
        self.assertEqual(result['privacy_verification_method'],'direct-api-404-no-redirect-v2')
