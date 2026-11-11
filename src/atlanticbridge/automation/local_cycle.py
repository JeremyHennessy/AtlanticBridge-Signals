"""One explicit bounded local import/review cycle; no scheduler or delivery.

Existing foundation runs and journal passes are the durable recovery authority.
There is no cross-database transaction or persistent coordinator state.
"""
import argparse
from pathlib import Path

from .models import canonical, integer, source_id
from .review_notifications import ReviewJournal, snapshot, stage_selection, utc
from .scheduler import OfflineScheduler, utc_now
from .workbench import ExistingStore

MODE = 'LOCAL_CYCLE_ONLY_NO_DELIVERY'


class IsolatedScheduler(OfflineScheduler):
    """A source claim failure must not prevent other due sources from running."""
    def run_one(self, source):
        try:
            result = super().run_one(source)
            result.setdefault('source_id', source)
            return result
        except Exception:
            # A failure can occur after a commit. Never assert rollback or mark a
            # run failed here: its persisted lease/run is the recovery authority.
            return dict(source_id=source, status='UNKNOWN', error_code='SOURCE_OPERATION_UNCERTAIN')


def readback(foundation, journal, plan_id):
    """Validate committed state independently; counts contain no private paths."""
    with snapshot(foundation, foundation=True) as db:
        result = {key: db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                  for key, table in [('runs', 'runs'), ('work_items', 'work_items'),
                                     ('evidence_events', 'evidence_events')]}
        result['running_runs'] = db.execute("SELECT COUNT(*) FROM runs WHERE outcome='RUNNING'").fetchone()[0]
    with snapshot(journal) as db:
        result['review_packets'] = db.execute('SELECT COUNT(*) FROM packets WHERE plan_id=?', (plan_id,)).fetchone()[0]
        row = db.execute('SELECT pass_id,end_seq,has_more FROM passes WHERE plan_id=? ORDER BY pass_id DESC LIMIT 1', (plan_id,)).fetchone()
        result['latest_review_pass'] = dict(row) if row else None
    return result


def run_cycle(foundation, journal, *, plan_id, max_jobs=100, max_scan=100, clock=utc_now):
    """Import READY due sources pinned by one existing review plan, then stage it.

    Bounds are per invocation, not a hard wall-clock deadline: integrity and
    history-prefix verification still inspect existing history. Concurrent
    writers are supported by the underlying per-source leases and transactions,
    not by a global cycle lock. Preflight is advisory and repeated by each write.
    """
    report = dict(mode=MODE, production_enabled=False, delivery_enabled=False,
                  lead_eligible=False, delivered=0, status='REJECTED', phase='PREFLIGHT',
                  imports=[], staging=None, readback=None)
    try:
        source_id(plan_id)
        integer(max_jobs, 'max_jobs', 1, 1000)
        integer(max_scan, 'max_scan', 1, 1000)
        at = utc(clock())
        # Never initialize a missing file. Reject malformed history, unknown or
        # mismatched plans, old cursors and backward timestamps before imports.
        if Path(foundation).resolve() == Path(journal).resolve():
            raise ValueError('Distinct databases required')
        with snapshot(foundation, foundation=True) as db, snapshot(journal) as review:
            config, *_ = stage_selection(review, db, plan_id=plan_id, at=at, max_scan=max_scan)
            latest = db.execute('SELECT MAX(occurred_at) FROM audit_log').fetchone()[0]
            last_run = db.execute('SELECT MAX(started_at) FROM runs').fetchone()[0]
            finished = db.execute('SELECT MAX(finished_at) FROM runs').fetchone()[0]
            if any(t and t > at for t in (latest, last_run, finished)):
                raise ValueError('Cycle clock predates durable activity')
    except Exception:
        report['error_code'] = 'PREFLIGHT_REJECTED'
        return report

    report.update(status='PARTIAL', phase='IMPORTS', plan_id=plan_id,
                  max_jobs=max_jobs, max_scan=max_scan)
    try:
        with ExistingStore(foundation) as store:
            report['imports'] = IsolatedScheduler(store, clock=clock).run_due(max_jobs=max_jobs, source_ids=sorted(config['sources']))
        report['phase'] = 'STAGING'
        with ReviewJournal(journal) as review:
            report['staging'] = review.stage(foundation, plan_id=plan_id, at=utc(clock()), max_scan=max_scan)
        report['phase'] = 'READBACK'
        report['readback'] = readback(foundation, journal, plan_id)
        report['phase'] = 'FINISHED'
        if any(r['status'] in {'FAILED', 'LEASE_LOST', 'UNKNOWN'} for r in report['imports']):
            report['error_code'] = 'SOURCE_FAILURES_OR_UNCERTAIN'
        else:
            report['status'] = 'BOUNDED_PASS_COMPLETE'
    except Exception:
        report['error_code'] = 'PHASE_FAILED_OR_UNCERTAIN'
        # Earlier commits remain. The failing operation itself may have committed.
        # Report only validated independent readback, never exception text/paths.
        try:
            report['readback'] = readback(foundation, journal, plan_id)
        except Exception:
            report['readback'] = None
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--foundation', required=True)
    parser.add_argument('--journal', required=True)
    parser.add_argument('--plan-id', required=True)
    parser.add_argument('--max-jobs', type=int, default=100)
    parser.add_argument('--max-scan', type=int, default=100)
    args = parser.parse_args(argv)
    report = run_cycle(args.foundation, args.journal, plan_id=args.plan_id,
                       max_jobs=args.max_jobs, max_scan=args.max_scan)
    print(canonical(report))
    return 0 if report['status'] == 'BOUNDED_PASS_COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
