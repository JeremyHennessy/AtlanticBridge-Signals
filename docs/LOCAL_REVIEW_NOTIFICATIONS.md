# Local review notification staging (unpublished candidate)

This is an **offline private review journal**, not a notification service. There is
no recipient, destination, transport, sender, delivery retry, background scheduler,
production enrollment, public alert or lead promotion. Creating a plan is inert.
Only an explicit `stage` invocation creates local historical review packets.
This staging slice remains local and unpublished. Its foundation is published as
draft PR #126; neither slice is deployed.

## Explicit local commands

Use a private directory and a separate journal file, never the research or
foundation database. Existing files and sidecars must be owned by the operator,
owner-only, regular, and singly linked. Opening/inspection never initializes a
missing journal. `init` and `backup` refuse existing destinations, including links.

```sh
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite init
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite register \
  --foundation private/foundation.sqlite --plan-id local-review-v1 \
  --source fixture --since 2026-11-06T00:00:00Z
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite stage \
  --foundation private/foundation.sqlite --plan-id local-review-v1 \
  --at 2026-11-08T12:00:00Z --max-scan 100
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite inspect
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite verify
python -m atlanticbridge.automation.review_notifications --journal private/review.sqlite backup \
  --destination private/review-backup.sqlite
```

The source IDs must already exist in the foundation. Registration pins their exact
contract IDs, explicit UTC `since` time and fixed `LOCAL_REVIEW_PREVIEW_ONLY` mode.
Re-registering identical configuration is idempotent. Changes require a new plan
ID. Plans accept 1–100 unique source IDs and have no delivery configuration.
The foundation stays read-only and its schema remains version 2. The journal uses
its own version 1 schema, owner-only files, WAL, FULL synchronous commits,
foreign keys, append-only triggers and atomic passes.

## Historical semantics and private payloads

A source baseline creates no event and therefore no packet. Existing foundation
observation semantics are preserved: replay or a return to an already known
version does not create another event. Staging does not reinterpret records or
invent business events. Packets say that they are historical local review
observations, may now be superseded, and are not verified business or lead events.

Packets include source and contract IDs, record/work-item/version/event IDs,
observation kind, import time separately from original event/published dates,
origin, coverage and declared attribution/licence. Invented fixtures remain
invented. All production/public-alert/lead/delivery flags remain false. Analyst
notes, status, due dates, source URLs, file paths, raw evidence and arbitrary fact
fields are excluded. Declared licence metadata may itself contain URLs. IDs and
metadata are still private, **not safe for public distribution**. A declared
licence is not verified permission to distribute or reuse the data.

## Cursor, consistency and restoration

Every pass opens the foundation read-only and copies its committed WAL-aware
SQLite snapshot into memory. Semantic verification and event selection use that
same snapshot. The foundation and sidecars are not permission-changed. The journal
holds one immediate write transaction across verification and insertion so concurrent
calls serialize. Packets, the pass record and its cursor commit together or not at
all. Unique plan/event and plan/event-sequence constraints prevent duplicate
staging. Inspection and journal verification also consume a consistent snapshot.

The global evidence-event rowid cursor advances over selected and filtered rows.
Import timestamps only filter; they are never the cursor. Later appends with
older valid import times are not silently lost. `has_more` describes additional
rows in the captured snapshot, not future appends. Stage time must be nondecreasing,
and scanned events may not have import times later than that stage time.

Each cursor retains its sequence, event-ID anchor and a hash of the entire consumed
global event prefix. Older or inconsistent source snapshots, changed pins and
missing/changed anchors fail closed. Rowids are internal to this immutable schema,
not portable identifiers promised across arbitrary VACUUM, schema rebuilds or
manual history edits. Never reset/reuse an abandoned cursor automatically. A
reviewed resync requires diagnosing the history mismatch, preserving the old
journal, and explicitly choosing a new plan/journal with reviewed sources and
`since` scope. A new plan has its own dedup namespace and can intentionally restage
observations; it is not a continuation pretending nothing happened.

`max_scan` (1–1000) bounds newly examined event rows per pass. It does **not** bound
total runtime or memory: SQLite copies and verifies all foundation history and
checks the consumed prefix. This local prototype makes no production scalability
claim. Large histories need a separately reviewed design.

Journal backup uses SQLite backup, retains committed WAL pages, verifies the
snapshot and refuses overwrite. Failed partial artifacts remain for inspection.
Restoring a journal backup preserves its recorded cursors and dedup constraints;
passes committed after that backup are naturally absent and can be staged again
within the restored history. No restoration can imply that anything was delivered.
Hashes and semantic checks detect corruption, not privileged tampering, authenticity
or signatures. Someone able to rewrite the database and all corresponding hashes
can forge history. Filesystem checks follow the foundation's existing private-file
model and are not a defense against a hostile local process racing file replacement.

## Integration gates

Before any remote integration: independent code review, full offline regression
checks and review of CI/workflow side effects. Foundation draft PR 126 remains
blocked where merging could trigger the previously denied archive probe. This
slice does not bypass that gate and has not run probes or live collectors.

External notifications would need a separate design and authorization covering
recipients, data/rights review, transport, secrets, privacy, delivery receipts,
idempotency, failure/retry handling and activation. This module intentionally offers
none of those controls and cannot be enabled into a live service by a flag.
