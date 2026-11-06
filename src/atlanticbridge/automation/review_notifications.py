"""Explicit, local-only historical review staging. No sender or scheduler exists."""
from contextlib import contextmanager
import argparse
import json
import os
from pathlib import Path
import sqlite3

from .models import canonical, digest, integer, source_id, timestamp, day, text, url, ORIGINS
from .store import _check_private_family, _reserve_private_destination, Conflict, verify_connection

MODE = 'LOCAL_REVIEW_PREVIEW_ONLY'
NOTICE = 'Historical local review observation; may now be superseded; not a verified business or lead event.'
FIXED = dict(mode=MODE, interpretation=NOTICE, production_enabled=False, public_alert=False,
             lead_eligible=False, delivery_enabled=False, delivered=False)
SCHEMA = '''
CREATE TABLE review_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO review_meta VALUES('schema_version','1'),('mode','LOCAL_REVIEW_PREVIEW_ONLY');
CREATE TABLE plans(plan_id TEXT PRIMARY KEY, config TEXT NOT NULL, sha TEXT NOT NULL);
CREATE TABLE passes(pass_id INTEGER PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans,
 at TEXT NOT NULL, start_seq INTEGER NOT NULL, end_seq INTEGER NOT NULL,
 anchor TEXT, prefix_sha TEXT NOT NULL, scanned INTEGER NOT NULL, staged INTEGER NOT NULL,
 has_more INTEGER NOT NULL, max_scan INTEGER NOT NULL);
CREATE TABLE packets(packet_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL REFERENCES plans,
 event_id TEXT NOT NULL, event_seq INTEGER NOT NULL, pass_id INTEGER NOT NULL REFERENCES passes,
 payload TEXT NOT NULL, sha TEXT NOT NULL, UNIQUE(plan_id,event_id), UNIQUE(plan_id,event_seq));
'''
for _table in ('plans', 'passes', 'packets', 'review_meta'):
    for _action in ('UPDATE', 'DELETE'):
        SCHEMA += f"CREATE TRIGGER {_table}_{_action} BEFORE {_action} ON {_table} BEGIN SELECT RAISE(ABORT,'append-only'); END;"


def hash_id(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid SHA-256 identifier')
    return value


def schema_objects(db):
    return {tuple(row) for row in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}


def expected_schema():
    db = sqlite3.connect(':memory:')
    try:
        db.executescript(SCHEMA)
        return schema_objects(db)
    finally:
        db.close()


EXPECTED_SCHEMA = expected_schema()



def utc(value):
    if not isinstance(value, str) or not value.endswith(('Z', '+00:00')):
        raise ValueError('Explicit UTC timestamp required')
    return timestamp(value)


@contextmanager
def snapshot(path, *, foundation=False):
    """Backup includes committed WAL pages. Validate and consume this same snapshot."""
    _check_private_family(str(path))
    source = sqlite3.connect(Path(path).absolute().as_uri() + '?mode=ro', uri=True)
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    try:
        source.backup(db)
        _check_private_family(str(path))
        if foundation:
            verify_connection(db)
        else:
            verify_journal(db)
        yield db
    finally:
        source.close()
        db.close()


def plan_config(plan_id, pins, since):
    source_id(plan_id)
    if not isinstance(pins, dict) or not 1 <= len(pins) <= 100:
        raise ValueError('Explicit nonempty source set required (maximum 100)')
    for key, value in pins.items():
        source_id(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
            raise ValueError('Invalid contract hash')
    return dict(plan_id=plan_id, sources=pins, since=utc(since), mode=MODE)


def prefix(db, seq):
    # Bind the entire consumed global history, including filtered events.
    import hashlib
    result = hashlib.sha256()
    for row in db.execute('SELECT rowid AS seq,* FROM evidence_events WHERE rowid<=? ORDER BY rowid', (seq,)):
        result.update(canonical(dict(row)).encode() + b'\n')
    return result.hexdigest()


def payload(db, event):
    version = db.execute('SELECT * FROM record_versions WHERE version_id=?', (event['to_version_id'],)).fetchone()
    contract = json.loads(db.execute('SELECT contract_json FROM contracts WHERE contract_id=?', (version['contract_id'],)).fetchone()[0])
    return dict(FIXED, source_id=event['source_id'], source_contract_id=version['contract_id'],
        record_id=event['record_id'], work_item_id=digest(['review-work',event['source_id'],event['record_id']]),
        from_version_id=event['from_version_id'], to_version_id=event['to_version_id'],
        event_id=event['event_id'], event_kind=event['kind'], imported_at=event['imported_at'],
        event_date=event['event_date'], published_date=event['published_date'], origin=version['origin'],
        coverage=contract['coverage'], attribution=contract['attribution'],
        license_name=contract['license_name'], license_url=contract['license_url'])


def validate_payload(p, config):
    fields = set(FIXED) | set('source_id source_contract_id record_id work_item_id from_version_id to_version_id event_id event_kind imported_at event_date published_date origin coverage attribution license_name license_url'.split())
    if not isinstance(p, dict) or set(p) != fields:
        raise ValueError('Invalid packet fields')
    source_id(p['source_id'])
    for key, value in FIXED.items():
        if type(p[key]) is not type(value) or p[key] != value:
            raise ValueError('Invalid fixed local-only semantics')
    if p['source_contract_id'] != config['sources'].get(p['source_id']):
        raise ValueError('Packet source contract mismatch')
    for key in ('source_contract_id', 'work_item_id', 'to_version_id', 'event_id'):
        if not isinstance(p[key], str) or len(p[key]) != 64 or any(c not in '0123456789abcdef' for c in p[key]):
            raise ValueError('Invalid identity')
    if p['from_version_id'] is not None and (not isinstance(p['from_version_id'],str) or len(p['from_version_id']) != 64 or any(c not in '0123456789abcdef' for c in p['from_version_id'])):
        raise ValueError('Invalid previous identity')
    text(p['record_id'], 'record ID', 512)
    if p['event_id'] != digest(['observed-version', p['to_version_id']]) or p['work_item_id'] != digest(['review-work',p['source_id'],p['record_id']]):
        raise ValueError('Non-deterministic identity')
    expected_kind = 'RECORD_CONTENT_CHANGED' if p['from_version_id'] else 'RECORD_FIRST_OBSERVED'
    if p['event_kind'] != expected_kind or p['origin'] not in ORIGINS:
        raise ValueError('Invalid observation kind/origin')
    if utc(p['imported_at']) != p['imported_at'] or p['imported_at'] < config['since']:
        raise ValueError('Invalid observation time')
    for key in ('event_date','published_date'): day(p[key])
    for key in ('coverage','attribution','license_name'): text(p[key], key, 4096)
    if url(p['license_url']) is None: raise ValueError('Missing declared license URL')


def verify_journal(db):
    if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('Journal SQLite integrity failed')
    try:
        if schema_objects(db) != EXPECTED_SCHEMA:
            raise ValueError('Unsupported or modified review journal schema')
        if dict(db.execute('SELECT key,value FROM review_meta')) != {'schema_version':'1','mode':MODE}:
            raise ValueError('Unsupported review journal')
        plans = {}
        for row in db.execute('SELECT * FROM plans'):
            c = json.loads(row['config'])
            if c != plan_config(c['plan_id'], c['sources'], c['since']) or c['plan_id'] != row['plan_id'] or digest(c) != row['sha'] or canonical(c) != row['config']:
                raise ValueError('Plan hash/config mismatch')
            plans[row['plan_id']] = c
        for plan, c in plans.items():
            seq, at, anchor, prefix_sha = 0, None, None, digest(None)
            for run in db.execute('SELECT * FROM passes WHERE plan_id=? ORDER BY pass_id', (plan,)):
                if utc(run['at']) != run['at'] or (at and run['at'] < at): raise ValueError('Nonmonotonic staging time')
                integer(run['pass_id'], 'pass ID', 1, 2**63-1)
                integer(run['start_seq'], 'start cursor', 0, 2**63-1)
                integer(run['end_seq'], 'end cursor', 0, 2**63-1)
                integer(run['staged'], 'staged count', 0, 1000)
                integer(run['max_scan'], 'max scan', 1, 1000)
                integer(run['scanned'], 'scanned', 0, run['max_scan'])
                if run['start_seq'] != seq or run['end_seq'] != seq + run['scanned'] or run['has_more'] not in (0,1) or (run['has_more'] and run['scanned'] != run['max_scan']):
                    raise ValueError('Inconsistent cursor/pass')
                hash_id(run['prefix_sha'])
                if run['anchor'] is not None: hash_id(run['anchor'])
                if bool(run['end_seq']) != bool(run['anchor']):
                    raise ValueError('Invalid cursor anchor')
                if at is not None and run['scanned'] == 0 and (run['anchor'] != anchor or run['prefix_sha'] != prefix_sha):
                    raise ValueError('Empty pass changed cursor anchor')
                if run['end_seq'] == 0:
                    import hashlib
                    if run['prefix_sha'] != hashlib.sha256().hexdigest():
                        raise ValueError('Invalid empty history digest')
                rows = db.execute('SELECT * FROM packets WHERE pass_id=?', (run['pass_id'],)).fetchall()
                if len(rows) != run['staged']: raise ValueError('Incorrect staged count')
                for row in rows:
                    integer(row['event_seq'], 'event sequence', 1, 2**63-1)
                    p = json.loads(row['payload']); validate_payload(p, c)
                    if row['event_seq'] == run['end_seq'] and row['event_id'] != run['anchor']:
                        raise ValueError('Packet/anchor mismatch')
                    if (row['plan_id'] != plan or row['event_id'] != p['event_id'] or
                        row['packet_id'] != digest([MODE,plan,row['event_id']]) or digest(p) != row['sha'] or canonical(p) != row['payload'] or
                        not seq < row['event_seq'] <= run['end_seq'] or p['imported_at'] > run['at']):
                        raise ValueError('Packet integrity mismatch')
                seq, at, anchor, prefix_sha = run['end_seq'], run['at'], run['anchor'], run['prefix_sha']
        return dict(integrity='ok', schema_version=1, mode=MODE,
                    packets=db.execute('SELECT COUNT(*) FROM packets').fetchone()[0])
    except (sqlite3.DatabaseError, KeyError, TypeError) as error:
        raise ValueError('Invalid review journal schema/content') from error


def stage_selection(journal, db, *, plan_id, at, max_scan):
    """Read-only stage preflight, shared with the locked staging operation."""
    at = utc(at); integer(max_scan, "max_scan", 1, 1000); source_id(plan_id)
    row = journal.execute('SELECT config FROM plans WHERE plan_id=?',(plan_id,)).fetchone()
    if not row: raise ValueError('Unknown plan')
    config = json.loads(row[0])
    for source, pin in config['sources'].items():
        current = db.execute('SELECT contract_id FROM sources WHERE source_id=?',(source,)).fetchone()
        if not current or current[0] != pin: raise Conflict('Source contract changed or disappeared')
    previous = journal.execute('SELECT * FROM passes WHERE plan_id=? ORDER BY pass_id DESC LIMIT 1',(plan_id,)).fetchone()
    seq = previous['end_seq'] if previous else 0
    if previous:
        anchor = db.execute('SELECT event_id FROM evidence_events WHERE rowid=?',(seq,)).fetchone()
        if (at < previous['at'] or (seq and (not anchor or anchor[0] != previous['anchor'])) or prefix(db,seq) != previous['prefix_sha']):
            raise Conflict('Older/changed source history or staging time; cursor cannot be reused')
    events = db.execute('SELECT rowid AS seq,* FROM evidence_events WHERE rowid>? ORDER BY rowid LIMIT ?', (seq,max_scan+1)).fetchall()
    more = len(events) > max_scan; events = events[:max_scan]
    if any(e['imported_at'] > at for e in events): raise Conflict('Source event is later than staging time')
    return config, previous, seq, more, events


class ReviewJournal:
    def __init__(self, path):
        self.path = str(path)
        _check_private_family(self.path)  # Opening is never implicit initialization.
        self.db = sqlite3.connect(Path(path).absolute().as_uri()+'?mode=rw', uri=True, isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        try:
            verify_journal(self.db)
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA synchronous=FULL')
        except BaseException:
            self.db.close(); raise

    @classmethod
    def initialize(cls, path):
        _reserve_private_destination(path)
        db = sqlite3.connect(path)
        try: db.executescript('BEGIN IMMEDIATE;' + SCHEMA + 'COMMIT;')
        finally: db.close()
        return cls(path)

    def __enter__(self): return self
    def __exit__(self, *args): self.db.close()

    @contextmanager
    def transaction(self):
        _check_private_family(self.path)
        self.db.execute('BEGIN IMMEDIATE')
        try:
            verify_journal(self.db)
            yield
            verify_journal(self.db)
            _check_private_family(self.path)
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK'); raise

    def register(self, foundation, *, plan_id, sources, since):
        if not isinstance(sources, (list,tuple)) or not 1 <= len(sources) <= 100 or len(set(sources)) != len(sources):
            raise ValueError('Explicit unique source IDs required')
        with snapshot(foundation, foundation=True) as db:
            pins = {}
            for source in sources:
                source_id(source)
                row = db.execute('SELECT contract_id FROM sources WHERE source_id=?',(source,)).fetchone()
                if row is None: raise ValueError('Unknown source')
                pins[source] = row[0]
            config = plan_config(plan_id, pins, since)
        with self.transaction():
            old = self.db.execute('SELECT config FROM plans WHERE plan_id=?',(plan_id,)).fetchone()
            if old:
                if old[0] != canonical(config): raise Conflict('Immutable plan differs; choose a new plan ID')
                return False
            self.db.execute('INSERT INTO plans VALUES(?,?,?)',(plan_id,canonical(config),digest(config)))
        return True

    def stage(self, foundation, *, plan_id, at, max_scan=100):
        at = utc(at); integer(max_scan,'max_scan',1,1000)
        with self.transaction(), snapshot(foundation, foundation=True) as db:
            config, previous, seq, more, events = stage_selection(self.db, db, plan_id=plan_id, at=at, max_scan=max_scan)
            end = events[-1]['seq'] if events else seq
            anchor = events[-1]['event_id'] if events else (previous['anchor'] if previous else None)
            selected = [e for e in events if e['source_id'] in config['sources'] and e['imported_at'] >= config['since']]
            run = self.db.execute('INSERT INTO passes(plan_id,at,start_seq,end_seq,anchor,prefix_sha,scanned,staged,has_more,max_scan) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (plan_id,at,seq,end,anchor,prefix(db,end),len(events),len(selected),int(more),max_scan)).lastrowid
            for event in selected:
                p = payload(db,event)
                self.db.execute('INSERT INTO packets VALUES(?,?,?,?,?,?,?)', (digest([MODE,plan_id,event['event_id']]),plan_id,event['event_id'],event['seq'],run,canonical(p),digest(p)))
        return dict(mode=MODE, scanned=len(events), staged=len(selected), cursor=end, has_more=more, delivered=0)

    def backup(self, destination):
        _reserve_private_destination(destination)
        target = sqlite3.connect(destination)
        try:
            _check_private_family(self.path)
            self.db.backup(target)
            target.row_factory = sqlite3.Row
            report = verify_journal(target)
            _check_private_family(str(destination))
            with open(destination,'rb') as handle: os.fsync(handle.fileno())
            return report
        finally: target.close()  # Failed artifacts deliberately retained.


def inspect(path, *, plan_id=None):
    with snapshot(path) as db:
        return [json.loads(r[0]) for r in db.execute('SELECT payload FROM packets WHERE (? IS NULL OR plan_id=?) ORDER BY pass_id,event_seq',(plan_id,plan_id))]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--journal', required=True)
    commands = parser.add_subparsers(dest='command',required=True)
    commands.add_parser('init'); commands.add_parser('verify')
    p = commands.add_parser('inspect'); p.add_argument('--plan-id')
    p = commands.add_parser('backup'); p.add_argument('--destination',required=True)
    p = commands.add_parser('register'); p.add_argument('--foundation',required=True); p.add_argument('--plan-id',required=True)
    p.add_argument('--source',action='append',required=True); p.add_argument('--since',required=True)
    p = commands.add_parser('stage'); p.add_argument('--foundation',required=True); p.add_argument('--plan-id',required=True)
    p.add_argument('--at',required=True); p.add_argument('--max-scan',type=int,default=100)
    args = parser.parse_args(argv)
    try:
        if args.command == 'inspect': result = inspect(args.journal,plan_id=args.plan_id)
        elif args.command == 'verify':
            with snapshot(args.journal) as db: result = verify_journal(db)
        elif args.command == 'init':
            with ReviewJournal.initialize(args.journal): result = dict(mode=MODE,initialized=True)
        else:
            with ReviewJournal(args.journal) as journal:
                if args.command == 'register': result = dict(registered=journal.register(args.foundation,plan_id=args.plan_id,sources=args.source,since=args.since),mode=MODE)
                elif args.command == 'stage': result = journal.stage(args.foundation,plan_id=args.plan_id,at=args.at,max_scan=args.max_scan)
                else: result = journal.backup(args.destination)
        print(canonical(result)); return 0
    except (ValueError, OSError, sqlite3.Error) as error:
        detail = 'Local database operation failed: ' + type(error).__name__ if isinstance(error, (OSError, sqlite3.Error)) else str(error)
        print(canonical(dict(error=detail, mode=MODE))); return 1


if __name__ == '__main__':
    raise SystemExit(main())
