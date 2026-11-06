"""Private company-level analyst persistence, separate from source evidence.

Consumes explicit local exports from ui/workspace.js. No HTTP, source ingestion,
identity mapping, notification, scheduling or public deployment is provided.
"""
from contextlib import contextmanager
from datetime import datetime
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3

from .models import canonical, day, integer, timestamp
from .store import Conflict, _check_private_family, _reserve_private_destination

FORMAT = 'atlanticbridge-analyst-workspace'
MODE = 'PRIVATE_COMPANY_ANALYST_STATE_ONLY'
MAX_BYTES = 2 * 1024 * 1024
MAX_ENTRIES = 500
STATUSES = {'new', 'researching', 'contacted', 'follow_up', 'closed'}
LIMITS = dict(company_name=1000, country=100, notes=4000, next_action=500,
              due_date=10, updated_at=40, source_url=2000, source_sha256=64,
              snapshot_observed_at=40, latest_public_date=10)
EDIT_FIELDS = {'status', 'notes', 'next_action', 'due_date'}
SCHEMA = '''
CREATE TABLE workspace_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO workspace_meta VALUES('schema_version','1'),('mode','PRIVATE_COMPANY_ANALYST_STATE_ONLY');
CREATE TABLE company_entries(company_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
 payload TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE analyst_history(seq INTEGER PRIMARY KEY, company_id TEXT NOT NULL,
 revision INTEGER NOT NULL, operation TEXT NOT NULL, actor TEXT NOT NULL,
 at TEXT NOT NULL, previous_sha TEXT, payload TEXT NOT NULL, sha TEXT NOT NULL,
 UNIQUE(company_id,revision));
'''
for _table in ('workspace_meta', 'analyst_history'):
    for _action in ('UPDATE', 'DELETE'):
        SCHEMA += f"CREATE TRIGGER {_table}_{_action} BEFORE {_action} ON {_table} BEGIN SELECT RAISE(ABORT,'append-only'); END;"


def _hash(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _objects(db):
    return {tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}


def _expected_schema():
    with sqlite3.connect(':memory:') as db:
        db.executescript(SCHEMA)
        return _objects(db)


EXPECTED_SCHEMA = _expected_schema()


def _object(pairs):
    value = {}
    for key, entry in pairs:
        if key in value:
            raise ValueError('Duplicate JSON key')
        value[key] = entry
    return value


def _loads(raw):
    return json.loads(raw, object_pairs_hook=_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))


def _text(value, limit):
    if type(value) is not str:
        raise ValueError('Expected text')
    # Match JavaScript string.length, including supplementary Unicode characters.
    # Reject unpaired surrogates instead of silently changing exported notes.
    if len(value.encode('utf-16-le')) // 2 > limit:
        raise ValueError('Text limit exceeded')
    return value


def _id(value):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Invalid exact company identity')
    return value


def _instant(value):
    _text(value, 40)
    # Existing exporter emits zoned ISO instants. More permissive browser date
    # strings require manual reconciliation; never normalize them silently.
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value):
        raise ValueError('Explicit ISO instant required')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Explicit timezone required')
    return value


def validate_entry(entry):
    if type(entry) is not dict or set(entry) != {'id', 'status', *LIMITS}:
        raise ValueError('Unknown or missing company workspace fields')
    _id(entry['id'])
    if type(entry['status']) is not str or entry['status'] not in STATUSES:
        raise ValueError('Invalid company workspace status')
    for key, limit in LIMITS.items():
        _text(entry[key], limit)
    for key in ('due_date', 'latest_public_date'):
        if entry[key]:
            day(entry[key])
    _instant(entry['updated_at'])
    if entry['snapshot_observed_at']:
        _instant(entry['snapshot_observed_at'])
    if entry['source_url'] and not re.match(r'^https?://', entry['source_url'], re.I):
        raise ValueError('Invalid declared source URL')
    if entry['source_sha256']:
        _id(entry['source_sha256'])
    return dict(entry)


def validate_backup(value):
    if isinstance(value, bytes):
        if len(value) > MAX_BYTES:
            raise ValueError('Backup exceeds byte limit')
        value = value.decode('utf-8')
    if type(value) is str:
        if len(value.encode('utf-8')) > MAX_BYTES:
            raise ValueError('Backup exceeds byte limit')
        value = _loads(value)
    if type(value) is not dict or set(value) not in (
            {'format', 'schema_version', 'entries'},
            {'format', 'schema_version', 'exported_at', 'entries'}):
        raise ValueError('Unsupported backup fields')
    if value['format'] != FORMAT or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported backup format')
    if 'exported_at' in value:
        _instant(value['exported_at'])
    if type(value['entries']) is not list or len(value['entries']) > MAX_ENTRIES:
        raise ValueError('Invalid entry count')
    entries = [validate_entry(entry) for entry in value['entries']]
    if len({entry['id'] for entry in entries}) != len(entries):
        raise ValueError('Duplicate company identity')
    if len(canonical(value).encode()) > MAX_BYTES:
        raise ValueError('Backup exceeds canonical byte limit')
    return entries


def _state(db):
    rows = [dict(row) for row in db.execute('SELECT * FROM company_entries ORDER BY company_id')]
    # Revision prevents ABA: editing and then restoring the same text changes the token.
    return _hash(rows)


def _export_fits(entries):
    # Reserve room for the longest supported timestamp so later exports remain
    # within the existing browser's 2 MiB backup/storage contract.
    value = dict(format=FORMAT, schema_version=1, exported_at='9999-12-31T23:59:59.999999+00:00', entries=entries)
    return len(canonical(value).encode()) <= MAX_BYTES


def _verify(db):
    if _objects(db) != EXPECTED_SCHEMA or db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('Invalid company workspace schema/integrity')
    if dict(db.execute('SELECT key,value FROM workspace_meta')) != {'schema_version':'1', 'mode':MODE}:
        raise ValueError('Invalid company workspace mode')
    current = {}
    previous_seq = 0
    for row in db.execute('SELECT * FROM analyst_history ORDER BY seq'):
        entry = validate_entry(_loads(row['payload']))
        if row['payload'] != canonical(entry) or row['sha'] != _hash(entry) or row['company_id'] != entry['id']:
            raise ValueError('Analyst history payload mismatch')
        integer(row['revision'], 'revision', 1, 2147483647)
        _text(row['actor'], 200)
        if not row['actor'].strip() or timestamp(row['at']) != row['at']:
            raise ValueError('Invalid analyst audit metadata')
        if row['seq'] != previous_seq + 1:
            raise ValueError('Analyst history sequence gap')
        previous_seq = row['seq']
        prior = current.get(entry['id'])
        if prior is None:
            if row['operation'] != 'IMPORT' or row['revision'] != 1 or row['previous_sha'] is not None:
                raise ValueError('Missing company import history')
        else:
            if (row['operation'] != 'SAVE' or row['revision'] != prior['revision'] + 1 or
                    row['previous_sha'] != prior['sha'] or row['at'] < prior['at']):
                raise ValueError('Invalid analyst revision chain')
            before = _loads(prior['payload'])
            immutable = set(entry) - EDIT_FIELDS - {'updated_at'}
            if any(entry[key] != before[key] for key in immutable) or entry['updated_at'] != row['at']:
                raise ValueError('Save changed imported company metadata')
        current[entry['id']] = dict(row)
    entries = [dict(row) for row in db.execute('SELECT * FROM company_entries ORDER BY company_id')]
    if len(entries) != len(current) or len(entries) > MAX_ENTRIES:
        raise ValueError('Company materialized state count mismatch')
    for entry in entries:
        prior = current.get(entry['company_id'])
        if prior is None or any(entry[key] != prior[key] for key in ('company_id', 'revision', 'payload', 'sha')):
            raise ValueError('Company materialized state mismatch')
    if not _export_fits([_loads(row['payload']) for row in entries]):
        raise ValueError('Company workspace exceeds reversible browser export limit')
    return {'mode':MODE, 'entries':len(entries), 'history':previous_seq, 'state_token':_state(db),
            'evidence_verified':False, 'identity_mapping_performed':False, 'delivery_enabled':False}


@contextmanager
def snapshot(path):
    path = str(Path(path).absolute())
    _check_private_family(path)
    source = sqlite3.connect(Path(path).as_uri() + '?mode=ro', uri=True)
    target = sqlite3.connect(':memory:')
    target.row_factory = sqlite3.Row
    try:
        source.backup(target)
        _check_private_family(path)
        _verify(target)
        yield target
    finally:
        source.close()
        target.close()


def initialize(path):
    """Explicit creation only. Never overwrite an existing database family."""
    path = str(Path(path).absolute())
    _reserve_private_destination(path)
    db = sqlite3.connect(str(path), isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('BEGIN IMMEDIATE;' + SCHEMA + 'COMMIT;')
        _check_private_family(str(path))
        return _verify(db)
    finally:
        db.close()


def _plan(db, entries):
    current = {row['company_id']:row['payload'] for row in db.execute('SELECT * FROM company_entries')}
    new = [entry for entry in entries if entry['id'] not in current]
    conflicts = [entry['id'] for entry in entries if entry['id'] in current and canonical(entry) != current[entry['id']]]
    combined = [_loads(value) for value in current.values()] + new
    return {'state_token':_state(db), 'backup_token':_hash(sorted(entries, key=lambda e:e['id'])),
            'incoming':len(entries), 'new':len(new), 'unchanged':len(entries)-len(new)-len(conflicts),
            'conflicting_company_ids':sorted(conflicts),
            'capacity_exceeded':len(combined)>MAX_ENTRIES or not _export_fits(combined),
            'mode':MODE, 'evidence_verified':False, 'identity_mapping_performed':False}


def plan_import(path, backup):
    entries = validate_backup(backup)
    with snapshot(path) as db:
        return _plan(db, entries)


@contextmanager
def _write(path):
    path = str(Path(path).absolute())
    _check_private_family(path)
    db = sqlite3.connect(Path(path).as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA synchronous=FULL')
        db.execute('BEGIN IMMEDIATE')
        _verify(db)
        yield db
        _verify(db)
        _check_private_family(path)
        db.commit()
    except BaseException:
        if db.in_transaction:
            db.rollback()
        raise
    finally:
        db.close()


def _audit(db, entry, revision, operation, actor, at, previous_sha=None):
    payload = canonical(entry)
    sha = _hash(entry)
    db.execute('INSERT INTO analyst_history(company_id,revision,operation,actor,at,previous_sha,payload,sha) VALUES(?,?,?,?,?,?,?,?)',
               (entry['id'], revision, operation, actor, at, previous_sha, payload, sha))
    db.execute('INSERT INTO company_entries VALUES(?,?,?,?) ON CONFLICT(company_id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload,sha=excluded.sha',
               (entry['id'], revision, payload, sha))


def _actor(actor):
    _text(actor, 200)
    if not actor.strip():
        raise ValueError('Audit actor required')
    return actor


def import_backup(path, backup, *, expected_state, expected_backup, actor, at):
    """All-or-nothing import. Conflicting identities are never overwritten."""
    entries = validate_backup(backup)
    _id(expected_state); _id(expected_backup); _actor(actor)
    at = timestamp(at)
    with _write(path) as db:
        plan = _plan(db, entries)
        if expected_state != plan['state_token'] or expected_backup != plan['backup_token']:
            raise Conflict('Workspace or selected backup changed; plan again')
        if plan['conflicting_company_ids'] or plan['capacity_exceeded']:
            raise Conflict('Import has conflicting company identities or exceeds capacity')
        existing = {row[0] for row in db.execute('SELECT company_id FROM company_entries')}
        for entry in entries:
            if entry['id'] not in existing:
                _audit(db, entry, 1, 'IMPORT', actor, at)
        return {**plan, 'added':plan['new'], 'state_token':_state(db)}


def entries(path):
    with snapshot(path) as db:
        return [{'entry':_loads(row['payload']), 'revision':row['revision']}
                for row in db.execute('SELECT * FROM company_entries ORDER BY company_id')]


def save(path, company_id, *, expected_revision, fields, actor, at):
    """Future UI storage boundary: analyst fields only, exact company namespace."""
    _id(company_id); integer(expected_revision, 'revision', 1, 2147483646); _actor(actor)
    if type(fields) is not dict or set(fields) != EDIT_FIELDS:
        raise ValueError('Only exact analyst edit fields may be saved')
    at = timestamp(at)
    with _write(path) as db:
        row = db.execute('SELECT * FROM company_entries WHERE company_id=?', (company_id,)).fetchone()
        if row is None or row['revision'] != expected_revision:
            raise Conflict('Company missing or revision changed')
        entry = validate_entry({**_loads(row['payload']), **fields, 'updated_at':at})
        _audit(db, entry, expected_revision+1, 'SAVE', actor, at, row['sha'])
        return {'entry':entry, 'revision':expected_revision+1}


def export_backup(path, *, at):
    result = dict(format=FORMAT, schema_version=1, exported_at=timestamp(at),
                  entries=[item['entry'] for item in entries(path)])
    validate_backup(result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('init'); commands.add_parser('verify')
    plan = commands.add_parser('plan-import'); plan.add_argument('--backup', required=True, type=Path)
    apply = commands.add_parser('import-backup'); apply.add_argument('--backup', required=True, type=Path)
    apply.add_argument('--expected-state', required=True); apply.add_argument('--expected-backup', required=True)
    apply.add_argument('--actor', required=True)
    export = commands.add_parser('export'); export.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    from .scheduler import utc_now
    try:
        if args.command == 'init':
            result = initialize(args.db)
        elif args.command in {'plan-import', 'import-backup'}:
            with args.backup.open('rb') as source:
                raw = source.read(MAX_BYTES+1)
            if args.command == 'plan-import':
                result = plan_import(args.db, raw)
            else:
                result = import_backup(args.db, raw, expected_state=args.expected_state,
                    expected_backup=args.expected_backup, actor=args.actor, at=utc_now())
        elif args.command == 'export':
            raw = canonical(export_backup(args.db, at=utc_now())).encode()
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0), 0o600)
            with os.fdopen(fd, 'wb') as target:
                target.write(raw); target.flush(); os.fsync(target.fileno())
            result = {'exported':True, 'private':True, 'bytes':len(raw)}
        else:
            with snapshot(args.db) as db:
                result = _verify(db)
        print(canonical(result))
        return 0
    except Exception:
        # Never print imported notes, filesystem paths or raw exception messages.
        print(canonical({'status':'REJECTED_OR_UNCERTAIN', 'mode':MODE,
                         'message':'Verify the existing workspace and selected backup before retrying.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
