from __future__ import annotations
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlanticbridge.automation import Conflict, OfflineScheduler, SourceContract, Store
from atlanticbridge.automation.models import Record, canonical, decode_batch, timestamp
from atlanticbridge.automation.review_bridge import prepare_review_collection
from atlanticbridge.automation.store import after, verify_database
from atlanticbridge.sources.halifax_building_permits import build_pinned_collection
from atlanticbridge.sources.nl_environmental_assessments import build_fixture_collection

NOW = "2026-11-06T12:00:00Z"
LATER = "2026-11-07T12:00:00Z"
THIRD = "2026-11-08T12:00:00Z"


def contract(source="fixture", **overrides):
    return SourceContract.from_dict({"source_id": source, "title": "Invented test source",
        "parser_version": "test-v1", "allowed_fields": ["title", "amount", "status"],
        "license_name": "Invented fixture; no production rights claimed", "license_url": "https://example.org/license",
        "attribution": "Invented test data", "coverage": "INCOMPLETE_NO_ABSENCE_PROOF",
        "origin": "INVENTED_FIXTURE", **overrides})


def body(c, rows=None, **overrides):
    return canonical({"format_version": 1, "source_id": c.source_id, "origin": c.origin,
        "coverage": c.coverage, "records": rows if rows is not None else [
            {"record_id": "one", "facts": {"title": "Invented first record"},
             "event_date": "2023-08-03", "published_date": "2023-08-04"}], **overrides}).encode()


class AutomationFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "foundation.sqlite"
        self.store = Store(self.path)
        self.addCleanup(lambda: self.store.close())
        self.c = contract()
        self.input = self.root / "fixture.json"
        self.input.write_bytes(body(self.c))
        self.store.register(self.c, at=NOW, input_path=self.input)

    def ready(self, source="fixture", at=NOW):
        self.store.set_source_state(source, "READY", at=at, actor="test reviewer")

    def ingest(self, rows=None, at=NOW, c=None):
        c = c or self.c
        run = self.store.claim(c.source_id, at=at)
        self.assertIsNotNone(run)
        return self.store.complete(run, decode_batch(body(c, rows), c), at=at)

    def count(self, table):
        return self.store.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def test_source_starts_paused(self):
        self.assertIsNone(self.store.claim("fixture", at=NOW))
        self.assertEqual(self.store.health(at=NOW)["sources"][0]["state"], "PAUSED")

    def test_network_or_production_contracts_rejected(self):
        for override in ({"production_enabled": True}, {"production_enabled": 0}, {"access_method": "HTTP"}, {"origin": "LIVE_HTTP_RESPONSE"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                contract(**override)

    def test_contract_values_strict(self):
        for override in ({"cadence_seconds": True}, {"lease_seconds": 0}, {"source_id": "../escape"},
                         {"allowed_fields": ["title", "title"]}, {"license_url": "http://example.org"},
                         {"max_bytes": 10 ** 9}, {"max_failures": 21}, {"retry_seconds": 10, "max_retry_seconds": 1}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                contract(**override)

    def test_idempotent_registration_and_immutable_pin(self):
        self.assertFalse(self.store.register(self.c, at=LATER, input_path=self.input))
        with self.assertRaises(Conflict):
            self.store.register(replace(self.c, parser_version="changed"), at=LATER, input_path=self.input)
        with self.assertRaises(Conflict):
            self.store.register(self.c, at=LATER, input_path=self.root / "other")

    def test_naive_time_rejected_and_offsets_canonical(self):
        with self.assertRaises(ValueError): timestamp("2026-11-06T12:00:00")
        self.assertEqual(timestamp(NOW), timestamp("2026-11-06T08:00:00-04:00"))

    def test_baseline_creates_work_without_new_event(self):
        self.ready(); result = self.ingest()
        self.assertEqual(result, {"records": 1, "new_versions": 1, "review_events": 0, "public_alerts": 0})
        self.assertEqual(self.count("work_items"), 1)
        self.assertEqual(self.count("evidence_events"), 0)
        assessment = dict(self.store.db.execute("SELECT * FROM assessments").fetchone())
        self.assertEqual(assessment["lead_eligible"], 0)
        self.assertEqual(assessment["disposition"], "CONTEXT_ONLY")

    def test_restart_replay_and_retrieval_clock_do_not_duplicate(self):
        self.ready(); self.ingest()
        self.store.close(); self.store = Store(self.path)
        rows = [{"record_id": "one", "facts": {"title": "Invented first record"},
                 "event_date": "2023-08-03", "published_date": "2023-08-04", "source_observed_at": LATER}]
        result = self.ingest(rows, at=LATER)
        self.assertEqual(result["new_versions"], 0)
        self.assertEqual(self.count("observations"), 2)
        self.assertEqual(self.count("evidence_events"), 0)
        self.assertEqual(self.count("work_items"), 1)

    def test_source_and_record_namespace_are_separate(self):
        c2 = contract("fixture2")
        self.store.register(c2, at=NOW)
        self.ready(); self.ready("fixture2")
        self.ingest(); self.ingest(c=c2)
        self.assertEqual(self.count("records"), 2)
        self.assertEqual(self.count("work_items"), 2)
        self.assertEqual(self.count("record_versions"), 2)

    def test_change_event_preserves_original_clocks(self):
        self.ready(); self.ingest()
        self.ingest([{"record_id": "one", "facts": {"title": "Changed"}, "event_date": "2023-08-03"}], at=LATER)
        event = dict(self.store.db.execute("SELECT * FROM evidence_events").fetchone())
        self.assertEqual(event["kind"], "RECORD_CONTENT_CHANGED")
        self.assertEqual(event["event_date"], "2023-08-03")
        self.assertEqual(event["imported_at"], timestamp(LATER))
        self.assertEqual(event["public_alert_allowed"], 0)

    def test_newly_imported_is_not_new_business_event(self):
        self.ready(); self.ingest()
        self.ingest([{"record_id": "two", "facts": {"title": "Other"}}], at=LATER)
        event = dict(self.store.db.execute("SELECT * FROM evidence_events").fetchone())
        self.assertEqual(event["kind"], "RECORD_FIRST_OBSERVED")
        self.assertIsNone(event["event_date"])

    def test_missing_records_do_not_delete_or_close_work(self):
        self.ready(); self.ingest(); self.ingest([], at=LATER)
        self.assertEqual(self.count("records"), 1)
        self.assertEqual(self.count("work_items"), 1)
        self.assertEqual(self.count("evidence_events"), 0)
        self.ingest(at=THIRD)
        self.assertEqual(self.count("evidence_events"), 0)

    def test_old_version_reappearance_does_not_emit_replay_event(self):
        self.ready(); self.ingest()
        self.ingest([{"record_id": "one", "facts": {"title": "changed"}}], at=LATER)
        self.ingest(at=THIRD)
        self.assertEqual(self.count("evidence_events"), 1)
        self.assertEqual(self.store.work_items()[0]["needs_review"], 1)

    def test_duplicate_record_batch_rejected_atomically(self):
        self.ready(); self.ingest()
        before = self.count("evidence_blobs")
        rows = [{"record_id": "two", "facts": {"title": "one"}}, {"record_id": "two", "facts": {"title": "two"}}]
        with self.assertRaises(ValueError): decode_batch(body(self.c, rows), self.c)
        self.assertEqual(self.count("evidence_blobs"), before)
        self.assertEqual(self.count("records"), 1)

    def test_unknown_fields_and_type_invalid_facts_rejected(self):
        cases = [{"title": {"nested": "secret"}}, {"not allowed": "value"}, {"title": float("nan")}, {"title": "\x00"}]
        for facts in cases:
            with self.subTest(facts=facts), self.assertRaises(ValueError):
                decode_batch(body(self.c, [{"record_id": "x", "facts": facts}]), self.c)

    def test_duplicate_keys_and_nonfinite_json_rejected(self):
        for bad in (b'{"format_version":1,"format_version":1}', b'{"x":NaN}'):
            with self.assertRaises(ValueError): decode_batch(bad, self.c)

    def test_origin_and_coverage_cannot_be_changed(self):
        for override in ({"origin": "LIVE_HTTP_RESPONSE"}, {"coverage": "COMPLETE"}, {"source_id": "other"}, {"format_version": True}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                decode_batch(body(self.c, **override), self.c)

    def test_retained_bytes_bind_exact_types_and_values(self):
        b = decode_batch(body(self.c, [{"record_id": "one", "facts": {"amount": 1}}]), self.c)
        with self.assertRaises(ValueError):
            replace(b, records=(Record("one", {"amount": True}),)).validate(self.c)
        with self.assertRaises(ValueError):
            replace(b, input_sha256="a" * 64).validate(self.c)

    def test_bad_dates_and_unsafe_urls_rejected(self):
        for override in ({"event_date": "2026-02-30"}, {"event_date": "2026-1-1"},
                         {"source_url": "javascript:alert(1)"}, {"source_url": "https://user:pass@example.org"},
                         {"source_observed_at": NOW[:-1]}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                decode_batch(body(self.c, [{"record_id": "one", "facts": {}, **override}]), self.c)

    def test_expired_lease_is_fenced_and_backed_off(self):
        self.ready(); old_run = self.store.claim("fixture", at=NOW)
        expired = after(NOW, self.c.lease_seconds)
        with self.assertRaises(Conflict):
            self.store.complete(old_run, decode_batch(body(self.c), self.c), at=expired)
        self.assertIsNone(self.store.claim("fixture", at=expired))
        row = self.store.db.execute("SELECT * FROM runs WHERE run_id=?", (old_run,)).fetchone()
        self.assertEqual(row["outcome"], "LEASE_EXPIRED")
        self.assertIsNone(self.store.claim("fixture", at=after(expired, 1)))
        next_run = self.store.claim("fixture", at=after(expired, self.c.retry_seconds))
        self.assertIsNotNone(next_run)
        with self.assertRaises(Conflict):
            self.store.complete(old_run, decode_batch(body(self.c), self.c), at=after(expired, self.c.retry_seconds))

    def test_two_connections_cannot_claim_same_source(self):
        self.ready()
        with Store(self.path) as other:
            self.assertIsNotNone(self.store.claim("fixture", at=NOW))
            self.assertIsNone(other.claim("fixture", at=NOW))

    def test_failure_preserves_previous_evidence(self):
        self.ready(); self.ingest()
        run = self.store.claim("fixture", at=LATER)
        self.store.fail(run, at=LATER, code="SCHEMA_INVALID")
        self.assertEqual(self.count("records"), 1)
        health = self.store.health(at=LATER)["sources"][0]
        self.assertEqual(health["last_success_at"], timestamp(NOW))
        self.assertEqual(health["state"], "QUARANTINED")
        self.assertEqual(health["live_source_freshness"], "UNVERIFIED_LOCAL_IMPORT_ONLY")

    def test_nontransient_failure_not_retried_without_review(self):
        self.ready(); run = self.store.claim("fixture", at=NOW)
        with self.assertRaises(ValueError): self.store.fail(run, at=NOW, code="PERMISSION_DENIED", transient=True)
        self.store.fail(run, at=NOW, code="PERMISSION_DENIED")
        self.assertIsNone(self.store.claim("fixture", at=LATER))
        with self.assertRaises(ValueError): self.ready(at=LATER)
        self.store.set_source_state("fixture", "READY", at=LATER, actor="reviewer", review_reason="Local file permission corrected")
        self.assertIsNotNone(self.store.claim("fixture", at=LATER))

    def test_transient_backoff_reaches_quarantine_cap(self):
        self.ready(); at = NOW
        for i in range(self.c.max_failures):
            run = self.store.claim("fixture", at=at)
            self.assertIsNotNone(run)
            self.store.fail(run, at=at, code="LOCAL_INPUT_UNAVAILABLE", transient=True)
            row = self.store.db.execute("SELECT * FROM sources").fetchone()
            at = row["next_due_at"]
        self.assertEqual(row["state"], "QUARANTINED")

    def test_scheduler_isolates_bad_source_from_good(self):
        self.input.write_bytes(b"bad JSON")
        good = contract("good"); path = self.root / "good.json"; path.write_bytes(body(good))
        self.store.register(good, at=NOW, input_path=path)
        self.ready(); self.ready("good")
        outcomes = OfflineScheduler(self.store, clock=lambda: NOW).run_due()
        self.assertEqual([o["status"] for o in outcomes], ["FAILED", "SUCCESS"])
        self.assertEqual(self.count("records"), 1)
        self.assertEqual(self.store.work_items()[0]["source_id"], "good")

    def test_scheduler_missing_file_retries_boundedly(self):
        self.input.unlink(); self.ready()
        outcome = OfflineScheduler(self.store, clock=lambda: NOW).run_one("fixture")
        self.assertEqual(outcome["error_code"], "LOCAL_INPUT_UNAVAILABLE")
        self.assertEqual(self.store.health(at=NOW)["sources"][0]["state"], "READY")

    def test_scheduler_refuses_oversized_input(self):
        self.input.write_bytes(b"x" * (self.c.max_bytes + 1)); self.ready()
        result = OfflineScheduler(self.store, clock=lambda: NOW).run_one("fixture")
        self.assertEqual(result["error_code"], "INPUT_TOO_LARGE")
        self.assertEqual(self.count("evidence_blobs"), 0)

    def test_work_update_persists_and_rejects_stale_editor(self):
        self.ready(); self.ingest(); item = self.store.work_items()[0]
        rev = self.store.update_work_item(item["item_id"], expected_revision=1, status="HOLD", notes="Review retained evidence",
                due_date="2026-11-09", needs_review=False, at=NOW, actor="reviewer")
        self.assertEqual(rev, 2)
        with self.assertRaises(Conflict):
            self.store.update_work_item(item["item_id"], expected_revision=1, status="DONE", notes="old editor", due_date=None,
                                        needs_review=False, at=NOW, actor="reviewer")
        self.store.close(); self.store = Store(self.path)
        self.assertEqual(self.store.work_items()[0]["notes"], "Review retained evidence")
        self.assertEqual(self.store.work_items()[0]["due_date"], "2026-11-09")

    def test_ingest_preserves_operator_status_notes_and_due_date(self):
        self.ready(); self.ingest(); item = self.store.work_items()[0]
        self.store.update_work_item(item["item_id"], expected_revision=1, status="DONE", notes="Kept note", due_date="2026-11-09",
                                    needs_review=False, at=NOW, actor="reviewer")
        self.ingest([{"record_id": "one", "facts": {"title": "Changed"}}], at=LATER)
        updated = self.store.work_items()[0]
        self.assertEqual((updated["status"], updated["notes"], updated["due_date"]), ("DONE", "Kept note", "2026-11-09"))
        self.assertEqual(updated["needs_review"], 1)
        self.assertEqual(updated["revision"], 3)

    def test_snapshot_backup_restores_exact_evidence_and_work(self):
        self.ready(); self.ingest(); destination = self.root / "backup.sqlite"
        report = self.store.backup(destination)
        self.assertEqual(report["integrity"], "ok")
        with Store(destination) as restored:
            self.assertEqual(restored.work_items(), self.store.work_items())
            self.assertEqual(restored.db.execute("SELECT body FROM evidence_blobs").fetchone()[0], body(self.c))
        with self.assertRaises(FileExistsError): self.store.backup(destination)

    def test_database_rejects_unrelated_or_future_schema(self):
        other = self.root / "other.sqlite"
        with sqlite3.connect(other) as connection: connection.execute("CREATE TABLE existing(x)")
        with self.assertRaises(ValueError): Store(other)
        self.store.db.execute("UPDATE foundation_meta SET value='999' WHERE key='schema_version'")
        with self.assertRaises(ValueError): Store(self.path)

    def test_evidence_versions_contracts_and_audit_are_immutable(self):
        self.ready(); self.ingest()
        for table in ("record_versions", "evidence_blobs", "contracts", "audit_log"):
            with self.subTest(table=table), self.assertRaises(sqlite3.IntegrityError):
                self.store.db.execute("DELETE FROM " + table)

    def test_late_failure_does_not_change_successful_run(self):
        self.ready(); run = self.store.claim("fixture", at=NOW)
        self.store.complete(run, decode_batch(body(self.c), self.c), at=NOW)
        with self.assertRaises(Conflict): self.store.fail(run, at=LATER, code="UNEXPECTED_ERROR")
        self.assertEqual(self.store.health(at=LATER)["sources"][0]["last_success_at"], timestamp(NOW))

    def test_complete_rolls_back_all_evidence_on_mid_transaction_error(self):
        self.ready()
        self.store.db.execute("CREATE TRIGGER test_failure BEFORE INSERT ON work_items BEGIN SELECT RAISE(ABORT,'injected test failure'); END;")
        run = self.store.claim("fixture", at=NOW)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.complete(run, decode_batch(body(self.c), self.c), at=NOW)
        for table in ("records", "record_versions", "evidence_blobs", "observations", "assessments"):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(self.store.db.execute("SELECT outcome FROM runs").fetchone()[0], "RUNNING")

    def test_cannot_move_source_time_before_last_success(self):
        self.ready(); run = self.store.claim("fixture", at=NOW)
        self.store.complete(run, decode_batch(body(self.c), self.c), at=after(NOW, 30))
        with self.assertRaises(Conflict): self.ready(at=after(NOW, 10))
        with self.assertRaises(Conflict): self.store.claim("fixture", at=after(NOW, 10))

    def test_active_source_does_not_starve_other_due_source(self):
        self.ready(); self.store.claim("fixture", at=NOW)
        c = contract("other"); path = self.root / "other.json"; path.write_bytes(body(c))
        self.store.register(c, at=NOW, input_path=path); self.ready("other")
        result = OfflineScheduler(self.store, clock=lambda: NOW).run_due(max_jobs=1)
        self.assertEqual(result[0]["source_id"], "other")
        self.assertEqual(result[0]["status"], "SUCCESS")

    def test_scheduler_refuses_file_replaced_by_symlink(self):
        replacement = self.root / "replacement.json"; replacement.write_bytes(body(self.c))
        self.input.unlink(); self.input.symlink_to(replacement); self.ready()
        result = OfflineScheduler(self.store, clock=lambda: NOW).run_one("fixture")
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(self.count("records"), 0)

    def test_backup_verification_detects_changed_raw_bytes(self):
        self.ready(); self.ingest(); backup = self.root / "corrupt.sqlite"; self.store.backup(backup)
        with sqlite3.connect(backup) as db:
            db.execute("DROP TRIGGER immutable_blob_update")
            db.execute("UPDATE evidence_blobs SET body=?", (b"corrupt",))
        with self.assertRaises(ValueError): verify_database(backup)

    def test_backup_verification_detects_observation_rebinding(self):
        self.ready(); self.ingest()
        self.ingest([{"record_id": "one", "facts": {"title": "Changed"}}], at=LATER)
        backup = self.root / "rebound.sqlite"; self.store.backup(backup)
        with sqlite3.connect(backup) as db:
            db.execute("DROP TRIGGER immutable_observation_update")
            sha = db.execute("SELECT input_sha256 FROM observations ORDER BY imported_at LIMIT 1").fetchone()[0]
            db.execute("UPDATE observations SET input_sha256=?", (sha,))
        with self.assertRaises(ValueError): verify_database(backup)

    def test_readonly_verify_does_not_create_database(self):
        nonexistent = self.root / "missing.sqlite"
        with self.assertRaises(sqlite3.OperationalError): verify_database(nonexistent)
        self.assertFalse(nonexistent.exists())

    def test_lease_elapsed_during_local_parse_cannot_commit(self):
        self.ready()
        times = iter([NOW, after(NOW, self.c.lease_seconds)])
        result = OfflineScheduler(self.store, clock=lambda: next(times)).run_one("fixture")
        self.assertEqual(result["status"], "LEASE_LOST")
        self.assertEqual(self.count("records"), 0)

    def test_health_never_exposes_local_path_or_lease_token(self):
        self.ready(); self.store.claim("fixture", at=NOW)
        source = self.store.health(at=NOW)["sources"][0]
        self.assertNotIn("input_path", source)
        self.assertNotIn("lease_token", source)
        self.assertFalse(source["production_enabled"])

    def test_halifax_bridge_preserves_historical_context(self):
        c, batch = prepare_review_collection(build_pinned_collection("ui_observed"), generated_at=NOW)
        self.assertEqual(c.origin, "LOCAL_REVIEW_PACKET")
        self.assertFalse(c.production_enabled)
        self.assertEqual(batch.records[0].event_date, "2023-08-03")
        self.assertIsNone(batch.records[0].source_observed_at)
        self.assertEqual(batch.records[0].facts["_evidence_class"], "UI_OBSERVED_NOT_API_VERIFIED")
        self.assertFalse(batch.records[0].facts["_lead_promotion_allowed"])
        batch.validate(c)

    def test_halifax_bridge_rejects_relabelled_sample(self):
        sample = build_pinned_collection("ui_observed")
        sample["records"][0]["Permit_Number"] = "changed"
        with self.assertRaises(ValueError): prepare_review_collection(sample, generated_at=NOW)

    def test_halifax_invented_stays_invented(self):
        c, batch = prepare_review_collection(build_pinned_collection("invented"), generated_at=NOW)
        self.assertEqual(c.origin, "INVENTED_FIXTURE")
        batch.validate(c)

    def test_nl_fixture_stays_invented(self):
        c, batch = prepare_review_collection(build_fixture_collection((Path(__file__).parent / "fixtures/nl_environmental_assessments/synthetic-projects.html").read_bytes(), ["009901"]), generated_at=NOW)
        self.assertEqual(c.origin, "INVENTED_FIXTURE")
        self.assertIn("not authorized", c.license_name)
        batch.validate(c)


if __name__ == "__main__":
    unittest.main()
