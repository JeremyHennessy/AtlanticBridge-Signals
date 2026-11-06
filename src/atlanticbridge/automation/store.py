"""Transactional, persistent local state with fenced leases and conservative evidence semantics."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import uuid

from . import schema
from .models import SourceContract, canonical, day, decode_batch, digest, integer, text, timestamp


class Conflict(ValueError):
    """Stale work revision, lease, or incompatible source contract."""


def after(instant, seconds):
    return timestamp((datetime.fromisoformat(timestamp(instant).replace("Z", "+00:00")) + timedelta(seconds=seconds)).isoformat())


def _check_private_file(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("Private database files must be regular files, not symlinks or hard links")
    if hasattr(os, "getuid") and info.st_uid != os.getuid():
        raise ValueError("Private database must be owned by the current operator")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise ValueError("Existing database/sidecar is not private; use an owner-only file in a private directory")


def _check_private_family(path):
    if path == ":memory:":
        return
    _check_private_file(path)
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = path + suffix
        if os.path.lexists(sidecar):
            _check_private_file(sidecar)


def _prepare_private_database(path):
    if path == ":memory:":
        return
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except FileExistsError:
        pass
    else:
        os.close(fd)
    _check_private_family(path)


class Store:
    def __init__(self, path):
        self.path = str(path)
        _prepare_private_database(self.path)
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=5000")
        try:
            tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables:
                self.db.executescript("BEGIN IMMEDIATE;" + schema.SCHEMA +
                                     f"INSERT INTO foundation_meta VALUES('schema_version','{schema.VERSION}');" +
                                     "INSERT INTO foundation_meta VALUES('mode','LOCAL_ONLY_NO_DELIVERY'); COMMIT;")
            elif "foundation_meta" not in tables:
                raise ValueError("Use a separate foundation database, not an existing research database")
            version = self.db.execute("SELECT value FROM foundation_meta WHERE key='schema_version'").fetchone()
            if version is None or version[0] != str(schema.VERSION):
                raise ValueError("Unsupported foundation schema; explicit migration required")
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            _check_private_family(self.path)
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @contextmanager
    def transaction(self):
        _check_private_family(self.path)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            _check_private_family(self.path)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _audit(self, kind, object_id, action, actor, at, details):
        self.db.execute("INSERT INTO audit_log(object_type,object_id,action,actor,occurred_at,details_json) VALUES(?,?,?,?,?,?)",
                        (kind, object_id, action, text(actor, "actor", 200), at, canonical(details)))

    def register(self, contract, *, at, input_path=None):
        """Pin an immutable contract. New sources start paused. No production enrollment."""
        if not isinstance(contract, SourceContract):
            raise ValueError("Expected a validated source contract")
        from .protected_sources import validate_protected_contract
        validate_protected_contract(contract)
        at = timestamp(at)
        path = str(Path(input_path).resolve()) if input_path is not None else None
        with self.transaction():
            existing = self.db.execute("SELECT * FROM sources WHERE source_id=?", (contract.source_id,)).fetchone()
            if existing:
                if existing["contract_id"] != contract.contract_id or existing["input_path"] != path:
                    raise Conflict("Source already pinned; use a new source ID for a different contract or path")
                return False
            self.db.execute("INSERT INTO contracts VALUES(?,?,?,?)", (contract.contract_id, contract.source_id, canonical(asdict(contract)), at))
            self.db.execute("INSERT INTO sources(source_id,contract_id,state,next_due_at,input_path) VALUES(?,?,'PAUSED',?,?)",
                            (contract.source_id, contract.contract_id, at, path))
            self._audit("source", contract.source_id, "REGISTERED_PAUSED", "system", at, {"production_enabled": False})
        return True

    def contract(self, source):
        row = self.db.execute("SELECT c.contract_json FROM contracts c JOIN sources s USING(contract_id) WHERE s.source_id=?", (source,)).fetchone()
        if not row:
            raise ValueError("Unknown source")
        return SourceContract.from_dict(json.loads(row[0]))

    def _latest_source_activity(self, source):
        row = self.db.execute("SELECT MAX(occurred_at) FROM audit_log WHERE object_type='source' AND object_id=?", (source,)).fetchone()
        return row[0] if row else None

    def set_source_state(self, source, state, *, at, actor, review_reason=None):
        if state not in {"PAUSED", "READY"}:
            raise ValueError("Source state must be PAUSED or READY")
        at = timestamp(at)
        with self.transaction():
            row = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source,)).fetchone()
            if not row:
                raise ValueError("Unknown source")
            if row["lease_token"]:
                raise Conflict("Cannot change source state while a lease is held")
            floor = self._latest_source_activity(source)
            if any(row[k] and at < row[k] for k in ("last_attempt_at", "last_success_at")) or (floor and at < floor):
                raise Conflict("Source state cannot move time backwards")
            if row["state"] == "QUARANTINED":
                if state == "PAUSED":
                    # Pausing must never erase the unresolved review requirement.
                    self._audit("source", source, "PAUSED_QUARANTINE_PRESERVED", actor, at,
                                {"review_reason": review_reason, "state": "QUARANTINED"})
                    return "QUARANTINED"
                text(review_reason, "quarantine review reason", 2000)
            self.db.execute("UPDATE sources SET state=?, next_due_at=?, consecutive_failures=CASE WHEN ?='READY' THEN 0 ELSE consecutive_failures END WHERE source_id=?",
                            (state, at, state, source))
            self._audit("source", source, state, actor, at, {"review_reason": review_reason})
        return state

    def claim(self, source, *, at):
        """One atomic claim per source. Expired claims fail independently, with backoff."""
        at = timestamp(at)
        contract = self.contract(source)
        with self.transaction():
            row = self.db.execute("SELECT * FROM sources WHERE source_id=?", (source,)).fetchone()
            floor = self._latest_source_activity(source)
            if any(row[k] and at < row[k] for k in ("last_attempt_at", "last_success_at")) or (floor and at < floor):
                raise Conflict("Source claim cannot move time backwards")
            if row["lease_token"]:
                if at < row["lease_until"]:
                    return None
                self._fail(row["lease_token"], at, "LEASE_EXPIRED", transient=True, expired=True)
                return None
            if row["state"] != "READY" or at < row["next_due_at"]:
                return None
            run_id = uuid.uuid4().hex
            lease_until = after(at, contract.lease_seconds)
            self.db.execute("INSERT INTO runs(run_id,source_id,contract_id,started_at,lease_until,outcome) VALUES(?,?,?,?,?,'RUNNING')",
                            (run_id, source, contract.contract_id, at, lease_until))
            self.db.execute("UPDATE sources SET lease_token=?,lease_until=?,last_attempt_at=? WHERE source_id=?",
                            (run_id, lease_until, at, source))
            return run_id

    def _live_run(self, run_id, at, allow_expired=False):
        row = self.db.execute("SELECT r.*,s.lease_token,s.baseline_complete FROM runs r JOIN sources s USING(source_id) WHERE run_id=?", (run_id,)).fetchone()
        if not row or row["outcome"] != "RUNNING" or row["lease_token"] != run_id:
            raise Conflict("Lease is no longer current")
        if at < row["started_at"] or (not allow_expired and at >= row["lease_until"]):
            raise Conflict("Completion is outside the lease interval")
        return row

    def _fail(self, run_id, at, code, *, transient, expired=False):
        run = self._live_run(run_id, at, allow_expired=expired)
        contract = self.contract(run["source_id"])
        failures = self.db.execute("SELECT consecutive_failures FROM sources WHERE source_id=?", (run["source_id"],)).fetchone()[0] + 1
        quarantined = not transient or failures >= contract.max_failures
        status = "QUARANTINED" if quarantined else "READY"
        delay = min(contract.max_retry_seconds, contract.retry_seconds * 2 ** min(failures - 1, 20))
        outcome = "LEASE_EXPIRED" if expired else ("QUARANTINED" if quarantined else "TRANSIENT_FAILURE")
        self.db.execute("UPDATE runs SET outcome=?,error_code=?,finished_at=? WHERE run_id=?", (outcome, code, at, run_id))
        self.db.execute("UPDATE sources SET state=?,next_due_at=?,consecutive_failures=?,last_error_code=?,lease_token=NULL,lease_until=NULL WHERE source_id=?",
                        (status, after(at, delay), failures, code, run["source_id"]))
        self._audit("source", run["source_id"], outcome, "scheduler", at, {"error_code": code, "failures": failures})

    def fail(self, run_id, *, at, code, transient=False):
        at = timestamp(at)
        if code not in {"LOCAL_INPUT_UNAVAILABLE", "SCHEMA_INVALID", "PERMISSION_DENIED", "INPUT_TOO_LARGE", "UNEXPECTED_ERROR"}:
            raise ValueError("Unknown failure code")
        if type(transient) is not bool or (transient and code != "LOCAL_INPUT_UNAVAILABLE"):
            raise ValueError("Only temporary unavailable local input is retryable")
        with self.transaction():
            self._fail(run_id, at, code, transient=transient)

    def complete(self, run_id, batch, *, at):
        at = timestamp(at)
        source = self.db.execute("SELECT source_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not source:
            raise Conflict("Unknown run")
        contract = self.contract(source[0])
        batch.validate(contract)
        with self.transaction():
            run = self._live_run(run_id, at)
            prior = self.db.execute("SELECT body FROM evidence_blobs WHERE sha256=?", (batch.input_sha256,)).fetchone()
            if prior and bytes(prior[0]) != batch.input_bytes:
                raise ValueError("Retained evidence hash collision or corruption")
            self.db.execute("INSERT OR IGNORE INTO evidence_blobs VALUES(?,?,?,?,?)",
                            (batch.input_sha256, batch.input_bytes, len(batch.input_bytes), batch.input_kind, at))
            new_versions = changes = 0
            for record in batch.records:
                old = self.db.execute("SELECT * FROM records WHERE source_id=? AND record_id=?", (batch.source_id, record.record_id)).fetchone()
                content = record.content()
                content_hash = digest(content)
                version_id = digest([batch.source_id, record.record_id, contract.contract_id, content_hash])
                existed = self.db.execute("SELECT 1 FROM record_versions WHERE version_id=?", (version_id,)).fetchone()
                if not old:
                    self.db.execute("INSERT INTO records VALUES(?,?,?,?,?)", (batch.source_id, record.record_id, at, at, version_id))
                self.db.execute("INSERT OR IGNORE INTO record_versions VALUES(?,?,?,?,?,?,?,?)",
                                (version_id, batch.source_id, record.record_id, contract.contract_id, content_hash, canonical(content), batch.origin, at))
                self.db.execute("INSERT OR IGNORE INTO assessments VALUES(?,'CONTEXT_ONLY',?,0)",
                                (version_id, "Local retained evidence only; identity, current status, rights and opportunity qualification are not inferred."))
                self.db.execute("INSERT INTO observations VALUES(?,?,?,?,?)",
                                (run_id, version_id, batch.input_sha256, at, timestamp(record.source_observed_at) if record.source_observed_at else None))
                self.db.execute("UPDATE records SET current_version_id=?, last_imported_at=? WHERE source_id=? AND record_id=?",
                                (version_id, at, batch.source_id, record.record_id))
                changed = old is None or old["current_version_id"] != version_id
                new_versions += not bool(existed)
                # Returning to a previously observed version is a state observation, not a new event.
                if run["baseline_complete"] and not existed:
                    kind = "RECORD_CONTENT_CHANGED" if old else "RECORD_FIRST_OBSERVED"
                    self.db.execute("INSERT INTO evidence_events VALUES(?,?,?,?,?,?,?,?,?,0)",
                                    (digest(["observed-version", version_id]), batch.source_id, record.record_id,
                                     old["current_version_id"] if old else None, version_id, kind, at, record.event_date, record.published_date))
                    changes += 1
                item_id = digest(["review-work", batch.source_id, record.record_id])
                item = self.db.execute("SELECT * FROM work_items WHERE item_id=?", (item_id,)).fetchone()
                if item is None:
                    self.db.execute("INSERT INTO work_items VALUES(?,?,?,?,'TRIAGE',1,'',NULL,1,?,?)",
                                    (item_id, batch.source_id, record.record_id, version_id, at, at))
                    self._audit("work_item", item_id, "CREATED_CONTEXT_ONLY", "ingest", at, {"version_id": version_id, "baseline": not bool(run["baseline_complete"])})
                elif changed:
                    if at < item["updated_at"]:
                        raise Conflict("Completion predates a newer work-item save; retry within the lease with a fresh timestamp")
                    self.db.execute("UPDATE work_items SET latest_version_id=?,needs_review=1,revision=revision+1,updated_at=? WHERE item_id=?", (version_id, at, item_id))
                    self._audit("work_item", item_id, "EVIDENCE_UPDATED", "ingest", at, {"from_version_id": item["latest_version_id"], "to_version_id": version_id})
            self.db.execute("UPDATE runs SET outcome='SUCCESS',finished_at=?,record_count=?,input_sha256=? WHERE run_id=?",
                            (at, len(batch.records), batch.input_sha256, run_id))
            self.db.execute("UPDATE sources SET baseline_complete=1,last_success_at=?,last_input_sha256=?,consecutive_failures=0,last_error_code=NULL,lease_token=NULL,lease_until=NULL,next_due_at=? WHERE source_id=?",
                            (at, batch.input_sha256, after(at, contract.cadence_seconds), batch.source_id))
            self._audit("source", batch.source_id, "LOCAL_IMPORT_SUCCEEDED", "ingest", at,
                        {"run_id": run_id, "records": len(batch.records), "new_versions": new_versions, "review_events": changes, "absence_inferred": False})
        return {"records": len(batch.records), "new_versions": new_versions, "review_events": changes, "public_alerts": 0}

    def update_work_item(self, item_id, *, expected_revision, status, notes, due_date, needs_review, at, actor):
        integer(expected_revision, "revision", 1, 2147483647)
        if status not in {"TRIAGE", "ACTIVE", "HOLD", "DONE"}:
            raise ValueError("Invalid work item status")
        if not isinstance(notes, str) or len(notes) > 16000 or "\x00" in notes:
            raise ValueError("Invalid work notes")
        if type(needs_review) is not bool:
            raise ValueError("needs_review must be a boolean")
        due_date = day(due_date)
        at = timestamp(at)
        with self.transaction():
            previous = self.db.execute("SELECT * FROM work_items WHERE item_id=?", (item_id,)).fetchone()
            if not previous or previous["revision"] != expected_revision:
                raise Conflict("Work item was changed; reload it before saving")
            if at < previous["updated_at"]:
                raise Conflict("Work update cannot move time backwards")
            self.db.execute("UPDATE work_items SET status=?,notes=?,due_date=?,needs_review=?,revision=revision+1,updated_at=? WHERE item_id=? AND revision=?",
                            (status, notes, due_date, int(needs_review), at, item_id, expected_revision))
            self._audit("work_item", item_id, "USER_SAVED", actor, at,
                        {"previous_revision": expected_revision, "previous": dict(previous), "new": {"status": status, "notes": notes, "due_date": due_date, "needs_review": needs_review}})
        return expected_revision + 1

    def work_items(self):
        return [dict(row) for row in self.db.execute("SELECT * FROM work_items ORDER BY source_id,record_id")]

    def health(self, *, at):
        at = timestamp(at)
        result = []
        for row in self.db.execute("SELECT * FROM sources ORDER BY source_id"):
            d = dict(row)
            d.pop("input_path")
            d.pop("lease_token")
            d["local_import_due"] = d["state"] == "READY" and at >= d["next_due_at"]
            d["lease_expired"] = bool(d["lease_until"] and at >= d["lease_until"])
            d["live_source_freshness"] = "UNVERIFIED_LOCAL_IMPORT_ONLY"
            d["coverage"] = self.contract(d["source_id"]).coverage
            d["production_enabled"] = False
            result.append(d)
        return {"mode": "LOCAL_ONLY_NO_DELIVERY", "sources": result}

    def backup(self, destination):
        """Use SQLite's snapshot API, not a copy of a live WAL database. Never overwrite."""
        destination = Path(destination)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
            target.close()
            report = verify_database(destination)
            with destination.open("rb") as handle:
                os.fsync(handle.fileno())
            return report
        except BaseException:
            target.close()
            # Do not remove a possibly useful partial artifact; report failure to caller.
            raise


def verify_database(path):
    """Read-only integrity and content-hash check. Does not promote or overwrite anything."""
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Backup SQLite integrity failed")
        version = db.execute("SELECT value FROM foundation_meta WHERE key='schema_version'").fetchone()
        if not version or version[0] != str(schema.VERSION):
            raise ValueError("Unsupported backup schema")
        for sha, body, count in db.execute("SELECT sha256,body,byte_count FROM evidence_blobs"):
            if len(body) != count or hashlib.sha256(body).hexdigest() != sha:
                raise ValueError("Backup evidence hash mismatch")
        for version_id, source, record_id, contract_id, sha, content in db.execute("SELECT version_id,source_id,record_id,contract_id,content_sha256,content_json FROM record_versions"):
            if digest(json.loads(content)) != sha or digest([source, record_id, contract_id, sha]) != version_id:
                raise ValueError("Backup record hash mismatch")
        for contract_id, source, content in db.execute("SELECT contract_id,source_id,contract_json FROM contracts"):
            contract = SourceContract.from_dict(json.loads(content))
            if contract.contract_id != contract_id or contract.source_id != source:
                raise ValueError("Backup source contract mismatch")
        bindings = db.execute("""SELECT v.source_id,v.record_id,v.content_json,v.origin,
            c.contract_json,b.body,o.source_observed_at,r.source_id
            FROM observations o JOIN record_versions v USING(version_id)
            JOIN contracts c ON c.contract_id=v.contract_id
            JOIN evidence_blobs b ON b.sha256=o.input_sha256
            JOIN runs r USING(run_id)""")
        decoded = {}
        for source, record_id, content, origin, contract_json, raw, observed, run_source in bindings:
            contract = SourceContract.from_dict(json.loads(contract_json))
            key = (contract.contract_id, hashlib.sha256(raw).hexdigest())
            if key not in decoded:
                if len(decoded) >= 2:
                    decoded.clear()  # Bound validation memory regardless of database history size.
                decoded[key] = {r.record_id: r for r in decode_batch(raw, contract).records}
            record = decoded[key].get(record_id)
            if (source != contract.source_id or run_source != source or origin != contract.origin
                    or record is None or canonical(record.content()) != content
                    or (timestamp(record.source_observed_at) if record.source_observed_at else None) != observed):
                raise ValueError("Backup observation-to-evidence binding failed")
        for table, pointer in (("records", "current_version_id"), ("work_items", "latest_version_id")):
            mismatch = db.execute(f"""SELECT 1 FROM {table} x JOIN record_versions v ON v.version_id=x.{pointer}
                WHERE x.source_id<>v.source_id OR x.record_id<>v.record_id LIMIT 1""").fetchone()
            if mismatch:
                raise ValueError("Backup current-version identity mismatch")
        from .integrity import validate_semantics
        validate_semantics(db)
        return {"integrity": "ok", "schema_version": schema.VERSION,
                "evidence_blobs": db.execute("SELECT COUNT(*) FROM evidence_blobs").fetchone()[0],
                "work_items": db.execute("SELECT COUNT(*) FROM work_items").fetchone()[0],
                "mode": "LOCAL_ONLY_NO_DELIVERY"}
    finally:
        db.close()
