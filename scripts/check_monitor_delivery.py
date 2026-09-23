"""Detect a missed UTC collection and dispatch the unchanged canonical monitor.

Does not modify source state or treat a dispatch as a successful collection.
Failures and disabled workflows need review, not an automatic reset/retry.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

REPO = 'repos/JeremyHennessy/AtlanticBridge-Signals'
PATH = '/actions/workflows/company-monitor.yml'

def instant(value):
    if not isinstance(value, str): raise ValueError('Missing timestamp')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None: raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)

def decide(now, workflow, health, runs):
    now = instant(now)
    if workflow.get('state') != 'active':
        return 'DISABLED_WORKFLOW_REQUIRES_REVIEW'
    if health.get('schema_version') != 1 or health.get('status') not in ('OBSERVED', 'DEGRADED'):
        raise ValueError('Invalid source health; no dispatch')
    last = instant(health['last_attempt_at'])
    if last > now: raise ValueError('Future source clock; no dispatch')
    if not isinstance(runs, list): raise ValueError('Invalid workflow inventory')
    relevant = [r for r in runs if r.get('head_branch') == 'main' and r.get('event') in ('schedule', 'workflow_dispatch', 'push')]
    for r in relevant:
        if instant(r['created_at']) > now: raise ValueError('Future workflow clock')
    active = [r for r in relevant if r.get('status') != 'completed']
    if active:
        return 'STALLED_RUN_REQUIRES_REVIEW' if any((now-instant(r['created_at'])).total_seconds()>7200 for r in active) else 'RUN_ALREADY_ACTIVE'
    if last.date() == now.date():
        return 'ALREADY_COLLECTED_TODAY' if health['status'] == 'OBSERVED' else 'FAILED_COLLECTION_REQUIRES_REVIEW'
    # Preserve the 09:37 primary schedule; allow 30 minutes before catch-up.
    if (now.hour, now.minute) < (10, 7): return 'BEFORE_RECOVERY_WINDOW'
    if any(instant(r['created_at']).date() == now.date() for r in relevant):
        return 'ATTEMPT_EXISTS_BUT_STATE_MISSING_REQUIRES_REVIEW'
    return 'MISSING_DAILY_EXECUTION'

def api(path, *args):
    return subprocess.check_output(['gh', 'api', REPO+path, *args], text=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True)
    ap.add_argument('--dispatch', action='store_true')
    args=ap.parse_args()
    out=Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    report={'schema_version':1, 'dispatch_requested':False, 'collection_verified':False}
    try:
        repo=json.loads(api('')); workflow=json.loads(api(PATH))
        if repo.get('default_branch') != 'main' or repo.get('archived') or repo.get('disabled'):
            raise ValueError('Unexpected repository state; no dispatch')
        before=json.loads(api('/branches/main'))['commit']['sha']
        import base64
        state=json.loads(api('/contents/health.json?ref=monitoring-state'))
        health=json.loads(base64.b64decode(state['content']))
        runs=[]
        for page in range(1, 6):
            batch=json.loads(api(PATH+f'/runs?branch=main&per_page=100&page={page}'))['workflow_runs']
            runs.extend(batch)
            if len(batch)<100: break
        else: raise ValueError('Workflow history cap reached; no absence inference')
        now=datetime.now(timezone.utc).isoformat()
        result=decide(now, workflow, health, runs)
        report.update(checked_at=now, code_commit=before, workflow_state=workflow['state'],
                      health_blob=state['sha'], last_collection_attempt=health['last_attempt_at'],
                      successful_dates=health.get('successful_days'), decision=result,
                      recent_runs=[{k:r.get(k) for k in ('id','event','head_branch','status','conclusion','created_at')} for r in runs[:20]])
        if result=='MISSING_DAILY_EXECUTION' and args.dispatch:
            if json.loads(api('/branches/main'))['commit']['sha']!=before:
                raise ValueError('Main changed during guard; re-evaluate')
            # Re-read the canonical inventory to close the common concurrent-start race.
            latest=json.loads(api(PATH+'/runs?branch=main&per_page=100'))['workflow_runs']
            today=instant(now).date()
            if any(r.get('status')!='completed' or instant(r['created_at']).date()==today for r in latest if r.get('head_branch')=='main' and r.get('event') in ('schedule','workflow_dispatch','push')):
                report['decision']='CONCURRENT_ATTEMPT_FOUND_NO_DISPATCH'
            else:
                api(PATH+'/dispatches', '--method','POST','-f','ref=main')
                report['dispatch_requested']=True
                report['decision']='CATCH_UP_DISPATCH_REQUESTED_NOT_COMPLETED'
        out.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k!='recent_runs'}))
        return 1 if report['decision'].endswith('REQUIRES_REVIEW') else 0
    except Exception as exc:
        report.update(decision='GUARD_FAILED_NO_RESET', error_type=type(exc).__name__)
        out.write_text(json.dumps(report,indent=2)+'\n')
        raise
if __name__=='__main__': raise SystemExit(main())
