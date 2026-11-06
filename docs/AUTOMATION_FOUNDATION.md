# Durable local automation foundation

## Status and boundary

This is a **local-only preparation layer**, added independently to the version 8 reliability workspace. It is not deployed, not connected to the public UI, not an unattended live-source service, and not a notification system. No source transport, background timer, GitHub Actions schedule, authenticated API, account, external credential, new paid service, or external delivery is introduced.

The existing historical database remains unchanged. Use a separate SQLite database with `python -m atlanticbridge.automation --db <local-path> init`.

All contracts reject network access methods, live origins and production enablement. Every new source is paused until an explicit local resume. The only scheduler input is a bounded regular local file. Existing federal grants and Nova Scotia restrictions remain in force. NL remains an invented fixture. The Halifax sample remains an observed historical permit, not an API-verified/live event. No source is activated by this package.

## Implemented data path

1. Pin an immutable source contract: source identity, parser version, allowed fields, declared licence/attribution, exact coverage/origin, input bounds, cadence, lease and retry policy.
2. Independently claim a source due for a local import. Claims are transactional and have persistent lease identities.
3. Read a bounded local normalized JSON packet. Validate exact schema, source/origin/coverage, dates, URLs, unique source record IDs, JSON types and field allowlists.
4. Atomically retain exact normalized input bytes and their SHA-256, immutable content versions, separate import and source-observation clocks, conservative observation events, context-only assessments and persistent work items.
5. Commit source health and checkpoint only with accepted evidence. Failed or expired work cannot erase a previous success.
6. Persist analyst edits with optimistic revision checking and an append-only audit. New evidence flags existing work for review while preserving status, notes and due date. If a changed-evidence completion timestamp predates a concurrent analyst save, the entire import is rejected without moving the work clock backward. A caller may retry the same live lease with a fresh timestamp.
7. Snapshot using SQLite's backup API and verify SQLite integrity, foreign keys, retained content hashes, accepted-run record counts, checkpoints, current versions and work/audit consistency before reporting success.

This removes fragile in-memory persistence **for callers of the new local API/CLI**. It does not yet replace the standalone browser's manual import/backup workflow.

## Schema and semantics

- `contracts` is immutable. Registration is idempotent only for the same contract and exact input path. Contract/path changes need a separately named source at this stage; there is no implicit schema migration.
- `sources` owns independent schedule, failure, lease, baseline and last-success state. Pausing a quarantined source preserves `QUARANTINED`; resuming still requires an explicit review reason. The returned state is reported by the CLI.
- `runs` separates attempted import, success, transient failure, quarantine and expired lease.
- `evidence_blobs` stores bounded local normalized packet bytes, explicitly **not raw source responses**. No invented proof of original-source retrieval is added.
- `records` holds the current pointer by `(source_id, record_id)`.
- `record_versions` is content-addressed by source, record, contract and normalized content. Retrieval-only clock differences do not become changed facts.
- `observations` associates each accepted run/version with retained input bytes, import time and optional source observation time.
- `evidence_events` distinguishes first local observation from changed content. These are review events, never verified business events. Initial enrollment, repeats and reappearance of an already-seen version emit no new event. A previous version's reappearance still changes the work item's current evidence and flags review. No absence/deletion/cancellation is inferred from a missing row.
- `assessments` cannot promote any version beyond context-only; `lead_eligible` remains false.
- `work_items` is one durable review item per source record. Status, notes and due dates are separate from source facts. An update must carry the expected revision. A closed item with changed evidence remains closed but is explicitly flagged for review.
- `audit_log` keeps source enrollment/state/failure/import and before/after analyst-edit history.
- `entities` and `entity_identities` are **reserved schema**, not an implemented resolver. There is no fuzzy-name merge, parent inference, identity claim or automatic entity linking.

Source licence strings are declared metadata, not newly verified usage permission. Generic local packet import is not a way to upgrade a fixture or gain production reuse rights. The review-collection bridge delegates existing Halifax/NL pin validation to `build_review_packet`, retains the original evidence class and interpretation boundaries, and keeps the fixture origin. Protected source IDs and identifiable provenance are additionally checked at contract registration, normalized decoding, direct store completion and backup verification. Canonical contracts and semantic records are regenerated from the existing hash-checked bundled pins, not from caller-supplied metadata. Changing a headline, origin, date, rights statement, interpretation, source identity or lead flag cannot retain protected attribution. Generic source aliases containing identifiable protected provenance are rejected.

## Source isolation and timeouts

`OfflineScheduler.run_due()` is one explicit bounded pass. It does not install or run an unattended schedule. It reads only ordinary local files with byte/record limits and refuses special files and final-component symlinks. One source's parse/permission failure is quarantined while unrelated sources continue. Missing local files use exponential backoff, capped delays and a finite failure count. Permissions, schema errors and unexpected failures are not retried automatically. `tick-local` exits with status 1 when any attempted source fails, loses its lease or has an expired lease recovered, while still reporting successful independent sources. Nothing due and all-success ticks exit with status 0.

An expired lease is fenced: stale results cannot commit. A later tick records its failure and schedules backoff. Lease ownership is enforced across separate SQLite connections. Leases are a recovery protocol, **not a hard CPU interrupt**. A future live adapter must have its own bounded I/O deadline and independently supervised execution. This foundation contains no arbitrary collector callback and no network worker.

Health says `UNVERIFIED_LOCAL_IMPORT_ONLY`. A recent successful import is not a fresh source observation. `last_success_at` means local acceptance, not a newly published permit/award/operation. The public 14-day production reliability requirement has not been met by these local tests.

## Local operation

Run with `PYTHONPATH=src` from the checkout; no new dependency is required.

```sh
mkdir -m 700 .atlantic-private
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite init
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite register \
  --contract local-contract.json --input local-input.json
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite resume-local \
  --source example_source --actor operator
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite tick-local
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite health
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite work-items
python -m atlanticbridge.automation --db .atlantic-private/work.sqlite backup \
  --output .atlantic-private/work-backup.sqlite
python -m atlanticbridge.automation --db .atlantic-private/work-backup.sqlite verify
```

`save-work-item` supports `--item`, `--revision`, `--status`, `--notes-file`, `--due-date`, `--needs-review` and `--actor`. A due date is only stored planning metadata, not a sent reminder. Notes, paths and evidence are private local data; do not commit them to a public branch or expose the database on a public web server.

The Python bridge `prepare_review_collection(collection, generated_at=...)` returns a validated contract and batch from one existing source collection without modifying storage. `Store.register()` starts paused. `Store.claim()` and `Store.complete()` allow accepted batches to be durably ingested. The returned normalized bytes can be saved to the pinned local file for later local ticks. The original collected packet should also be retained separately if its broader collection metadata is needed.

## Backup, recovery and security

- Backups refuse to overwrite any existing destination and use SQLite's consistent snapshot operation, including committed WAL data.
- `verify` opens read-only and validates database integrity, hashes and semantic links. Every successful run must refer to retained input bytes, the exact parsed record count and matching observations. It checks empty successes, source checkpoints, active leases, non-null current/latest pointers, preserved review-event semantics and matching work-item audit revisions with nondecreasing per-item audit timestamps. For a recovery exercise, verify the backup, then open it as a **new** local database. The package never overwrites an existing database.
- A partially written backup is preserved on failure rather than silently discarded. A failed verification is not a successful backup.
- Content hashes and immutable SQL triggers detect accidental corruption and block normal API mutation. They are not encryption, a signature, remote authentication, tamper-proof storage or protection from a privileged local database editor.
- New primary databases and backup files are created owner-only (0600). SQLite WAL/SHM/journal files inherit that mode and are checked before writes. Existing files with broader permissions, symlinks, hard links or another owner are rejected, not silently chmodded. `.gitignore` excludes SQLite database/sidecar patterns and `.atlantic-private/`; put packet files, notes and other operator material in that directory too. These ignore rules do not untrack previously committed files.
- Store the database in a private user directory. Local source registration and actor labels assume one trusted operator, not multiple authenticated users. This reviewed revision uses schema version 2. Version 1 databases are deliberately rejected rather than silently migrated, and the original source/package remains available. There was no production database to migrate. Do not discard any older operator data; preserve its verified backup and reconcile it explicitly before moving to schema 2. A migration tool has not been implemented.
- No retention purge is implemented. Evidence and audit bytes grow with imported data; measure size and define approved retention before production.

## Next integration gates

1. Obtain independent re-review of this corrected revision and apply its isolated patch after the production release reconciliation. No baseline files or workflows need replacement.
2. Select an authorized persistent host and operator authentication model. GitHub Pages cannot by itself provide private server-side writes. Introduce no new credentials, access grants or costs without the applicable authorization.
3. Integrate current approved collectors through separately reviewed source contracts. Preserve original permitted raw evidence externally with hashes, while distinguishing raw response, normalized packet and derived interpretation.
4. Connect the UI to authenticated evidence/work APIs, enforce per-user access, and test concurrent editors and restoration. Static in-browser notes must not silently become public state.
5. Add independent source execution deadlines, approved schedules, live health and complete archive reconciliation. Verify exact deployment and browser behavior.
6. Add an inert subscription/outbox design, then authorized delivery adapters with persistent deduplication, retries, recipients and approved content. There is currently **no delivery table or sender** and no automatic external outreach.
7. Exercise unattended reliability for the approved cohort, retain last-good data during outages, and only then expand sources. Prediction publication remains blocked.

## Verification

`tests/test_automation_foundation.py` and `tests/test_automation_review_fixes.py` cover paused enrollment, strict contracts and JSON, baseline/replay semantics, source namespace separation, date preservation, no absence inference, atomic validation, input-to-record type binding, lease fencing/recovery, two-connection claims, conservative retry/quarantine, independent source failure, immutable retention, persistent/stale work saves, backup restoration and existing Halifax/NL boundaries.

Run the full offline Python/Node suites and the unchanged strict publication gate on the final integrated tree. Passing offline tests does not establish deployed production readiness, authentication, hard real-time timeouts, a live transport, or independent security review.

## Review remediation in revision 2

The original foundation was withheld after independent review found two high-priority bypasses and three reliability/privacy issues. This revision closes the quarantine pause/resume bypass, adds protected-source validation at the actual durable boundaries, returns failure exit status for failed ticks, validates semantic snapshot integrity and creates private database/sidecar files with ignore rules. The original package is preserved for audit, not recommended for use. The corrected candidate includes 82 focused tests, including 37 added adversarial regressions. Re-review and full integrated test results are reported separately in the delivery manifest.
