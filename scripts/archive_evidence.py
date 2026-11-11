"""Retain exact source artifacts in non-public draft assets; never publish a release.

Adds a verified copy outside Actions expiry, not immutable or off-site storage.
No collector, source ledger or existing checkpoint contract is changed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from atlanticbridge.company_sources import Ledger
from atlanticbridge.monitoring_checkpoint import validate, restore, checkpoint, health

REPO = 'JeremyHennessy/AtlanticBridge-Signals'
API = 'https://api.github.com/repos/' + REPO
PRIVACY_METHOD = 'direct-api-404-no-redirect-v2'
# Defense in depth only, not a shared-IP or cross-run rate allowance.
MAX_PRIVACY_REQUESTS = 48
MAX_BYTES = 128 * 1024 * 1024
MAX_CHECKPOINT_BYTES = 16 * 1024 * 1024
PINS = {
    10718724645: '46f6e0853b6848cc10d5982e54bebeac2bf810e6e3ede19062b470e6c39a75a6',
    10724109813: '6f5f5b169681f0bbc0b01d116f97cb3ee0a254385619f094cd101d8c98c415cc',
    10717489758: '003c42f02705066074a87bc5cac33ac0c72833d1c4a03bed3b01a1c5b660874a',
    10720884358: 'db6e1b2055d27d3bf945a2c2ce228321b3425d1dea4c6baaf4d9d78f7713e802',
    10724340100: 'eb1a6546cf4306118d0dc77cbb7e665468230a169cefed7ed5dc56ef52acaf0a',
    10729310481: '478167783afbd109deccc8a4576252fef895a67c9585ce8c61c45ae937336365',
    10729682735: '39892597bcdf03f6ba7e093ece34c7618f0dff8450d8c77c30951745b1ff2064',
}

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def parse_json(raw: bytes | str, context: str):
    """Decode JSON while retaining only safe source context, never response bodies."""
    try:
        return json.loads(raw)
    except UnicodeDecodeError:
        raise ValueError(f'{context} was not valid JSON (invalid text encoding)') from None
    except json.JSONDecodeError as exc:
        raise ValueError(
            f'{context} was not valid JSON (line {exc.lineno}, column {exc.colno})'
        ) from None

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Non-HTTPS download redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            redirected.remove_header('Authorization')
        return redirected


class ActionsOnlyRedirect(SafeRedirect):
    """Allow ZIP transport only to documented Actions artifact blob storage.

    Metadata must be returned directly. Never follow a redirect to a GitHub
    release/API/browser route, and never send the origin token to blob storage.
    Unknown storage domains fail closed rather than widening this boundary.
    Domain reference: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
    """
    def __init__(self, *, binary):
        super().__init__()
        self.binary = binary

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            target = urllib.parse.urlsplit(newurl)
            storage = (target.hostname == 'results-receiver.actions.githubusercontent.com'
                       or re.fullmatch(r'[a-z0-9]{3,24}\.blob\.core\.windows\.net', target.hostname or ''))
            if (not self.binary or target.scheme != 'https' or not storage
                    or target.fragment or target.port not in (None, 443)
                    or target.username or target.password):
                raise ValueError('Refused')
            redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        except ValueError:
            # Parser exceptions can include credentials or signed URL components.
            raise ValueError('Actions-only proof redirect refused') from None
        if redirected:
            redirected.remove_header('Authorization')
        return redirected

    def http_error_302(self, req, fp, code, msg, headers):
        try:
            return super().http_error_302(req, fp, code, msg, headers)
        except ValueError:
            # urllib parses Location before calling redirect_request as well.
            raise ValueError('Actions-only proof redirect refused') from None

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302

class PrivacyResponseProcessor(urllib.request.HTTPErrorProcessor):
    """Inspect the original response, without redirect/error URL rewriting."""
    def http_response(self, request, response):
        return response
    https_response = http_response

class PrivacyCheckError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__('Draft privacy check failed or inconclusive: ' + json.dumps(diagnostic, sort_keys=True))

def privacy_headers(headers):
    """Small fixed allowlist; reject duplicates, oversized and malformed values."""
    result = {}
    patterns = {
        'X-GitHub-Request-Id': r'[0-9A-Fa-f]{1,16}(?::[0-9A-Fa-f]{1,16}){1,7}',
        'X-RateLimit-Limit': r'[0-9]{1,12}',
        'X-RateLimit-Remaining': r'[0-9]{1,12}',
        'X-RateLimit-Used': r'[0-9]{1,12}',
        'X-RateLimit-Reset': r'[0-9]{1,12}',
        'Retry-After': r'[0-9]{1,12}',
        'X-RateLimit-Resource': r'(?:core|search|graphql|integration_manifest)',
    }
    for name, pattern in patterns.items():
        values = headers.get_all(name, [])
        if len(values) == 1 and isinstance(values[0], str) and len(values[0]) <= 128 and re.fullmatch(pattern, values[0]):
            result[name.lower()] = values[0]
    return result

class Client:
    def __init__(self, token: str):
        if not token: raise ValueError('Authenticated archive token required')
        self.token = token
        self.phase = 'startup'
        self.opener = urllib.request.build_opener(SafeRedirect())
        # No origin credentials/cookies or redirects; preserve configured proxy routing.
        self.privacy_opener = urllib.request.build_opener(PrivacyResponseProcessor())
        self.direct_privacy_verified = set()
        self.privacy_request_count = 0
        self._privacy_review_hold = False
        self._privacy_lock = threading.Lock()
    def verify_private(self, url):
        # Serialize reservations and outcomes, including concurrent direct callers.
        with self._privacy_lock:
            if self._privacy_review_hold:
                raise PrivacyCheckError({'method': PRIVACY_METHOD, 'outcome': 'client_review_hold'})
            try:
                return self._verify_private_locked(url)
            except BaseException:
                # Includes cancellation: an unknown outcome cannot be retried.
                self._privacy_review_hold = True
                raise
    def _verify_private_locked(self, url):
        # Exact origin and bounded numeric path only; never log untrusted URLs.
        match = re.fullmatch(re.escape(API) + r'/releases/(assets/)?([1-9][0-9]{0,19})', url)
        if not match:
            raise PrivacyCheckError({'method': PRIVACY_METHOD, 'outcome': 'invalid_endpoint'})
        diagnostic = {'method': PRIVACY_METHOD, 'endpoint_role': 'asset' if match[1] else 'release',
                      'endpoint_path': url[len('https://api.github.com'):], 'status': None}
        if url in self.direct_privacy_verified:
            return
        if self.privacy_request_count >= MAX_PRIVACY_REQUESTS:
            diagnostic['outcome'] = 'privacy_request_budget_exhausted'
            raise PrivacyCheckError(diagnostic)
        # Reserve before transport. Failure/cancellation never refunds a request.
        self.privacy_request_count += 1
        headers = {'User-Agent': 'AtlanticBridge-evidence-retention',
                   'Accept': 'application/octet-stream' if match[1] else 'application/vnd.github+json',
                   'X-GitHub-Api-Version': '2026-03-10'}
        response = None
        try:
            response = self.privacy_opener.open(urllib.request.Request(url, headers=headers), timeout=60)
            code = response.code
            if type(code) is int and 100 <= code <= 599:
                diagnostic['status'] = code
            if response.geturl() != url:
                diagnostic['outcome'] = 'response_endpoint_mismatch'
            else:
                diagnostic.update(privacy_headers(response.headers))
                diagnostic['outcome'] = 'direct_404' if type(code) is int and code == 404 else 'non_404'
        except Exception:
            # Exception messages and bodies can contain credentials/signed URLs.
            diagnostic['outcome'] = 'transport_error'
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    diagnostic['outcome'] = 'transport_error'
        if diagnostic.get('outcome') != 'direct_404':
            raise PrivacyCheckError(diagnostic) from None
        self.direct_privacy_verified.add(url)
    def request(self, url: str, method='GET', body=None, *, auth=True, binary=False, mime='application/json', actions_only=False):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'uploads.github.com', 'github.com'} or parsed.username or parsed.password:
            raise ValueError('Unapproved GitHub endpoint')
        if actions_only:
            path = '/repos/' + REPO + '/actions/artifacts/'
            suffix = '/zip' if binary else ''
            if (parsed.scheme != 'https' or parsed.netloc != 'api.github.com'
                    or not re.fullmatch(re.escape(path) + r'[1-9][0-9]*' + suffix, parsed.path)
                    or parsed.query or parsed.fragment or method != 'GET'
                    or body is not None or not auth):
                raise ValueError('Actions-only proof endpoint refused')
        accept = 'application/vnd.github+json'
        if binary and parsed.path.startswith('/repos/'+REPO+'/contents/'):
            accept = 'application/vnd.github.raw+json'
        elif binary and '/releases/assets/' in parsed.path:
            accept = 'application/octet-stream'
        headers = {'User-Agent':'AtlanticBridge-evidence-retention', 'Accept':accept, 'X-GitHub-Api-Version':'2026-03-10', 'Content-Type':mime}
        if auth: headers['Authorization'] = 'Bearer ' + self.token
        if isinstance(body, dict): body = json.dumps(body).encode()
        opener = (urllib.request.build_opener(ActionsOnlyRedirect(binary=binary))
                  if actions_only else self.opener)
        try:
            with opener.open(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=60) as response:
                raw=response.read(MAX_BYTES+1)
                if len(raw)>MAX_BYTES: raise ValueError('Download exceeds bounded archive size')
                return response.status, raw
        except urllib.error.HTTPError as exc:
            return exc.code, b''  # Never expose credentials or signed URLs in error bodies.
    def json(self, url, method='GET', body=None):
        code, raw = self.request(url, method, body)
        if code not in (200,201): raise ValueError(f'GitHub archive request failed: HTTP {code}')
        endpoint=urllib.parse.urlsplit(url).path
        return parse_json(raw, f'GitHub API {method} {endpoint} (HTTP {code}, bytes {len(raw)})')
    def pages(self, path):
        rows=[]
        for page in range(1,21):
            part=self.json(API+path+('&' if '?' in path else '?')+f'per_page=100&page={page}')
            if not isinstance(part,list): raise ValueError('Expected paginated list')
            rows.extend(part)
            if len(part)<100:return rows
        raise ValueError('Archive inventory pagination cap exceeded')

def inspect_zip(raw: bytes, expected: str):
    if not re.fullmatch('[0-9a-f]{64}',expected) or sha(raw)!=expected: raise ValueError('Artifact checksum mismatch')
    z=zipfile.ZipFile(io.BytesIO(raw));names=z.namelist()
    if len(names)!=len(set(names)) or len(names)>10000 or sum(x.file_size for x in z.infolist())>MAX_BYTES: raise ValueError('Oversized or duplicate artifact')
    for item in z.infolist():
        p=PurePosixPath(item.filename)
        if p.is_absolute() or '..' in p.parts or '\\' in item.filename or (item.external_attr>>16)&0o170000==0o120000: raise ValueError('Unsafe archive entry')
    count=0
    for name in names:
        if name.endswith('.bin') and '/raw/' in '/'+name:
            expected_raw=PurePosixPath(name).stem
            if not re.fullmatch('[0-9a-f]{64}',expected_raw) or sha(z.read(name))!=expected_raw: raise ValueError('Raw response checksum mismatch')
            count+=1
    if not count: raise ValueError('Archive contains no retained raw responses')
    return z,count

LEGACY_ADDITIVE_HEALTH_FIELDS = {'operational_source_count', 'reliability_scope'}

def inspect_checkpoint(raw: bytes, observed_health: dict):
    value=validate(parse_json(raw,'retained checkpoint.json'))
    expected_health=health(value)
    if not isinstance(observed_health,dict):
        raise ValueError('Checkpoint does not match captured monitoring health')
    missing=set(expected_health)-set(observed_health)
    extra=set(observed_health)-set(expected_health)
    # Historical monitor artifacts predate these derived cohort-health fields.
    # Permit only their absence; every field actually captured must still match exactly.
    if extra or (missing-LEGACY_ADDITIVE_HEALTH_FIELDS) or any(expected_health[k]!=v for k,v in observed_health.items()):
        raise ValueError('Checkpoint does not match captured monitoring health')
    with tempfile.TemporaryDirectory() as tmp:
        ledger=Ledger(str(Path(tmp)/'restore.sqlite'))
        restore(ledger,value)
        if ledger.db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Restored SQLite integrity failure')
        recovered=checkpoint(ledger,runs=value['runs'])
        ledger.db.close()
        if recovered!=value: raise ValueError('Restoration changed original clocks, fingerprints or source state')
    return {'checkpoint_checksum':value['checksum'],'run_id':observed_health['run_id'],
            'observations':len(value['tables']['company_observations']),
            'sqlite_integrity':'ok','exact_state_restore':True,'successful_days':observed_health['successful_days']}

def require_draft(release):
    if release.get('draft') is not True or release.get('published_at') is not None:
        raise ValueError('Evidence archive must remain an unpublished draft')

def draft_for(client, tag):
    matches=[x for x in client.pages('/releases') if x.get('tag_name')==tag]
    if len(matches)>1: raise ValueError('Ambiguous archive release')
    if matches:
        release=matches[0];require_draft(release);return release
    main=client.json(API+'/git/ref/heads/main')['object']['sha']
    release=client.json(API+'/releases','POST',{'tag_name':tag,'target_commitish':main,'name':'Restricted evidence archive '+tag,'body':'Operational evidence backup. MUST REMAIN DRAFT. Not commercially reusable content. No automatic expiry; mutable/deletable, same-provider storage. Do not publish or remove while referenced.','draft':True,'prerelease':True,'make_latest':'false'})
    require_draft(release);return release

def store_asset(client, release, name, raw):
    require_draft(client.json(API+f"/releases/{release['id']}"))
    matches=[a for a in client.pages(f"/releases/{release['id']}/assets") if a['name']==name]
    if len(matches)>1:raise ValueError('Duplicate archive asset name')
    if matches: asset=matches[0]
    else:
        url='https://uploads.github.com/repos/'+REPO+f"/releases/{release['id']}/assets?name="+urllib.parse.quote(name,safe='')
        code,data=client.request(url,'POST',raw,mime='application/octet-stream')
        if code!=201:raise ValueError(f'Archive upload failed: HTTP {code}')
        asset=parse_json(data,'GitHub release asset upload response')
    endpoint=API+f"/releases/assets/{asset['id']}"
    code, restored=client.request(endpoint,binary=True)
    if code!=200 or restored!=raw:raise ValueError('Existing/uploaded archive asset differs; never overwrite it')
    # Verify the release once and each asset API independently. Caching the identical
    # release check avoids exhausting anonymous rate limits during bounded backfill.
    for url in (API+f"/releases/{release['id']}",endpoint):
        client.verify_private(url)
    require_draft(client.json(API+f"/releases/{release['id']}"))
    return {'asset_id':asset['id'],'name':name,'sha256':sha(restored),'size':len(restored),'byte_restore_verified':True,'anonymous_access_status':404,'privacy_verification_method':PRIVACY_METHOD},restored

def archive_one(client, artifact, expected, release, monitoring=False, raw_override=None):
    artifact_id=int(artifact['id'])
    digest=artifact.get('digest')
    if digest and digest!='sha256:'+expected:raise ValueError('API artifact checksum conflicts with expected proof')
    if raw_override is None:
        code,raw=client.request(API+f'/actions/artifacts/{artifact_id}/zip',binary=True)
        if code!=200:raise ValueError(f'Source artifact unavailable: HTTP {code}')
    else:raw=raw_override
    z,raw_count=inspect_zip(raw,expected)
    extra=None;restore_result=None
    if monitoring:
        data_sha=z.read('data-commit.txt').decode().strip()
        if not re.fullmatch('[0-9a-f]{40}',data_sha):raise ValueError('Missing exact data-state revision')
        observed=parse_json(z.read('health.json'),'retained health.json')
        run_id=str(artifact['workflow_run']['id'])+'-'+str(observed['run_id'].split('-')[-1])
        if observed['run_id']!=run_id:raise ValueError('Captured health belongs to a different run')
        # Inline Contents API base64 is omitted above 1 MB. Request the original
        # raw bytes at the artifact's immutable state commit, never a moving ref.
        status,extra=client.request(API+'/contents/checkpoint.json?ref='+data_sha,binary=True)
        if status!=200:raise ValueError(f'Pinned checkpoint download failed: HTTP {status}')
        if not 0<len(extra)<=MAX_CHECKPOINT_BYTES:raise ValueError('Pinned checkpoint is empty or exceeds the size limit')
        restore_result=inspect_checkpoint(extra,observed)
        restore_result['data_commit']=data_sha
    asset,back=store_asset(client,release,f'artifact-{artifact_id}-{expected[:16]}.zip',raw)
    inspect_zip(back,expected)
    result={'artifact_id':artifact_id,'original_workflow_run':artifact['workflow_run']['id'],'raw_response_count':raw_count,'archive_asset':asset}
    if extra:
        cp,back=store_asset(client,release,f"checkpoint-{data_sha}-{sha(extra)[:16]}.json",extra)
        inspect_checkpoint(back,observed)
        result.update(checkpoint_asset=cp,restore=restore_result)
    return result

def accepted_proof(client, artifact_id, *, actions_only=False):
    """Read exact pinned proof; Actions-only callers never consult retained releases."""
    if artifact_id not in PINS:raise ValueError('Unapproved source-proof artifact')
    expected=PINS[artifact_id]
    transport={'actions_only':True} if actions_only else {}
    code,metadata=client.request(API+f'/actions/artifacts/{artifact_id}',**transport)
    if code==200:
        info=parse_json(metadata,'GitHub Actions artifact metadata')
        if actions_only:
            if (not isinstance(info,dict) or type(info.get('id')) is not int
                    or info['id'] != artifact_id or info.get('expired') is not False
                    or not isinstance(info.get('workflow_run'),dict)
                    or type(info['workflow_run'].get('id')) is not int
                    or info['workflow_run']['id'] <= 0):
                raise ValueError('Actions-only proof requires exact, unexpired artifact metadata and original run provenance')
        if info.get('expired') is not True:
            status,raw=client.request(API+f'/actions/artifacts/{artifact_id}/zip',binary=True,**transport)
            if status==200:
                inspect_zip(raw,expected);return info,raw
            if status not in (404,410):raise ValueError(f'Proof download failed: HTTP {status}')
    elif code not in (404,410):raise ValueError(f'Proof metadata failed: HTTP {code}')
    if actions_only:
        raise ValueError('Actions-only proof unavailable; retained release fallback is disabled')
    name=f'artifact-{artifact_id}-{expected[:16]}.zip'
    for release in client.pages('/releases'):
        if not release.get('tag_name','').startswith('evidence-v1-'):continue
        require_draft(release)
        assets=[a for a in client.pages(f"/releases/{release['id']}/assets") if a['name']==name]
        if len(assets)>1:raise ValueError('Ambiguous archived proof')
        if not assets:continue
        status,raw=client.request(API+f"/releases/assets/{assets[0]['id']}",binary=True)
        if status!=200:raise ValueError('Archived proof unavailable')
        inspect_zip(raw,expected)
        return {'id':artifact_id,'workflow_run':{'id':None},'provenance':'Recovered exact pinned bytes; original run is in retained acceptance records'},raw
    raise ValueError('Accepted proof missing from both Actions and unpublished archives')

def run(client):
    now=datetime.now(timezone.utc).isoformat()
    client.phase='draft_release'
    release=draft_for(client,'evidence-v1-'+now[:7])
    artifacts=[]
    client.phase='pinned_proofs'
    for aid,expected in PINS.items():
        metadata,raw=accepted_proof(client,aid)
        artifacts.append(archive_one(client,metadata,expected,release,raw_override=raw))
    client.phase='monitor_run_inventory'
    runs=client.json(API+'/actions/workflows/company-monitor.yml/runs?branch=main&per_page=20')['workflow_runs']
    found=0
    for run in runs:
        client.phase='monitor_run_artifacts'
        if run['status']!='completed' or run['head_branch']!='main' or run['event'] not in {'push','schedule','workflow_dispatch'}:continue
        rows=client.json(API+f"/actions/runs/{run['id']}/artifacts?per_page=100")
        if rows['total_count']>100:raise ValueError('Monitor artifact pagination requires explicit handling')
        for artifact in rows['artifacts']:
            if not artifact['name'].startswith('company-monitor-'):continue
            client.phase='monitor_artifact_'+str(artifact['id'])
            digest=artifact.get('digest','')
            if not digest.startswith('sha256:'):raise ValueError('Missing GitHub artifact digest')
            artifacts.append(archive_one(client,artifact,digest[7:],release,True));found+=1
    if not found:raise ValueError('No completed production monitor artifact to archive')
    return {'schema_version':1,'privacy_verification_method':PRIVACY_METHOD,'status':'VERIFIED_DRAFT_COPY','verified_at':now,'archive_run_id':os.environ.get('GITHUB_RUN_ID'),'code_commit':os.environ.get('GITHUB_SHA'),'release_id':release['id'],'release_tag':release['tag_name'],'draft':True,'items':artifacts,'production_monitor_artifacts_archived':found,'monitor_run_scan_window':20,'retention_policy':'Retain while referenced, at least 18 months from capture; no automatic deletion. GitHub draft assets have no Actions artifact expiration clock.','limitations':['Same-provider mutable/deletable backup, not immutable storage or an off-site copy.','An access-controlled copy does not grant commercial redistribution rights.','Does not establish elapsed operational reliability, completed company qualification or predictive validity.']}

def main():
    # Single executable entrypoint: no archive client before durable reservation.
    from archive_durable import ArchiveRun, GraphQL, Store
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report-dir', required=True)
    ap.add_argument('--migration-receipt', help='Explicit first-run migration receipt; never a privacy proof')
    args = ap.parse_args()
    out = Path(args.report_dir).absolute()
    # Refuse reused outputs/symlink ancestry before any remote state operation.
    if any(parent.is_symlink() for parent in out.parents):
        raise RuntimeError('Unsafe archive report directory')
    out.mkdir(mode=0o700, parents=True, exist_ok=False)
    report_fd = os.open(out, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    def write_report(name, value):
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=report_fd)
        with os.fdopen(fd, 'w') as stream:
            stream.write(json.dumps(value, indent=2) + '\n')
    token = os.environ.get('GH_TOKEN', '')
    owner = os.environ.get('GITHUB_RUN_ID', '') + '-' + os.environ.get('GITHUB_RUN_ATTEMPT', '')
    attempt = {'status': 'REQUIRES_REVIEW'}
    try:
        receipt = None
        if args.migration_receipt:
            from archive_migration import load_json
            receipt = load_json(args.migration_receipt, 8192)
        runner = ArchiveRun(Store(GraphQL(token)), owner, migration_receipt=receipt)
        result = runner.execute(lambda: Client(token), run)
        write_report('report.json', result)
        attempt = {'status': 'VERIFIED_DRAFT_COPY', 'owner': owner}
    except Exception:
        raise RuntimeError('Evidence archive requires review; no retry authorized') from None
    finally:
        try:
            write_report('attempt.json', attempt)
        finally:
            os.close(report_fd)

if __name__ == '__main__':
    main()
