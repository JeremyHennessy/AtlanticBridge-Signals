# Explicit bounded local cycle

This offline integration joins existing local imports, append-only historical review staging, and persistent workbench state. It is **not a live collector, background scheduler, alert sender, or production activation**. It does not initialize databases, register/resume sources, create plans, or change schedules. No public UI or HTTP mutation endpoint is added.

## Preconditions and invocation

Use an existing private schema-2 foundation, an existing valid review journal, and one already-registered immutable review plan. Sources must already be READY to import; PAUSED and QUARANTINED sources remain unchanged. Existing source cadence and retry state govern eligibility. Input files must already exist in the format required by their registered contracts. The plan's source contract hashes must match the foundation.

From the installed package or checkout:

```sh
PYTHONPATH=src python -m atlanticbridge.automation.local_cycle \
  --foundation /private/existing-foundation.sqlite \
  --journal /private/existing-review.sqlite \
  --plan-id existing-plan --max-jobs 10 --max-scan 100
```

The API is `run_cycle(foundation, journal, plan_id=..., max_jobs=..., max_scan=...)`. The injectable clock is for deterministic tests; normal operation uses a fresh UTC wall clock for each claim/completion/staging call, preserving lease expiry checks. No command-line timestamp override exists.

The cycle imports **only sources pinned by the selected plan**, not other READY sources in the foundation. A plan's `since` filters review packets, not source import eligibility. Staging scans global event order, including filtered events, to preserve its existing cursor/prefix integrity guarantees. Baseline imports create context-only work items but intentionally produce no review events. Subsequent genuinely new versions produce historical review observations. Repeated unchanged input and replayed staging do not duplicate events or packets. Analyst notes/status/due dates survive source updates; changed source facts raise needs-review and advance revisions.

## Order, bounds, and reports

1. Read-only backup snapshots validate both existing databases, the selected plan's pins and cursor, timestamp compatibility, and integer bounds before source work. This is logical read-only preflight, not a promise of zero filesystem activity: SQLite may maintain WAL/SHM sidecars. Invalid requests do not create source runs or staging passes. Final-component symlinks, hard links, unsafe ownership/modes and unsafe existing sidecars are rejected by existing private-file checks.
2. Run at most `max_jobs` due selected sources, preserving independent source leases, backoff and quarantine. The default is 100 and supported range is 1–1000. Each source still enforces its own byte/record limits. An unexpected source operation is reported UNKNOWN and does not stop the remaining selected sources.
3. Stage at most `max_scan` existing evidence events into the selected plan, default 100, range 1–1000. The existing journal write transaction repeats plan/cursor checks against a fresh validated foundation snapshot. `staging.has_more` means another explicit bounded invocation is needed; there is no internal drain loop.
4. Independently validate committed foundation and journal snapshots and report durable counts and the latest selected-plan pass ID/cursor. These are separate observation snapshots, not an atomic cross-database view or a global-cycle receipt. The local workbench can read updated items and history on its next load; this cycle does not launch a server or push updates to a browser.

CLI exit 0 and `BOUNDED_PASS_COMPLETE` mean this invocation completed its bounded phases. They do **not** mean all due work was drained, all source leases finished, or evidence is fresh/live. Another source worker may hold a valid lease and be skipped. `max_jobs` can leave more eligible sources for another invocation. Full existing-history integrity and prefix verification is not bounded by these counts, and the cycle has no total memory bound and is not a hard CPU/wall-clock deadline.

Exit 1 reports either `REJECTED` at preflight or `PARTIAL`. The report includes phase, safe error codes, source IDs/run IDs when known, completed staging results if confirmed, and independently validated readback when available. It does not return local input/database paths, raw exception messages, evidence content or analyst notes. Import failure and lease loss are partial outcomes even when another source and staging succeed. A source UNKNOWN means its write outcome must be inspected, not assumed rolled back.

## Interruption and recovery

There is **no cross-database transaction or new coordinator ledger**. Foundation runs/leases/evidence/work/audit history and journal passes/packets are the durable authorities. Earlier commits survive later failures. A failure after a commit but before its result is received may show `staging: null` even though readback finds the packet/pass. Counts may include other invocations. No durable cycle-level ID is claimed.

On a partial outcome, inspect existing runs/source health and selected-plan history using the existing tools/workbench, address the reported source or journal problem, and explicitly invoke another bounded cycle. Already-imported input remains governed by source cadence; staging can catch up even when no source is due. Existing packet identities/cursors prevent duplicate delivery previews. Never automatically resume a quarantined source. A process interruption or KeyboardInterrupt may produce no coordinator report; committed rows remain, an abandoned live claim stays fenced until its lease expires, and later ticks perform existing recovery/backoff. The coordinator does not force-clear leases or invent terminal run outcomes.

Preflight cannot prevent later disk errors, clock changes, concurrent legitimate mutations or a local actor replacing files. Open-for-write uses SQLite `mode=rw` and never creates a missing foundation/journal after preflight. Use trusted owner-only local directories and existing SQLite filesystem assumptions; this is not protection against a malicious process with the operator's filesystem access. Concurrent cycles rely on per-source leases and journal transactions, not a global lock. Error reports intentionally distinguish rejected preflight from potentially committed later phases.

## Verification boundary

Tests run only in-process with existing network/socket/subprocess-denying guards. Coverage includes local-input change to durable work and in-process WSGI readback, preserved notes/state and fixture provenance, baseline suppression, source isolation, bounds/backlog, duplicate/repeated/concurrent cycles, invalid preflight, absent/unsafe files, expired leases, interrupted staging, committed-but-lost staging results and readback failures. Real server/browser behavior, live collectors, delivery, deployment and continuous scheduling remain **UNVERIFIED and inactive**.
