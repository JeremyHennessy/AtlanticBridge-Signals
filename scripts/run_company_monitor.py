"""One incremental monitoring run; never replace production state with a quiet reset."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from atlanticbridge.company_sources import Ledger, VERSION, digest, url
from atlanticbridge.monitoring_checkpoint import checkpoint, restore, save, health
from probe_company_sources import Capture, collect


def reviewed_additions(manifest: dict, known: set[str]) -> set[str]:
    sources = manifest.get('sources')
    if not isinstance(sources, list) or not sources:
        raise ValueError('Missing monitoring source manifest')
    ids = [s.get('id') for s in sources]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('Invalid or duplicate monitoring source id')
    current = set(ids)
    removed = known - current
    if removed:
        raise ValueError('Source removal requires an explicit reviewed migration: ' + ', '.join(sorted(removed)))
    added = current - known
    if not added:
        return set()
    enrollment = manifest.get('enrollment')
    if not isinstance(enrollment, dict) or enrollment.get('policy') != 'ADDITIVE_BASELINE_NO_EVENTS':
        raise ValueError('New monitoring sources require reviewed additive-baseline approval')
    approvals = enrollment.get('approved_additions')
    if not isinstance(approvals, list) or len(approvals) != len(added):
        raise ValueError('Enrollment approval count does not match new source set')
    by_id = {s['id']: s for s in sources}
    approval_ids = set()
    for approval in approvals:
        if not isinstance(approval, dict) or set(approval) != {'id','proof_artifact_id','proof_archive_sha256','source_contract_sha256'}:
            raise ValueError('Invalid enrollment approval schema')
        sid = approval['id']
        if sid in approval_ids or sid not in added:
            raise ValueError('Enrollment approval is duplicate or not a new source')
        approval_ids.add(sid)
        if type(approval['proof_artifact_id']) is not int or approval['proof_artifact_id'] <= 0:
            raise ValueError('Enrollment proof artifact id is invalid')
        for key in ('proof_archive_sha256','source_contract_sha256'):
            if not isinstance(approval[key], str) or not re.fullmatch(r'[a-f0-9]{64}', approval[key]):
                raise ValueError('Enrollment proof hash is invalid')
        contract = digest({'parser_version': VERSION, 'source': by_id[sid]})
        if contract != approval['source_contract_sha256']:
            raise ValueError('Approved source contract does not match manifest: ' + sid)
    if approval_ids != added:
        raise ValueError('Enrollment approvals do not exactly cover new sources')
    return added


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--state-dir', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--run-id', required=True)
    args = ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', args.run_id):
        raise ValueError('Invalid run identity')
    state_dir, out = Path(args.state_dir), Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    path = state_dir / 'checkpoint.json'
    # Missing/corrupt state is an operational failure, never a fresh baseline.
    previous = json.loads(path.read_text())
    ledger = Ledger(':memory:')
    restore(ledger, previous)
    if args.run_id in {r['id'] for r in previous['runs']}:
        raise ValueError('This run identity is already committed')
    manifest = json.loads(Path('reviews/company_sources/pilot-2026-09-22.json').read_text())
    sources = manifest['sources']
    known = {r['id'] for r in previous['tables']['company_source_state']}
    additions = reviewed_additions(manifest, known)
    capture = Capture(out / 'raw', {urlsplit(url(s['url'])).hostname for s in sources} |
                      {'api.ashbyhq.com', 'boards-api.greenhouse.io'})
    results = []
    pending_additions = {}
    try:
        # Every new source must fetch and parse before any enrollment state is written.
        # This makes cohort expansion all-or-nothing while preserving the old checkpoint.
        enrollment_failures = []
        for source in [s for s in sources if s['id'] in additions]:
            try:
                pending_additions[source['id']] = collect(source, capture)
            except Exception as exc:
                enrollment_failures.append({'id': source['id'], 'source_url': source['url'],
                                            'status': 'UNVERIFIED_ENROLLMENT_SOURCE_FAILURE',
                                            'error_type': type(exc).__name__})
        if enrollment_failures:
            (out / 'enrollment-failure.json').write_text(json.dumps({'schema_version': 1,
                'policy': 'NO_STATE_CHANGE_ON_ENROLLMENT_FAILURE', 'failures': enrollment_failures}, indent=2) + '\n')
            raise ValueError('Enrollment preflight failed; no new source state was written')
        if additions:
            # Exercise every new contract against a disposable restoration of the
            # exact checkpoint before mutating the production ledger.
            trial = Ledger(':memory:')
            try:
                restore(trial, previous)
                trial_observed = datetime.now(timezone.utc).isoformat()
                for source in [s for s in sources if s['id'] in additions]:
                    rows, sha, _ = pending_additions[source['id']]
                    if trial.apply(source, rows, trial_observed, sha):
                        raise AssertionError('Enrollment trial emitted review events')
            finally:
                trial.close()
        for source in sources:
            try:
                rows, sha, coverage = pending_additions.get(source['id']) or collect(source, capture)
                now = datetime.now(timezone.utc).isoformat()
                events = ledger.apply(source, rows, now, sha)
                if source['id'] in additions and events:
                    raise AssertionError('New source baseline emitted review events')
                if ledger.apply(source, rows, now, sha):
                    raise AssertionError('Source replay emitted events')
                result = {'id': source['id'], 'source_url': source['url'], 'status': 'OBSERVED',
                          'records': len(rows), 'change_events': len(events), 'raw_sha256': sha,
                          'enrollment_baseline': source['id'] in additions,
                          'canada_location_candidates': sum(r['canada_relevance'] == 'CANDIDATE_REQUIRES_REVIEW' for r in rows),
                          'scope_held_candidates': sum(r['canada_relevance'] == 'CANDIDATE_REQUIRES_REVIEW' and bool(r['scope_exclusion']) for r in rows),
                          'coverage': coverage['coverage']}
            except Exception as exc:
                # The accepted Ledger commits sources atomically; failures retain last success.
                result = {'id': source['id'], 'source_url': source['url'], 'status': 'UNVERIFIED_SOURCE_FAILURE',
                          'records': None, 'change_events': None, 'enrollment_baseline': source['id'] in additions,
                          'error_type': type(exc).__name__}
            results.append(result)
            print(json.dumps(result), flush=True)
        import hashlib
        for response in capture.responses:
            if 'sha256' in response:
                if hashlib.sha256((capture.directory / (response['sha256'] + '.bin')).read_bytes()).hexdigest() != response['sha256']:
                    raise ValueError('Raw response hash mismatch; no checkpoint promotion')
        run = {'id': args.run_id, 'finished_at': datetime.now(timezone.utc).isoformat(), 'sources': results}
        updated = checkpoint(ledger, runs=previous['runs'] + [run])
        save(path, updated)
        public = health(updated)
        (state_dir / 'health.json').write_text(json.dumps(public, indent=2) + '\n')
        (state_dir / 'runs').mkdir(exist_ok=True)
        (state_dir / 'runs' / (args.run_id + '.json')).write_text(json.dumps(run, indent=2) + '\n')
        (out / 'report.json').write_text(json.dumps(dict(public, responses=capture.responses), indent=2) + '\n')
        return 1 if any(r['status'] != 'OBSERVED' for r in results) else 0
    finally:
        ledger.close()


if __name__ == '__main__':
    raise SystemExit(main())
