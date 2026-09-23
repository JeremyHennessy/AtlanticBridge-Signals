"""Retain exact source artifacts in non-public draft assets; never publish a release.

Adds a verified copy outside Actions expiry, not immutable or off-site storage.
No collector, source ledger or existing checkpoint contract is changed.
"""
from __future__ import annotations
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from atlanticbridge.company_sources import Ledger
from atlanticbridge.monitoring_checkpoint import validate, restore, checkpoint, health

REPO = 'JeremyHennessy/AtlanticBridge-Signals'
API = 'https://api.github.com/repos/' + REPO
MAX_BYTES = 128 * 1024 * 1024
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

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('Non-HTTPS download redirect')
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected and urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            redirected.remove_header('Authorization')
        return redirected

class Client:
    def __init__(self, token: str):
        if not token: raise ValueError('Authenticated archive token required')
        self.token = token
        self.opener = urllib.request.build_opener(SafeRedirect())
    def request(self, url: str, method='GET', body=None, *, auth=True, binary=False, mime='application/json'):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'https' or parsed.hostname not in {'api.github.com', 'uploads.github.com', 'github.com'} or parsed.username or parsed.password:
            raise ValueError('Unapproved GitHub endpoint')
        headers = {'User-Agent':'AtlanticBridge-evidence-retention', 'Accept':'application/octet-stream' if binary and '/releases/assets/' in parsed.path else 'application/vnd.github+json', 'X-GitHub-Api-Version':'2026-03-10', 'Content-Type':mime}
        if auth: headers['Authorization'] = 'Bearer ' + self.token
        if isinstance(body, dict): body = json.dumps(body).encode()
        try:
            with self.opener.open(urllib.request.Request(url, data=body, method=method, headers=headers), timeout=60) as response:
                raw=response.read(MAX_BYTES+1)
                if len(raw)>MAX_BYTES: raise ValueError('Download exceeds bounded archive size')
                return response.status, raw
        except urllib.error.HTTPError as exc:
            return exc.code, b''  # Never expose credentials or signed URLs in error bodies.
    def json(self, url, method='GET', body=None):
        code, raw = self.request(url, method, body)
        if code not in (200,201): raise ValueError(f'GitHub archive request failed: HTTP {code}')
        return json.loads(raw)
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

def inspect_checkpoint(raw: bytes, observed_health: dict):
    value=validate(json.loads(raw))
    if health(value)!=observed_health: raise ValueError('Checkpoint does not match captured monitoring health')
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
        asset=json.loads(data)
    endpoint=API+f"/releases/assets/{asset['id']}"
    code, restored=client.request(endpoint,binary=True)
    if code!=200 or restored!=raw:raise ValueError('Existing/uploaded archive asset differs; never overwrite it')
    # Verify the release once and each asset API independently. Caching the identical
    # release check avoids exhausting anonymous rate limits during bounded backfill.
    if not hasattr(client,'anonymous_verified'):client.anonymous_verified=set()
    for url in (API+f"/releases/{release['id']}",endpoint):
        if url in client.anonymous_verified:continue
        code,_=client.request(url,auth=False,binary=True)
        if code!=404:raise ValueError(f'Draft privacy check failed or inconclusive: HTTP {code}')
        client.anonymous_verified.add(url)
    require_draft(client.json(API+f"/releases/{release['id']}"))
    return {'asset_id':asset['id'],'name':name,'sha256':sha(restored),'size':len(restored),'byte_restore_verified':True,'anonymous_access_status':404},restored

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
        observed=json.loads(z.read('health.json'))
        run_id=str(artifact['workflow_run']['id'])+'-'+str(observed['run_id'].split('-')[-1])
        if observed['run_id']!=run_id:raise ValueError('Captured health belongs to a different run')
        state=client.json(API+'/contents/checkpoint.json?ref='+data_sha)
        extra=base64.b64decode(state['content']);restore_result=inspect_checkpoint(extra,observed)
        restore_result['data_commit']=data_sha
    asset,back=store_asset(client,release,f'artifact-{artifact_id}-{expected[:16]}.zip',raw)
    inspect_zip(back,expected)
    result={'artifact_id':artifact_id,'original_workflow_run':artifact['workflow_run']['id'],'raw_response_count':raw_count,'archive_asset':asset}
    if extra:
        cp,back=store_asset(client,release,f"checkpoint-{data_sha}-{sha(extra)[:16]}.json",extra)
        inspect_checkpoint(back,observed)
        result.update(checkpoint_asset=cp,restore=restore_result)
    return result

def accepted_proof(client, artifact_id):
    """Prefer the accepted exact artifact, then the verified unpublished archive copy."""
    if artifact_id not in PINS:raise ValueError('Unapproved source-proof artifact')
    expected=PINS[artifact_id]
    code,metadata=client.request(API+f'/actions/artifacts/{artifact_id}')
    if code==200:
        info=json.loads(metadata)
        if info.get('expired') is not True:
            status,raw=client.request(API+f'/actions/artifacts/{artifact_id}/zip',binary=True)
            if status==200:
                inspect_zip(raw,expected);return info,raw
            if status not in (404,410):raise ValueError(f'Proof download failed: HTTP {status}')
    elif code not in (404,410):raise ValueError(f'Proof metadata failed: HTTP {code}')
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
    now=datetime.now(timezone.utc).isoformat();release=draft_for(client,'evidence-v1-'+now[:7])
    artifacts=[]
    for aid,expected in PINS.items():
        metadata,raw=accepted_proof(client,aid)
        artifacts.append(archive_one(client,metadata,expected,release,raw_override=raw))
    runs=client.json(API+'/actions/workflows/company-monitor.yml/runs?branch=main&per_page=20')['workflow_runs']
    found=0
    for run in runs:
        if run['status']!='completed' or run['head_branch']!='main' or run['event'] not in {'push','schedule','workflow_dispatch'}:continue
        rows=client.json(API+f"/actions/runs/{run['id']}/artifacts?per_page=100")
        if rows['total_count']>100:raise ValueError('Monitor artifact pagination requires explicit handling')
        for artifact in rows['artifacts']:
            if not artifact['name'].startswith('company-monitor-'):continue
            digest=artifact.get('digest','')
            if not digest.startswith('sha256:'):raise ValueError('Missing GitHub artifact digest')
            artifacts.append(archive_one(client,artifact,digest[7:],release,True));found+=1
    if not found:raise ValueError('No completed production monitor artifact to archive')
    return {'schema_version':1,'status':'VERIFIED_DRAFT_COPY','verified_at':now,'archive_run_id':os.environ.get('GITHUB_RUN_ID'),'code_commit':os.environ.get('GITHUB_SHA'),'release_id':release['id'],'release_tag':release['tag_name'],'draft':True,'items':artifacts,'production_monitor_artifacts_archived':found,'monitor_run_scan_window':20,'retention_policy':'Retain while referenced, at least 18 months from capture; no automatic deletion. GitHub draft assets have no Actions artifact expiration clock.','limitations':['Same-provider mutable/deletable backup, not immutable storage or an off-site copy.','An access-controlled copy does not grant commercial redistribution rights.','Does not establish elapsed operational reliability, completed company qualification or predictive validity.']}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--state-dir',required=True);ap.add_argument('--report-dir',required=True);args=ap.parse_args()
    state=Path(args.state_dir);out=Path(args.report_dir);out.mkdir(parents=True,exist_ok=True)
    attempt={'schema_version':1,'run_id':os.environ.get('GITHUB_RUN_ID'),'attempt_at':datetime.now(timezone.utc).isoformat(),'status':'FAILED'}
    try:
        result=run(Client(os.environ.get('GH_TOKEN','')))
        attempt['status']='VERIFIED_DRAFT_COPY'
        state.mkdir(parents=True,exist_ok=True)
        (state/'archive-health.json').write_text(json.dumps(result,indent=2)+'\n')
        manifests=state/'archive-manifests';manifests.mkdir(exist_ok=True)
        (manifests/(str(os.environ.get('GITHUB_RUN_ID','local'))+'.json')).write_text(json.dumps(result,indent=2)+'\n')
        (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    except Exception as exc:
        attempt['error_type']=type(exc).__name__
        if type(exc) is ValueError:attempt['detail']=str(exc)
        # Exception text may contain signed HTTP URLs. Keep diagnostics credential-free.
        raise RuntimeError('Evidence archive failed: '+type(exc).__name__) from None
    finally:
        state.mkdir(parents=True,exist_ok=True)
        (state/'archive-attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
        (out/'attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')

if __name__=='__main__':main()
