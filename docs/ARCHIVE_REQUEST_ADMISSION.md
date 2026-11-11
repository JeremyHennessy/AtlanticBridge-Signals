# Durable archive admission: integrated local candidate, NOT published

This candidate integrates `scripts/archive_durable.py` into the sole executable
archive entrypoint and proposes replacing post-execution git persistence in
`.github/workflows/evidence-retention.yml`. It has not run against GitHub. The
current remote workflow is not protected by this unpublished implementation.
No source activation, workflow dispatch, credentials, remote mutation, or live
privacy request was performed. Known historical 403 remains unresolved and held.

## Concrete exact-head store

The fixed repository is JeremyHennessy/AtlanticBridge-Signals, branch
monitoring-state. GraphQL `createCommitOnBranch` uses required `expectedHeadOid`
and only allowlisted file additions. This appends a commit and updates its branch
atomically; unmentioned monitoring/checkpoint/history files remain untouched.
REST nonforce ref updates check ancestry, not exact old-head equality, and are not
used. No force push, subprocess, merge-on-conflict, fallback or retry exists.

Official references checked 2026-11-08:
- https://docs.github.com/en/graphql/reference/commits#createcommitonbranch
- https://docs.github.com/en/graphql/reference/commits#createcommitonbranchinput
- https://docs.github.com/en/graphql/reference/git#committablebranch

CommittableBranch uses `repositoryNameWithOwner` and `branchName` (not the stale
`refName` prose). A single branch-target Commit query resolves all requested
regular-file blobs consistently. Exact SHA and exact changed UTF-8 bytes are read
back independently after each mutation. Any GraphQL errors, truncated/non-blob or
symlink entries, invalid JSON, stale/mismatched head, changed bytes, denied request
or uncertain response fails closed. The authenticated transport is fixed-origin,
no-redirect, bounded and uses configured proxy routing. Diagnostics do not expose
transport bodies, credentials or signed URLs. Payloads are capped at 4 MiB raw,
five changed files; mutations are never split.

## Preflight and once-only execution

`ArchiveRun.execute` consumes its in-process execution slot before any work. It
reads authoritative admission, current owner record, manifest and prior attempt.
Missing/malformed state, clock rollback, reserved/review_hold, repeated owner or
existing manifest denies. An owner is `GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT`.
No local receipt file can restore admission. The durable run record also blocks
reusing a successful owner after its cooldown. Client construction, inventory,
draft creation, download, upload and privacy checks happen only after reservation
CAS and exact readback. The factory and work callable are trusted application
code, not sandboxed plugins.

The full 48-request budget is reserved, never refunded. The existing single-client
48 cap, serialized requests and failure latch remain unchanged. Fresh direct API
404 with exact original response URL and no redirects remains the only successful
privacy observation. No previous privacy result establishes fresh proof. The cap
is not a guarantee of shared-IP allowance or an hourly scheduler.

## Atomic finalization and acknowledgment ambiguity

Verified success writes admission ready, owner record, archive-attempt.json,
archive-health.json and a unique owner manifest in ONE exact-reservation-head CAS.
Failure writes review_hold plus safe attempt/owner records, preserving last-good
health and all manifests. Cancellation/crash before finalization leaves reserved.
A concurrent branch writer makes finalization fail, with no merge or retry.

A lost final success acknowledgment can mean the complete ready/evidence commit
already exists. It is impossible to promise both automatic subsequent admissions
and that every lost final acknowledgment leaves the server held. This candidate
therefore never reports the uncertain caller successful and never retries its
mutation. A DIFFERENT run may later proceed only after authoritative validation
of the entire coherent final bundle: exact owner record and attempt bytes,
regular-file health and owner manifest byte equality, expected manifest/state
SHA-256 values, reservation revision, strict successful record shape, plus the
one-hour-after-completion cooldown. A lone spent ready latch, missing/partial
bundle, legacy success, contradictory error/privacy record or mixed head denies.
This is a bounded read verification, not a retry or reset of a failed archive.

The old pure `propose_completion` policy describes state transitions; the concrete
adapter adds this full-bundle admission requirement. No ambiguous finalization is
claimed universally held. No live service consistency/permission guarantee has
been established by synthetic tests.

## Initialization and release remain blocked

There is no automatic initializer, reset or override. The explicit historical
migration protocol is described in ARCHIVE_HISTORICAL_MIGRATION.md; it is not
authorized or activated. It creates migration_pending, never a normal success. Only a separately
reviewed pristine ready state (spent=0) may omit prior completion evidence. This
code does NOT authorize provisioning that state. The known failed historical
archive-attempt, including the 403, blocks even a mistakenly ready admission file.
A failed record never expires. Missing state never bootstraps itself. Only the
separately reviewed, narrowly bound migration receipt path may admit a first run
while retaining the exact historical failure in immutable evidence.

Before any release: resolve the historical denial under existing authorization,
review actual token capabilities and branch protections, establish trusted state
without erasing failure evidence, drain/inspect old queued/running workflows,
and verify exact-head CI. The current contents:write GITHUB_TOKEN may be suitable,
but actual mutation authorization is UNTESTED. No expanded access or credential
fallback is allowed. Old runners/revisions can bypass new code and must not be
mistaken for protected execution. Shared company-monitor-production concurrency
is preserved but is not CAS and does not establish hourly reliability.

All PR archive execution is removed in the workflow proposal; PR tests remain.
The production CLI is `python scripts/archive_evidence.py --report-dir NEW_DIR`.
It requires GH_TOKEN, GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT from an authorized runner.
Do NOT invoke against GitHub during offline review. No legacy --state-dir route
exists. Report directory must be fresh, with no static symlink ancestry; report
files use exclusive no-follow writes anchored to an opened directory descriptor.
This is a dedicated-runner safety measure, not protection against a malicious
process racing ancestor creation on the same filesystem. Local report failure
cannot roll back a durable final commit and must not trigger a retry.

## Offline evidence

Synthetic transport tests model exact-CAS conflicts, reservation and final response
loss, stale readback, partial evidence, historical denial, duplicate owners,
concurrent readers/writers, cancellation, preservation of unrelated state, strict
transport parsing and safe paths. Full Python and Node suites run under network
and subprocess guards; see packaged logs for exact counts. No live endpoint,
server, browser, git mutation, token permission or branch-rule test was performed.
