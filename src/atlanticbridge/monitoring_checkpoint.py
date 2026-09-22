"""Portable monitoring state using the accepted Ledger, with no public source bodies.

Persistent fingerprints and clocks support operational change detection. Full
raw documents stay in Actions artifacts (90-day retention); this
checkpoint alone is deliberately ineligible as a historical backtest snapshot.
"""
from __future__ import annotations
import json
from pathlib import Path
from .company_sources import Ledger, digest, instant

COLUMNS = {
    'company_source_state': ('id', 'contract', 'last_success'),
    'company_observations': ('id', 'source_id', 'first_seen', 'last_seen', 'fingerprint', 'payload'),
    'company_observation_events': ('id', 'source_id', 'observed_at', 'kind', 'payload'),
}
# No company/job description, title, contact details, analyst notes or article text
# is published in durable state. Record URLs and source-local IDs are public facts.
FACTS = {'id', 'source_id', 'source_record_id', 'source_url', 'source_publication_date',
         'publication_precision', 'publication_clock', 'source_updated_at',
         'first_observed_at', 'last_observed_at', 'raw_sha256',
         'canada_relevance', 'scope_exclusion', 'backtest_eligible', 'public_alert_allowed'}


def _facts(payload: str, event: bool) -> str:
    data = json.loads(payload)
    if event:
        data = {k: data[k] for k in ('id', 'kind', 'observed_at', 'public_alert_allowed', 'review_required')}
        original = json.loads(payload)
        data['record'] = {k: v for k, v in original['record'].items() if k in FACTS}
    else:
        data = {k: v for k, v in data.items() if k in FACTS}
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def checkpoint(ledger: Ledger, *, runs: list[dict] | None = None) -> dict:
    tables = {}
    for table, columns in COLUMNS.items():
        rows = []
        for record in ledger.db.execute(f"SELECT {','.join(columns)} FROM {table} ORDER BY id"):
            row = dict(zip(columns, record))
            if 'payload' in row:
                row['payload'] = _facts(row['payload'], table == 'company_observation_events')
            rows.append(row)
        tables[table] = rows
    content = {'schema_version': 1, 'tables': tables, 'runs': list(runs or []),
               'raw_retention_days': 90, 'historical_backtest_eligible': False}
    return dict(content, checksum=digest(content))


def validate(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {'schema_version', 'tables', 'runs',
            'raw_retention_days', 'historical_backtest_eligible', 'checksum'}:
        raise ValueError('Unsupported monitoring checkpoint')
    content = {k: v for k, v in value.items() if k != 'checksum'}
    if value['schema_version'] != 1 or value['checksum'] != digest(content):
        raise ValueError('Checkpoint checksum/schema mismatch')
    if value['historical_backtest_eligible'] is not False or value['raw_retention_days'] != 90:
        raise ValueError('Unapproved evidence-retention contract')
    if set(value['tables']) != set(COLUMNS) or not isinstance(value['runs'], list):
        raise ValueError('Invalid monitoring tables/runs')
    source_ids = set()
    identities = set()
    for table, columns in COLUMNS.items():
        records = value['tables'][table]
        if not isinstance(records, list) or len(records) > 100000:
            raise ValueError('Oversized state')
        ids = set()
        for row in records:
            if set(row) != set(columns) or not all(isinstance(v, str) for v in row.values()):
                raise ValueError('Invalid checkpoint row')
            if not row['id'] or row['id'] in ids:
                raise ValueError('Duplicate/missing checkpoint identity')
            ids.add(row['id'])
            if table == 'company_source_state':
                source_ids.add(row['id']); instant(row['last_success'])
            else:
                if row['source_id'] not in source_ids:
                    raise ValueError('Orphan source reference')
                payload = json.loads(row['payload'])
                facts = payload['record'] if table == 'company_observation_events' else payload
                if set(facts) - FACTS or facts.get('public_alert_allowed') is not False or facts.get('backtest_eligible') is not False:
                    raise ValueError('Public state must contain only unqualified metadata')
                if facts.get('source_id') != row['source_id']:
                    raise ValueError('Mismatched payload source')
                if table == 'company_observations':
                    if facts.get('id') != row['id'] or instant(row['first_seen']) > instant(row['last_seen']):
                        raise ValueError('Invalid observation identity/clock')
                    identities.add(row['id'])
                else:
                    if facts.get('id') not in identities or payload.get('public_alert_allowed') is not False or payload.get('review_required') is not True:
                        raise ValueError('Invalid review-only event')
                    instant(row['observed_at'])
    run_ids = set()
    for run in value['runs']:
        if not isinstance(run, dict) or not run.get('id') or run['id'] in run_ids:
            raise ValueError('Duplicate/missing run identity')
        run_ids.add(run['id']); instant(run['finished_at'])
        if not isinstance(run.get('sources'), list):
            raise ValueError('Missing per-source health')
    return value


def restore(ledger: Ledger, value: dict) -> None:
    validate(value)  # Validate the entire document before changing even one table.
    if any(ledger.db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in COLUMNS):
        raise ValueError('Restore requires an empty ledger; existing state is never overwritten')
    with ledger.db:
        for table, columns in COLUMNS.items():
            ledger.db.executemany(f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                                 [tuple(r[c] for c in columns) for r in value['tables'][table]])


def save(path: Path, value: dict) -> None:
    validate(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n')
    temporary.replace(path)


def health(value: dict) -> dict:
    validate(value)
    runs = value['runs']
    states = {r['id']: r for r in value['tables']['company_source_state']}
    latest = runs[-1] if runs else None
    good_days = sorted({r['finished_at'][:10] for r in runs if r['sources'] and all(s['status'] == 'OBSERVED' for s in r['sources'])})
    # A run repeated 14 times in one day never becomes 14 days of reliability.
    streak = 0
    if latest:
        from datetime import date, timedelta
        day = date.fromisoformat(latest['finished_at'][:10])
        good = set(good_days)
        while day.isoformat() in good:
            streak += 1; day -= timedelta(days=1)
    return {'schema_version': 1, 'status': ('OBSERVED' if all(s['status'] == 'OBSERVED' for s in latest['sources']) else 'DEGRADED') if latest else 'BASELINE_ONLY',
            'last_attempt_at': latest['finished_at'] if latest else None,
            'run_id': latest['id'] if latest else None,
            'sources': [dict(s, last_success_at=states.get(s['id'], {}).get('last_success')) for s in latest['sources']] if latest else [],
            'successful_days': len(good_days), 'consecutive_successful_days': streak,
            'operational_target_days': 14, 'operational_target_met': streak >= 14 and bool(latest) and all(s['status'] == 'OBSERVED' for s in latest['sources']),
            'retained_observation_count': len(value['tables']['company_observations']),
            'review_only_change_count': len(value['tables']['company_observation_events']),
            'public_alert_count': 0, 'predictive_validation_complete': False,
            'retention': 'Metadata and fingerprints retained in Git; raw responses in 90-day Actions artifacts. Not a twelve-month raw archive.'}
