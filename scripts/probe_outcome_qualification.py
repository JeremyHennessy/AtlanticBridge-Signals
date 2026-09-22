"""Collect primary documents, qualify discovered projects and exercise safe recovery."""
from __future__ import annotations
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from atlanticbridge.company_sources import Ledger, parse_article
from atlanticbridge.investment_discovery import parse_investment_cards, retained_review_records
from atlanticbridge.outcome_qualification import qualify
from probe_company_sources import Capture


def prove_recovery(ledger: Ledger, source: dict, records: list[dict], raw_sha: str) -> dict:
    """Fault injection operates on a disposable copy, never the retained source ledger."""
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / 'recovery.sqlite')
        clone = Ledger(path)
        ledger.db.backup(clone.db)
        before = '\n'.join(clone.db.iterdump())
        first = dict(clone.db.execute('SELECT id,first_seen FROM company_observations'))
        now = datetime.now(timezone.utc) + timedelta(seconds=1)
        try:
            try:
                clone.apply(source, records, now.isoformat(), raw_sha, complete=False)
            except ValueError:
                pass
            else:
                raise AssertionError('Incomplete snapshot was accepted')
            assert '\n'.join(clone.db.iterdump()) == before, 'Failed snapshot mutated retained evidence'
            assert clone.apply(source, [], now.isoformat(), raw_sha) == []
        finally:
            clone.close()
        clone = Ledger(path)
        try:
            events = clone.apply(source, records, (now + timedelta(seconds=1)).isoformat(), raw_sha)
            assert events == [], 'Restart/reappearance emitted old records as new'
            assert dict(clone.db.execute('SELECT id,first_seen FROM company_observations')) == first
        finally:
            clone.close()
    return {'source_id': source['id'], 'records': len(records), 'failed_snapshot_unchanged': True,
            'empty_window_restart_recovery_events': 0, 'first_observation_preserved': True,
            'test_scope': 'DISPOSABLE_LEDGER_COPY_NOT_PRODUCTION_OUTAGE'}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', default='reviews/commercial_validation/discovery-review-2026-09-22.json')
    ap.add_argument('--output', default='artifacts/outcome-qualification')
    ap.add_argument('--state')
    args = ap.parse_args()
    path = Path(args.manifest)
    manifest = json.loads(path.read_text())
    discovery_source = json.loads(Path('reviews/company_sources/investment-discovery-2026-09-22.json').read_text())['sources'][0]
    sources = [discovery_source] + manifest['sources']
    if not 1 <= len(sources) <= 20 or len({s['id'] for s in sources}) != len(sources):
        raise ValueError('Invalid bounded source manifest')
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    state = Path(args.state) if args.state else out / 'observations.sqlite'
    state.parent.mkdir(parents=True, exist_ok=True)
    capture = Capture(out / 'raw', {urlsplit(s['url']).hostname for s in sources})
    ledger = Ledger(str(state))
    report = {'schema_version': 1, 'manifest_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'sources': [], 'failures': [], 'recovery_tests': [], 'qualification': None}
    discovery, evidence = [], {}
    try:
        for source in sources:
            try:
                body, sha = capture.get(source['url'])
                rows = (parse_investment_cards if source['kind'] == 'investment_cards' else parse_article)(body, source)
                observed = datetime.now(timezone.utc).isoformat()
                events = ledger.apply(source, rows, observed, sha)
                assert not ledger.apply(source, rows, observed, sha), 'Replay was not idempotent'
                saved = retained_review_records(ledger, rows)
                report['sources'].append({'id': source['id'], 'records': len(rows),
                    'raw_sha256': sha, 'observed_at': observed, 'change_events': len(events), 'replay_events': 0})
                if source['kind'] == 'investment_cards':
                    discovery = saved
                else:
                    evidence[source['id']] = saved[0]
                report['recovery_tests'].append(prove_recovery(ledger, source, rows, sha))
                print(json.dumps(report['sources'][-1]), flush=True)
            except Exception as exc:
                failure = {'id': source['id'], 'status': 'UNVERIFIED', 'error': str(exc),
                           'failed_url': getattr(exc, 'url', None)}
                report['failures'].append(failure)
                print(json.dumps(failure), flush=True)
        if not report['failures']:
            try:
                result = qualify(discovery, manifest, evidence)
                report['qualification'] = result['summary']
                (out / 'reviewed-discovery.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
            except Exception as exc:
                report['failures'].append({'id': 'documentary-qualification', 'status': 'UNVERIFIED', 'error': str(exc)})
    finally:
        ledger.close()
        report['responses'] = capture.responses
        for response in capture.responses:
            if 'sha256' in response:
                raw = capture.directory / (response['sha256'] + '.bin')
                if hashlib.sha256(raw.read_bytes()).hexdigest() != response['sha256']:
                    report['failures'].append({'id': response['url'], 'error': 'Raw hash mismatch'})
        report['summary'] = {'requested_source_paths': len(sources), 'successful_source_paths': len(report['sources']),
            'source_records': sum(s['records'] for s in report['sources']), 'failures': len(report['failures']),
            'change_events': sum(s['change_events'] for s in report['sources']),
            'raw_responses_verified': sum('sha256' in r for r in capture.responses),
            'production_alerts_published': 0, 'predictive_validation_complete': False}
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        print(json.dumps(report['summary']), flush=True)
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
