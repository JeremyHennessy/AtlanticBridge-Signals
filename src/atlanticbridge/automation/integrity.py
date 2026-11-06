"""Semantic snapshot validation in addition to SQLite and content-hash integrity."""
from __future__ import annotations
import json

from .models import SourceContract, Record, canonical, day, decode_batch, digest, timestamp
from .protected_sources import validate_protected_contract


def _time(value, label):
    if value is None or timestamp(value) != value:
        raise ValueError(f"Backup {label} is not a canonical timestamp")
    return value


def validate_semantics(db):
    """Reject incoherent runs, checkpoints, pointers and work, including empty runs.

    This validates one snapshot. It does not authenticate a file against a
    hostile privileged editor who can rewrite all its evidence and audit data.
    """
    mode = db.execute("SELECT value FROM foundation_meta WHERE key='mode'").fetchone()
    if not mode or mode[0] != "LOCAL_ONLY_NO_DELIVERY":
        raise ValueError("Backup mode is not local-only")
    for contract in db.execute("SELECT * FROM contracts"):
        parsed = SourceContract.from_dict(json.loads(contract["contract_json"]))
        validate_protected_contract(parsed)
        if parsed.source_id != contract["source_id"]:
            raise ValueError("Backup contract source mismatch")
        _time(contract["created_at"], "contract creation")

    for run in db.execute("SELECT rowid AS sequence,* FROM runs"):
        source = db.execute("SELECT * FROM sources WHERE source_id=?", (run["source_id"],)).fetchone()
        if not source or source["contract_id"] != run["contract_id"]:
            raise ValueError("Backup run-to-source contract mismatch")
        start = _time(run["started_at"], "run start")
        end = _time(run["lease_until"], "run lease")
        if end <= start:
            raise ValueError("Backup lease does not follow run start")
        observations = db.execute("""SELECT o.*,v.source_id,v.record_id,v.contract_id,v.content_json,v.origin
            FROM observations o JOIN record_versions v USING(version_id) WHERE o.run_id=? LIMIT 10001""", (run["run_id"],)).fetchall()
        if run["outcome"] == "RUNNING":
            if (run["finished_at"] is not None or run["error_code"] is not None
                    or run["record_count"] is not None or run["input_sha256"] is not None or observations
                    or source["lease_token"] != run["run_id"] or source["lease_until"] != end
                    or source["state"] != "READY"):
                raise ValueError("Backup running lease state is inconsistent")
            continue
        finished = _time(run["finished_at"], "run finish")
        if finished < start:
            raise ValueError("Backup run finishes before it starts")
        if run["outcome"] != "SUCCESS":
            if (run["outcome"] not in {"TRANSIENT_FAILURE", "QUARANTINED", "LEASE_EXPIRED"}
                    or not run["error_code"] or run["record_count"] is not None
                    or run["input_sha256"] is not None or observations):
                raise ValueError("Backup failed run contains accepted evidence")
            if run["outcome"] == "LEASE_EXPIRED" and finished < end:
                raise ValueError("Backup expired lease finished before expiry")
            continue
        blob = db.execute("SELECT body FROM evidence_blobs WHERE sha256=?", (run["input_sha256"],)).fetchone()
        if blob is None or run["error_code"] is not None or finished >= end:
            raise ValueError("Backup successful run has missing evidence or an invalid completion")
        contract_json = db.execute("SELECT contract_json FROM contracts WHERE contract_id=?", (run["contract_id"],)).fetchone()[0]
        contract = SourceContract.from_dict(json.loads(contract_json))
        batch = decode_batch(bytes(blob[0]), contract)
        if (type(run["record_count"]) is not int or run["record_count"] != len(batch.records)
                or len(observations) != len(batch.records)):
            raise ValueError("Backup successful-run record count differs from accepted evidence")
        expected = {r.record_id: r for r in batch.records}
        seen = set()
        for observation in observations:
            record = expected.get(observation["record_id"])
            if (record is None or observation["record_id"] in seen
                    or observation["source_id"] != run["source_id"]
                    or observation["contract_id"] != run["contract_id"]
                    or observation["origin"] != contract.origin
                    or observation["input_sha256"] != run["input_sha256"]
                    or observation["imported_at"] != finished
                    or canonical(record.content()) != observation["content_json"]
                    or (timestamp(record.source_observed_at) if record.source_observed_at else None) != observation["source_observed_at"]):
                raise ValueError("Backup accepted-run observation differs from its evidence")
            seen.add(record.record_id)

    for source in db.execute("SELECT * FROM sources"):
        _time(source["next_due_at"], "source due time")
        latest_attempt = db.execute("SELECT * FROM runs WHERE source_id=? ORDER BY rowid DESC LIMIT 1", (source["source_id"],)).fetchone()
        success = db.execute("SELECT * FROM runs WHERE source_id=? AND outcome='SUCCESS' ORDER BY rowid DESC LIMIT 1", (source["source_id"],)).fetchone()
        expected_last = latest_attempt["started_at"] if latest_attempt else None
        if source["last_attempt_at"] != expected_last:
            raise ValueError("Backup source last-attempt checkpoint is inconsistent")
        if (source["baseline_complete"] != int(success is not None)
                or source["last_success_at"] != (success["finished_at"] if success else None)
                or source["last_input_sha256"] != (success["input_sha256"] if success else None)):
            raise ValueError("Backup source success checkpoint is inconsistent")
        running = db.execute("SELECT * FROM runs WHERE source_id=? AND outcome='RUNNING'", (source["source_id"],)).fetchall()
        if len(running) > 1:
            raise ValueError("Backup has multiple active runs for a source")
        if (source["lease_token"] != (running[0]["run_id"] if running else None)
                or source["lease_until"] != (running[0]["lease_until"] if running else None)):
            raise ValueError("Backup source lease checkpoint is inconsistent")
        if type(source["consecutive_failures"]) is not int or source["consecutive_failures"] < 0:
            raise ValueError("Backup source failure count is invalid")
        if source["state"] == "QUARANTINED" and (not source["last_error_code"] or not source["consecutive_failures"]):
            raise ValueError("Backup quarantine has no unresolved failure")

    expected_events = 0
    for version in db.execute("SELECT * FROM record_versions"):
        content = json.loads(version["content_json"])
        if not isinstance(content, dict) or set(content) != {"record_id", "facts", "source_url", "event_date", "published_date"}:
            raise ValueError("Backup version has an invalid normalized structure")
        contract_json = db.execute("SELECT contract_json FROM contracts WHERE contract_id=?", (version["contract_id"],)).fetchone()[0]
        contract = SourceContract.from_dict(json.loads(contract_json))
        Record(**content).validate(contract)
        if content["record_id"] != version["record_id"] or contract.source_id != version["source_id"] or contract.origin != version["origin"]:
            raise ValueError("Backup version identity is inconsistent")
        first = db.execute("""SELECT o.*,r.rowid AS run_sequence FROM observations o JOIN runs r USING(run_id)
            WHERE version_id=? ORDER BY r.rowid LIMIT 1""", (version["version_id"],)).fetchone()
        if first is None or version["first_imported_at"] != first["imported_at"]:
            raise ValueError("Backup version lacks its first accepted observation")
        assessment = db.execute("SELECT * FROM assessments WHERE version_id=?", (version["version_id"],)).fetchone()
        if assessment is None or assessment["disposition"] != "CONTEXT_ONLY" or assessment["lead_eligible"] != 0:
            raise ValueError("Backup version lacks its context-only assessment")
        baseline = db.execute("SELECT run_id FROM runs WHERE source_id=? AND outcome='SUCCESS' ORDER BY rowid LIMIT 1", (version["source_id"],)).fetchone()[0]
        event = db.execute("SELECT * FROM evidence_events WHERE to_version_id=?", (version["version_id"],)).fetchall()
        if first["run_id"] == baseline:
            if event:
                raise ValueError("Backup baseline must not emit review events")
            continue
        expected_events += 1
        previous = db.execute("""SELECT o.version_id FROM observations o JOIN record_versions v USING(version_id)
            JOIN runs r USING(run_id) WHERE v.source_id=? AND v.record_id=? AND r.rowid<?
            ORDER BY r.rowid DESC LIMIT 1""", (version["source_id"], version["record_id"], first["run_sequence"])).fetchone()
        if len(event) != 1:
            raise ValueError("Backup version is missing its unique review event")
        event = event[0]
        if (event["event_id"] != digest(["observed-version", version["version_id"]])
                or event["source_id"] != version["source_id"] or event["record_id"] != version["record_id"]
                or event["from_version_id"] != (previous[0] if previous else None)
                or event["kind"] != ("RECORD_CONTENT_CHANGED" if previous else "RECORD_FIRST_OBSERVED")
                or event["imported_at"] != first["imported_at"] or event["event_date"] != content["event_date"]
                or event["published_date"] != content["published_date"] or event["public_alert_allowed"] != 0):
            raise ValueError("Backup review event has inconsistent identity, clock or semantics")
    if db.execute("SELECT COUNT(*) FROM evidence_events").fetchone()[0] != expected_events:
        raise ValueError("Backup contains orphan or duplicate review events")

    for record in db.execute("SELECT * FROM records"):
        observation_query = """SELECT o.*,v.version_id FROM observations o JOIN record_versions v USING(version_id)
            JOIN runs r USING(run_id) WHERE v.source_id=? AND v.record_id=? ORDER BY r.rowid """
        key = (record["source_id"], record["record_id"])
        latest = db.execute(observation_query + "DESC LIMIT 1", key).fetchone()
        first = db.execute(observation_query + "ASC LIMIT 1", key).fetchone()
        if (latest is None or first is None or record["current_version_id"] is None
                or record["current_version_id"] != latest["version_id"]
                or record["first_imported_at"] != first["imported_at"]
                or record["last_imported_at"] != latest["imported_at"]):
            raise ValueError("Backup record current-version pointer or import clock is inconsistent")
        item = db.execute("SELECT * FROM work_items WHERE source_id=? AND record_id=?", (record["source_id"], record["record_id"])).fetchone()
        if (item is None or item["item_id"] != digest(["review-work", record["source_id"], record["record_id"]])
                or item["latest_version_id"] != record["current_version_id"]
                or item["created_at"] != record["first_imported_at"]
                or item["status"] not in {"TRIAGE", "ACTIVE", "HOLD", "DONE"}
                or item["needs_review"] not in (0, 1) or type(item["revision"]) is not int or item["revision"] < 1
                or not isinstance(item["notes"], str) or len(item["notes"]) > 16000 or "\x00" in item["notes"]):
            raise ValueError("Backup persistent work item is inconsistent with its source record")
        day(item["due_date"])
        if _time(item["updated_at"], "work update") < item["created_at"]:
            raise ValueError("Backup work item update predates creation")
        audit_count = 0
        previous_time = None
        for audit in db.execute("SELECT occurred_at FROM audit_log WHERE object_type='work_item' AND object_id=? ORDER BY audit_id", (item["item_id"],)):
            audit_time = _time(audit["occurred_at"], "work audit time")
            if previous_time is not None and audit_time < previous_time:
                raise ValueError("Backup work audit history moves backwards in time")
            if previous_time is None and audit_time != item["created_at"]:
                raise ValueError("Backup work creation differs from its first audit time")
            previous_time = audit_time
            audit_count += 1
        if audit_count != item["revision"] or previous_time != item["updated_at"]:
            raise ValueError("Backup work revision or update time differs from its audit history")
    if db.execute("SELECT COUNT(*) FROM records").fetchone()[0] != db.execute("SELECT COUNT(*) FROM work_items").fetchone()[0]:
        raise ValueError("Backup work items do not match retained source records")
    if db.execute("SELECT 1 FROM evidence_blobs b WHERE NOT EXISTS(SELECT 1 FROM runs r WHERE r.outcome='SUCCESS' AND r.input_sha256=b.sha256) LIMIT 1").fetchone():
        raise ValueError("Backup retained blob lacks a successful ingestion run")
