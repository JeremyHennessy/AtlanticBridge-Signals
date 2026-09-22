"""One incremental monitoring run; never replace production state with a quiet reset."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from atlanticbridge.company_sources import Ledger, url
from atlanticbridge.monitoring_checkpoint import checkpoint, restore, save, health
from probe_company_sources import Capture, collect


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
    if set(s['id'] for s in sources) != known:
        raise ValueError('Manifest/state source set changed; explicit reviewed migration required')
    capture = Capture(out / 'raw', {urlsplit(url(s['url'])).hostname for s in sources} |
                      {'api.ashbyhq.com', 'boards-api.greenhouse.io'})
    results = []
    try:
        for source in sources:
            try:
                rows, sha, coverage = collect(source, capture)
                now = datetime.now(timezone.utc).isoformat()
                events = ledger.apply(source, rows, now, sha)
                if ledger.apply(source, rows, now, sha):
                    raise AssertionError('Source replay emitted events')
                result = {'id': source['id'], 'source_url': source['url'], 'status': 'OBSERVED',
                          'records': len(rows), 'change_events': len(events), 'raw_sha256': sha,
                          'canada_location_candidates': sum(r['canada_relevance'] == 'CANDIDATE_REQUIRES_REVIEW' for r in rows),
                          'scope_held_candidates': sum(r['canada_relevance'] == 'CANDIDATE_REQUIRES_REVIEW' and bool(r['scope_exclusion']) for r in rows),
                          'coverage': coverage['coverage']}
            except Exception as exc:
                # The accepted Ledger commits sources atomically; failures retain last success.
                result = {'id': source['id'], 'source_url': source['url'], 'status': 'UNVERIFIED_SOURCE_FAILURE',
                          'records': None, 'change_events': None, 'error_type': type(exc).__name__}
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
