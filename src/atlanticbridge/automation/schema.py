"""Separate local database, not a migration of the historical research database."""
VERSION = 2
SCHEMA = """
CREATE TABLE foundation_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE contracts (
    contract_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL, UNIQUE(source_id, contract_id)
);
CREATE TABLE sources (
    source_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL REFERENCES contracts,
    state TEXT NOT NULL CHECK(state IN ('PAUSED','READY','QUARANTINED')),
    next_due_at TEXT NOT NULL, input_path TEXT,
    baseline_complete INTEGER NOT NULL DEFAULT 0 CHECK(baseline_complete IN (0,1)),
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT, last_success_at TEXT, last_error_code TEXT,
    last_input_sha256 TEXT, lease_token TEXT, lease_until TEXT,
    FOREIGN KEY(source_id, contract_id) REFERENCES contracts(source_id, contract_id)
);
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources,
    contract_id TEXT NOT NULL REFERENCES contracts, started_at TEXT NOT NULL,
    lease_until TEXT NOT NULL, finished_at TEXT,
    outcome TEXT NOT NULL CHECK(outcome IN ('RUNNING','SUCCESS','TRANSIENT_FAILURE','QUARANTINED','LEASE_EXPIRED')),
    error_code TEXT, record_count INTEGER,
    input_sha256 TEXT REFERENCES evidence_blobs(sha256),
    CHECK((outcome='RUNNING' AND finished_at IS NULL AND error_code IS NULL AND record_count IS NULL AND input_sha256 IS NULL)
       OR (outcome='SUCCESS' AND finished_at IS NOT NULL AND error_code IS NULL AND record_count >= 0 AND record_count IS NOT NULL AND input_sha256 IS NOT NULL)
       OR (outcome IN ('TRANSIENT_FAILURE','QUARANTINED','LEASE_EXPIRED') AND finished_at IS NOT NULL AND error_code IS NOT NULL AND record_count IS NULL AND input_sha256 IS NULL))
);
CREATE TABLE evidence_blobs (
    sha256 TEXT PRIMARY KEY, body BLOB NOT NULL, byte_count INTEGER NOT NULL,
    evidence_kind TEXT NOT NULL CHECK(evidence_kind='LOCAL_NORMALIZED_PACKET_NOT_RAW_SOURCE_RESPONSE'),
    created_at TEXT NOT NULL
);
CREATE TABLE records (
    source_id TEXT NOT NULL REFERENCES sources, record_id TEXT NOT NULL,
    first_imported_at TEXT NOT NULL, last_imported_at TEXT NOT NULL,
    current_version_id TEXT NOT NULL, PRIMARY KEY(source_id, record_id),
    FOREIGN KEY(current_version_id) REFERENCES record_versions(version_id) DEFERRABLE INITIALLY DEFERRED
);
CREATE TABLE record_versions (
    version_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, record_id TEXT NOT NULL,
    contract_id TEXT NOT NULL REFERENCES contracts,
    content_sha256 TEXT NOT NULL, content_json TEXT NOT NULL,
    origin TEXT NOT NULL CHECK(origin IN ('LOCAL_REVIEW_PACKET','INVENTED_FIXTURE')),
    first_imported_at TEXT NOT NULL,
    FOREIGN KEY(source_id, record_id) REFERENCES records(source_id, record_id),
    UNIQUE(source_id, record_id, contract_id, content_sha256)
);
CREATE TABLE observations (
    run_id TEXT NOT NULL REFERENCES runs, version_id TEXT NOT NULL REFERENCES record_versions,
    input_sha256 TEXT NOT NULL REFERENCES evidence_blobs, imported_at TEXT NOT NULL,
    source_observed_at TEXT, PRIMARY KEY(run_id, version_id)
);
CREATE TABLE evidence_events (
    event_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, record_id TEXT NOT NULL,
    from_version_id TEXT REFERENCES record_versions, to_version_id TEXT NOT NULL REFERENCES record_versions,
    kind TEXT NOT NULL CHECK(kind IN ('RECORD_FIRST_OBSERVED','RECORD_CONTENT_CHANGED')),
    imported_at TEXT NOT NULL, event_date TEXT, published_date TEXT,
    public_alert_allowed INTEGER NOT NULL DEFAULT 0 CHECK(public_alert_allowed=0),
    FOREIGN KEY(source_id, record_id) REFERENCES records(source_id, record_id)
);
CREATE TABLE assessments (
    version_id TEXT PRIMARY KEY REFERENCES record_versions,
    disposition TEXT NOT NULL CHECK(disposition='CONTEXT_ONLY'),
    reason TEXT NOT NULL, lead_eligible INTEGER NOT NULL DEFAULT 0 CHECK(lead_eligible=0)
);
CREATE TABLE entities (
    entity_id TEXT PRIMARY KEY, legal_name TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE entity_identities (
    scheme TEXT NOT NULL, identifier TEXT NOT NULL, entity_id TEXT NOT NULL REFERENCES entities,
    supporting_version_id TEXT NOT NULL REFERENCES record_versions,
    reviewed_by TEXT NOT NULL, reviewed_at TEXT NOT NULL, PRIMARY KEY(scheme, identifier)
);
CREATE TABLE work_items (
    item_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, record_id TEXT NOT NULL,
    latest_version_id TEXT NOT NULL REFERENCES record_versions,
    status TEXT NOT NULL CHECK(status IN ('TRIAGE','ACTIVE','HOLD','DONE')),
    needs_review INTEGER NOT NULL CHECK(needs_review IN (0,1)),
    notes TEXT NOT NULL DEFAULT '', due_date TEXT, revision INTEGER NOT NULL,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    FOREIGN KEY(source_id, record_id) REFERENCES records(source_id, record_id),
    UNIQUE(source_id, record_id)
);
CREATE TABLE audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT, object_type TEXT NOT NULL,
    object_id TEXT NOT NULL, action TEXT NOT NULL, actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL, details_json TEXT NOT NULL
);
CREATE INDEX runs_by_source_time ON runs(source_id, started_at);
CREATE INDEX records_by_current_version ON records(current_version_id);
CREATE INDEX work_by_status_due ON work_items(status, due_date);
CREATE INDEX observations_by_version ON observations(version_id);
CREATE INDEX events_by_record ON evidence_events(source_id, record_id);
CREATE TRIGGER immutable_blob_update BEFORE UPDATE ON evidence_blobs BEGIN SELECT RAISE(ABORT,'Evidence is immutable'); END;
CREATE TRIGGER immutable_blob_delete BEFORE DELETE ON evidence_blobs BEGIN SELECT RAISE(ABORT,'Evidence is immutable'); END;
CREATE TRIGGER immutable_version_update BEFORE UPDATE ON record_versions BEGIN SELECT RAISE(ABORT,'Version is immutable'); END;
CREATE TRIGGER immutable_version_delete BEFORE DELETE ON record_versions BEGIN SELECT RAISE(ABORT,'Version is immutable'); END;
CREATE TRIGGER immutable_audit_update BEFORE UPDATE ON audit_log BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
CREATE TRIGGER immutable_audit_delete BEFORE DELETE ON audit_log BEGIN SELECT RAISE(ABORT,'Audit is append only'); END;
CREATE TRIGGER immutable_observation_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'Observation is immutable'); END;
CREATE TRIGGER immutable_observation_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'Observation is immutable'); END;
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON evidence_events BEGIN SELECT RAISE(ABORT,'Event is immutable'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON evidence_events BEGIN SELECT RAISE(ABORT,'Event is immutable'); END;
CREATE TRIGGER immutable_contract_update BEFORE UPDATE ON contracts BEGIN SELECT RAISE(ABORT,'Contract is immutable'); END;
CREATE TRIGGER immutable_contract_delete BEFORE DELETE ON contracts BEGIN SELECT RAISE(ABORT,'Contract is immutable'); END;
"""
