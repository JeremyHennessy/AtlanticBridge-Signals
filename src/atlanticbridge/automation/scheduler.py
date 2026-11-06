"""An explicitly invoked offline tick. No OS schedule, external fetch or delivery."""
from __future__ import annotations
from datetime import datetime, timezone
import os
import stat

from .models import decode_batch, integer, timestamp, source_id
from .store import Conflict


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class OfflineScheduler:
    """Process bounded local files independently, with persisted per-source health.

    Leases fence stale completion and recover abandoned work. They are not a hard
    CPU kill mechanism. A future network worker must implement its own hard I/O
    deadline and run each source independently; this class never calls one.
    """
    def __init__(self, store, *, clock=utc_now):
        self.store = store
        self.clock = clock

    def _fail(self, run_id, code, transient=False):
        try:
            self.store.fail(run_id, at=self.clock(), code=code, transient=transient)
        except Conflict:
            # A completion past its lease cannot mutate accepted evidence.
            # claim() on the next tick accounts for the expired lease.
            return {"run_id": run_id, "status": "LEASE_LOST"}
        return {"run_id": run_id, "status": "FAILED", "error_code": code}

    def run_one(self, source):
        now = timestamp(self.clock())
        previous = self.store.db.execute("SELECT lease_token FROM sources WHERE source_id=?", (source,)).fetchone()
        run_id = self.store.claim(source, at=now)
        if not run_id:
            if previous and previous["lease_token"]:
                old = self.store.db.execute("SELECT outcome,finished_at FROM runs WHERE run_id=?", (previous["lease_token"],)).fetchone()
                if old and old["outcome"] == "LEASE_EXPIRED" and old["finished_at"] == now:
                    return {"source_id": source, "run_id": previous["lease_token"], "status": "FAILED", "error_code": "LEASE_EXPIRED"}
            return {"source_id": source, "status": "NOT_CLAIMED"}
        contract = self.store.contract(source)
        path = self.store.db.execute("SELECT input_path FROM sources WHERE source_id=?", (source,)).fetchone()[0]
        if not path:
            return self._fail(run_id, "LOCAL_INPUT_UNAVAILABLE", True)
        try:
            # Refuse FIFOs/devices and final-component symlinks. No unbounded wait
            # for input or unbounded allocation from a growing local file.
            flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags)
            with os.fdopen(fd, "rb") as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode):
                    return self._fail(run_id, "PERMISSION_DENIED")
                if info.st_size > contract.max_bytes:
                    return self._fail(run_id, "INPUT_TOO_LARGE")
                body = handle.read(contract.max_bytes + 1)
            if len(body) > contract.max_bytes:
                return self._fail(run_id, "INPUT_TOO_LARGE")
            batch = decode_batch(body, contract)
            result = self.store.complete(run_id, batch, at=self.clock())
            return {"source_id": source, "run_id": run_id, "status": "SUCCESS", **result}
        except FileNotFoundError:
            return self._fail(run_id, "LOCAL_INPUT_UNAVAILABLE", True)
        except PermissionError:
            return self._fail(run_id, "PERMISSION_DENIED")
        except Conflict:
            return {"source_id": source, "run_id": run_id, "status": "LEASE_LOST"}
        except ValueError:
            return self._fail(run_id, "SCHEMA_INVALID")
        except OSError:
            return self._fail(run_id, "PERMISSION_DENIED")
        except Exception:
            return self._fail(run_id, "UNEXPECTED_ERROR")

    def run_due(self, *, max_jobs=100, source_ids=None):
        integer(max_jobs, "maximum jobs", 1, 1000)
        scope, args = '', []
        if source_ids is not None:
            if not isinstance(source_ids, (list, tuple)) or not 1 <= len(source_ids) <= 100:
                raise ValueError('Explicit bounded source scope required')
            for value in source_ids:
                source_id(value)
            if len(set(source_ids)) != len(source_ids):
                raise ValueError('Duplicate source scope')
            scope = ' AND source_id IN (' + ','.join('?' for _ in source_ids) + ')'
            args = list(source_ids)
        at = timestamp(self.clock())
        sources = [row[0] for row in self.store.db.execute(
            "SELECT source_id FROM sources WHERE state='READY' AND ((lease_token IS NULL AND next_due_at<=?) OR lease_until<=?)" + scope + " ORDER BY next_due_at,source_id LIMIT ?",
            (at, at, *args, max_jobs))]
        return [self.run_one(source) for source in sources]
