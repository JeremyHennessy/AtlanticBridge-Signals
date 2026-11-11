"""Adversarial regressions for the independent review of the local foundation."""
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from unittest.mock import patch

from atlanticbridge.automation import Batch, Record, SourceContract, Store, OfflineScheduler
from atlanticbridge.automation.__main__ import main
from atlanticbridge.automation.models import canonical, decode_batch
from atlanticbridge.automation.review_bridge import prepare_review_collection
from atlanticbridge.automation.store import after, verify_database
from atlanticbridge.sources.halifax_building_permits import build_pinned_collection
from atlanticbridge.sources.nl_environmental_assessments import build_fixture_collection
from test_automation_foundation import contract, body, NOW, LATER, THIRD


class AutomationReviewFixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.db_path = self.root / "work.sqlite"
        self.store = Store(self.db_path); self.addCleanup(self.store.close)
        self.c = contract(); self.input = self.root / "input.json"; self.input.write_bytes(body(self.c))
        self.store.register(self.c, at=NOW, input_path=self.input)
        self.store.set_source_state("fixture", "READY", at=NOW, actor="test")

    def ingest(self, data=None, at=NOW):
        run = self.store.claim("fixture", at=at)
        return self.store.complete(run, decode_batch(data or body(self.c), self.c), at=at)

    def quarantine(self):
        run = self.store.claim("fixture", at=NOW)
        self.store.fail(run, at=NOW, code="PERMISSION_DENIED")

    def cli(self, *args, at=NOW):
        capture = io.StringIO()
        with patch("atlanticbridge.automation.__main__.OfflineScheduler", side_effect=lambda store: OfflineScheduler(store, clock=lambda: at)):
            with patch("atlanticbridge.automation.__main__.utc_now", return_value=at), redirect_stdout(capture):
                code = main(["--db", str(self.db_path), *args])
        return code, json.loads(capture.getvalue())

    def backup(self, name="backup.sqlite"):
        path = self.root / name; self.store.backup(path); return path

    def test_quarantine_pause_resume_cannot_clear_review(self):
        self.quarantine()
        for _ in range(2):
            self.assertEqual(self.store.set_source_state("fixture", "PAUSED", at=NOW, actor="test"), "QUARANTINED")
            with self.assertRaises(ValueError):
                self.store.set_source_state("fixture", "READY", at=NOW, actor="test")
            self.assertIsNone(self.store.claim("fixture", at=LATER))
        self.assertEqual(self.store.health(at=NOW)["sources"][0]["consecutive_failures"], 1)
        verify_database(self.backup())

    def test_pause_does_not_apply_supplied_reason_as_clearance(self):
        self.quarantine()
        self.store.set_source_state("fixture", "PAUSED", at=NOW, actor="test", review_reason="Text accompanying pause")
        with self.assertRaises(ValueError): self.store.set_source_state("fixture", "READY", at=NOW, actor="test")
        self.store.set_source_state("fixture", "READY", at=NOW, actor="reviewer", review_reason="Reviewed and corrected local file access")
        self.assertIsNotNone(self.store.claim("fixture", at=NOW))
        verify_database(self.backup())

    def test_cli_pause_reports_unresolved_quarantine(self):
        self.quarantine(); code, result = self.cli("pause", "--source", "fixture", "--actor", "test")
        self.assertEqual(code, 0); self.assertEqual(result["state"], "QUARANTINED")

    def pinned(self, source="halifax", kind="ui_observed"):
        if source == "halifax": collection = build_pinned_collection(kind)
        else:
            fixture = Path(__file__).parent / "fixtures/nl_environmental_assessments/synthetic-projects.html"
            collection = build_fixture_collection(fixture.read_bytes(), ["009901"])
        return prepare_review_collection(collection, generated_at=NOW)

    def test_protected_contract_changes_cannot_be_registered(self):
        c, _ = self.pinned()
        for changed in (replace(c, attribution="Different rights"),
                        replace(c, coverage="COMPLETE"), replace(c, parser_version="new"),
                        replace(c, allowed_fields=tuple(x for x in c.allowed_fields if x != "_interpretation_limit"))):
            with self.subTest(changed=changed), self.assertRaises(ValueError): self.store.register(changed, at=NOW)

    def test_protected_id_relabeling_cannot_be_registered(self):
        for source in ("halifax", "nl"):
            c, _ = self.pinned(source)
            with self.subTest(source=source), self.assertRaises(ValueError): self.store.register(replace(c, source_id="unrelated"), at=NOW)

    def test_halifax_normalized_fields_are_revalidated_on_decode(self):
        c, batch = self.pinned()
        for field, value in (("_headline", "Forged headline"), ("_evidence_class", "LIVE_VERIFIED"),
                             ("_interpretation_limit", "Construction completed"), ("_lead_promotion_allowed", True),
                             ("_lead_promotion_allowed", 0), ("currency", "CAD"), ("estimated project value", 1)):
            raw = json.loads(batch.input_bytes); raw["records"][0]["facts"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), c)

    def test_halifax_dates_and_source_observation_cannot_be_rewritten(self):
        c, batch = self.pinned()
        for field, value in (("event_date", "2026-11-06"), ("published_date", "2026-11-06"),
                             ("source_observed_at", NOW), ("record_id", "BPCOM-2026-99999"),
                             ("source_url", "https://example.org/relabelled")):
            raw = json.loads(batch.input_bytes); raw["records"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), c)

    def test_halifax_observed_record_cannot_relabel_as_invented_variant(self):
        _, observed = self.pinned(); invented_contract, _ = self.pinned(kind="invented")
        raw = json.loads(observed.input_bytes); raw["origin"] = "INVENTED_FIXTURE"
        with self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), invented_contract)

    def test_failure_completion_prevents_backdated_pause_and_claim(self):
        run = self.store.claim("fixture", at=NOW)
        self.store.fail(run, at=after(NOW, 30), code="LOCAL_INPUT_UNAVAILABLE", transient=True)
        with self.assertRaises(ValueError): self.store.set_source_state("fixture", "PAUSED", at=after(NOW, 10), actor="test")
        with self.assertRaises(ValueError): self.store.claim("fixture", at=after(NOW, 10))

    def test_nl_normalized_fixture_facts_and_origin_stay_pinned(self):
        c, batch = self.pinned("nl")
        for field, value in (("_headline", "Real investment"), ("_interpretation_limit", "Operations started"),
                             ("_lead_promotion_allowed", True), ("_evidence_class", "UI_OBSERVED_NOT_API_VERIFIED")):
            raw = json.loads(batch.input_bytes); raw["records"][0]["facts"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), c)
        with self.assertRaises(ValueError):
            self.store.register(replace(c, origin="LOCAL_REVIEW_PACKET"), at=NOW)

    def test_direct_complete_revalidates_protected_batch_even_with_recomputed_hash(self):
        c, batch = self.pinned(); self.store.register(c, at=NOW)
        self.store.set_source_state(c.source_id, "READY", at=NOW, actor="test")
        run = self.store.claim(c.source_id, at=NOW)
        raw = json.loads(batch.input_bytes); raw["records"][0]["facts"]["_headline"] = "FORGED"
        wire = canonical(raw).encode()
        forged = Batch(c.source_id, c.origin, tuple(Record(**row) for row in raw["records"]), c.coverage,
                       hashlib.sha256(wire).hexdigest(), wire)
        with self.assertRaises(ValueError): self.store.complete(run, forged, at=NOW)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM records").fetchone()[0], 0)

    def test_scheduler_quarantines_modified_protected_packet(self):
        c, batch = self.pinned(); path = self.root / "halifax.json"
        raw = json.loads(batch.input_bytes); raw["records"][0]["facts"]["_headline"] = "FORGED"
        path.write_bytes(canonical(raw).encode()); self.store.register(c, at=NOW, input_path=path)
        self.store.set_source_state(c.source_id, "READY", at=NOW, actor="test")
        result = OfflineScheduler(self.store, clock=lambda: NOW).run_one(c.source_id)
        self.assertEqual(result["error_code"], "SCHEMA_INVALID")
        self.assertEqual(self.store.db.execute("SELECT state FROM sources WHERE source_id=?", (c.source_id,)).fetchone()[0], "QUARANTINED")

    def test_identifiable_protected_records_cannot_use_generic_contract(self):
        for source in ("halifax", "nl"):
            protected, batch = self.pinned(source)
            generic = contract("alias", allowed_fields=list(protected.allowed_fields), origin=protected.origin)
            raw = json.loads(batch.input_bytes); raw.update(source_id=generic.source_id, coverage=generic.coverage)
            with self.subTest(source=source), self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), generic)

    def test_pinned_rows_survive_store_backup_and_restore_verification(self):
        for source in ("halifax", "nl"):
            c, batch = self.pinned(source); self.store.register(c, at=NOW)
            self.store.set_source_state(c.source_id, "READY", at=NOW, actor="test")
            run = self.store.claim(c.source_id, at=NOW); self.store.complete(run, batch, at=NOW)
        self.assertEqual(verify_database(self.backup())["work_items"], 2)

    def test_empty_protected_packet_cannot_claim_valid_current_collection(self):
        c, batch = self.pinned(); raw = json.loads(batch.input_bytes); raw["records"] = []
        with self.assertRaises(ValueError): decode_batch(canonical(raw).encode(), c)

    def test_cli_failure_exits_nonzero_and_preserves_other_source_success(self):
        self.input.write_bytes(b"invalid JSON")
        good = contract("good"); path = self.root / "good.json"; path.write_bytes(body(good))
        self.store.register(good, at=NOW, input_path=path); self.store.set_source_state("good", "READY", at=NOW, actor="test")
        code, result = self.cli("tick-local")
        self.assertEqual(code, 1); self.assertEqual([r["status"] for r in result], ["FAILED", "SUCCESS"])
        self.assertEqual(self.store.work_items()[0]["source_id"], "good")

    def test_cli_expired_lease_exits_nonzero(self):
        self.store.claim("fixture", at=NOW)
        code, result = self.cli("tick-local", at=after(NOW, self.c.lease_seconds))
        self.assertEqual(code, 1); self.assertEqual(result[0]["error_code"], "LEASE_EXPIRED")

    def test_cli_success_and_nothing_due_exit_zero(self):
        self.assertEqual(self.cli("tick-local")[0], 0)
        self.assertEqual(self.cli("tick-local"), (0, []))

    def test_successful_run_with_nonexistent_blob_is_rejected(self):
        self.ingest(); path = self.backup()
        with sqlite3.connect(path) as db: db.execute("UPDATE runs SET input_sha256=?", ("f" * 64,))
        with self.assertRaises(ValueError): verify_database(path)

    def test_successful_run_with_absurd_record_count_is_rejected(self):
        self.ingest(); path = self.backup()
        with sqlite3.connect(path) as db: db.execute("UPDATE runs SET record_count=999999")
        with self.assertRaises(ValueError): verify_database(path)

    def test_empty_success_run_retains_and_verifies_its_blob(self):
        self.ingest(body(self.c, [])); self.assertEqual(verify_database(self.backup())["work_items"], 0)

    def test_current_version_cannot_be_null_under_v2_schema(self):
        self.ingest()
        with self.assertRaises(sqlite3.IntegrityError): self.store.db.execute("UPDATE records SET current_version_id=NULL")

    def test_current_version_cannot_point_to_an_older_same_record_version(self):
        self.ingest(); old = self.store.work_items()[0]["latest_version_id"]
        self.ingest(body(self.c, [{"record_id": "one", "facts": {"title": "Changed"}}]), at=LATER)
        path = self.backup()
        with sqlite3.connect(path) as db: db.execute("UPDATE records SET current_version_id=?", (old,))
        with self.assertRaises(ValueError): verify_database(path)

    def test_missing_accepted_observation_is_rejected(self):
        self.ingest(); path = self.backup()
        with sqlite3.connect(path) as db:
            db.execute("DROP TRIGGER immutable_observation_delete"); db.execute("DELETE FROM observations")
        with self.assertRaises(ValueError): verify_database(path)

    def test_source_success_checkpoint_cannot_be_forged(self):
        self.ingest(); path = self.backup()
        with sqlite3.connect(path) as db: db.execute("UPDATE sources SET last_success_at=?", (LATER,))
        with self.assertRaises(ValueError): verify_database(path)

    def test_observation_cannot_be_reassigned_to_failed_run(self):
        self.ingest(); run = self.store.claim("fixture", at=LATER); self.store.fail(run, at=LATER, code="SCHEMA_INVALID")
        path = self.backup()
        with sqlite3.connect(path) as db:
            db.execute("DROP TRIGGER immutable_observation_update"); db.execute("UPDATE observations SET run_id=?", (run,))
        with self.assertRaises(ValueError): verify_database(path)

    def test_work_pointer_and_audit_revision_are_verified(self):
        self.ingest(); path = self.backup()
        with sqlite3.connect(path) as db: db.execute("UPDATE work_items SET revision=50")
        with self.assertRaises(ValueError): verify_database(path)

    def test_pending_lease_and_quarantine_are_valid_backup_states(self):
        run = self.store.claim("fixture", at=NOW); verify_database(self.backup("pending.sqlite"))
        self.store.fail(run, at=NOW, code="SCHEMA_INVALID"); verify_database(self.backup("quarantine.sqlite"))

    def test_reappearance_and_empty_batch_history_verify(self):
        self.ingest(); self.ingest(body(self.c, [{"record_id": "one", "facts": {"title": "Changed"}}]), at=LATER)
        self.ingest(at=THIRD); self.ingest(body(self.c, []), at=after(THIRD, 86400))
        self.assertEqual(verify_database(self.backup())["work_items"], 1)

    def test_primary_database_and_sqlite_sidecars_are_owner_only(self):
        self.ingest()
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.db_path) + suffix)
            self.assertTrue(path.exists(), suffix)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.backup().stat().st_mode), 0o600)

    def test_insecure_existing_primary_is_rejected_without_chmod(self):
        os.chmod(self.db_path, 0o644)
        try:
            with self.assertRaises(ValueError): Store(self.db_path)
            self.assertEqual(stat.S_IMODE(self.db_path.stat().st_mode), 0o644)
        finally: os.chmod(self.db_path, 0o600)

    def test_insecure_existing_sidecar_is_rejected_without_chmod(self):
        self.ingest(); wal = Path(str(self.db_path) + "-wal"); os.chmod(wal, 0o644)
        try:
            with self.assertRaises(ValueError): Store(self.db_path)
            self.assertEqual(stat.S_IMODE(wal.stat().st_mode), 0o644)
        finally: os.chmod(wal, 0o600)

    def test_database_symlink_and_hardlink_are_rejected(self):
        link = self.root / "linked.sqlite"; link.symlink_to(self.db_path)
        with self.assertRaises(ValueError): Store(link)
        hard = self.root / "hard.sqlite"; os.link(self.db_path, hard)
        try:
            with self.assertRaises(ValueError): Store(hard)
        finally: hard.unlink()

    def test_late_completion_cannot_rewind_a_concurrent_analyst_save(self):
        self.ingest(); item = self.store.work_items()[0]
        run = self.store.claim("fixture", at=LATER)
        self.store.update_work_item(item["item_id"], expected_revision=1, status="HOLD", notes="Saved while import was validating",
            due_date="2026-11-09", needs_review=False, at=after(LATER, 30), actor="analyst")
        changed = decode_batch(body(self.c, [{"record_id": "one", "facts": {"title": "Changed"}}]), self.c)
        with self.assertRaises(ValueError): self.store.complete(run, changed, at=after(LATER, 10))
        after_rejection = self.store.work_items()[0]
        self.assertEqual(after_rejection["updated_at"], after(LATER, 30))
        self.assertEqual(after_rejection["revision"], 2)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM record_versions").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM evidence_blobs").fetchone()[0], 1)
        self.assertEqual(self.store.db.execute("SELECT outcome FROM runs WHERE run_id=?", (run,)).fetchone()[0], "RUNNING")
        self.store.complete(run, changed, at=after(LATER, 31))
        updated = self.store.work_items()[0]
        self.assertEqual((updated["updated_at"], updated["status"], updated["notes"], updated["revision"]),
                         (after(LATER, 31), "HOLD", "Saved while import was validating", 3))
        verify_database(self.backup())

    def test_backup_rejects_work_audit_chronology_rewind(self):
        self.ingest(); item = self.store.work_items()[0]
        self.store.update_work_item(item["item_id"], expected_revision=1, status="HOLD", notes="Operator note",
            due_date=None, needs_review=False, at=after(LATER, 30), actor="analyst")
        self.ingest(body(self.c, [{"record_id": "one", "facts": {"title": "Changed"}}]), at=after(LATER, 31))
        path = self.backup()
        with sqlite3.connect(path) as db:
            db.execute("DROP TRIGGER immutable_audit_update")
            db.execute("UPDATE audit_log SET occurred_at=? WHERE object_type='work_item' AND action='EVIDENCE_UPDATED'", (after(LATER, 10),))
            db.execute("UPDATE work_items SET updated_at=?", (after(LATER, 10),))
        with self.assertRaises(ValueError): verify_database(path)

    def test_private_runtime_artifacts_are_gitignored(self):
        rules = (Path(__file__).resolve().parents[1] / ".gitignore").read_text().splitlines()
        for required in (".atlantic-private/", "*.sqlite", "*.sqlite3", "*.db", "*.sqlite-*", "*.sqlite3-*", "*.db-*"):
            self.assertIn(required, rules)

    def test_schema_v1_is_not_silently_migrated(self):
        old = self.backup();
        with sqlite3.connect(old) as db: db.execute("UPDATE foundation_meta SET value='1' WHERE key='schema_version'")
        with self.assertRaises(ValueError): Store(old)
        with self.assertRaises(ValueError): verify_database(old)


if __name__ == "__main__": unittest.main()
