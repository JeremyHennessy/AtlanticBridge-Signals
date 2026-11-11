# Historical migration protocol: offline candidate, not release approval

No real migration, approval, restriction resolution, privacy probe, dispatch or
remote mutation has been performed. Known historical 403 and the stale queued
job remain release blockers. Existing custom permissions for other repositories
do not authorize this transition. General instructions to continue are not the
specific future release authorization required here.

## Why this is not a success reset

The migration CLI creates a proposal from an exact monitoring-state head, then
requires independently supplied resolution and authorization records. Apply writes
only archive-admission.json (migration_pending) and archive-migration.json in one
exact-head CAS. It never calls the archive client, privacy verifier, workflow
dispatch or callbacks. It never writes a successful attempt or health record.
Old missing, FAILED, 403, legacy VERIFIED_DRAFT_COPY, reserved or review_hold state
is captured exactly, not relabeled as new success.

The entire certificate, including decisions and evidence, is committed to the
monitoring-state branch and is visible to everyone with repository access. Use
only concise non-sensitive review references, never transcripts, credentials or
raw exception text. Input bytes and reviewer/reference lengths are bounded.

The immutable certificate embeds exact original admission, attempt, health and
operator-selected provenance blob text, including null for absence. Its original
commit SHA pins the entire original tree and history. Future normal execution
can replace mutable latest attempt/health, but the certificate and original
commit preserve the originals. Git hosting retention and protection of reachable
history are operational prerequisites, not established by these tests.

## Explicit trusted-input boundary

This is an operator-reviewed deployment protocol, not an authorization service.
JSON fields such as approved_by, authorization_reference and restriction_resolved
are audit attestations, NOT cryptographic proof of permission or resolution.
The operator must independently authenticate the actual user's specific future
release approval and independently inspect the referenced restriction and queue
resolution evidence. Anyone controlling trusted code, credentials, or these
operator files can lie. No synthetic fixture is a real approval.

There are no approval generators, defaults, workflow invocations, automatic
certificate recovery, clock-based failure resets or replacement credentials.
No receipt is a fresh privacy proof. Only the subsequent ordinary archive
verifier can establish that proof, under its unchanged fail-closed rules.

## Concrete future handoff (not authorized now)

1. Keep archive dispatch and all old runners disabled/drained. Resolve the actual
   restriction, inspect real token scope and branch protections, and verify no
   old revision can write or run. Record the independently verified drain time: drained_at is when the LAST
   possible legacy request ended, not merely when a queue/workflow was disabled.
   Wait a full hour after that point.
2. In a separately explicitly authorized maintenance execution, obtain its own
   existing GITHUB_RUN_ID-GITHUB_RUN_ATTEMPT before invoking any archive work.
   This execution must pause for review. It may run the read-only plan command.
   This avoids dispatching a normal archive simply to discover a run ID. There
   is no maintenance workflow shipped by this change. The existing scheduled
   retention workflow does not invoke plan/apply or pass a receipt; merely
   enabling it cannot bootstrap this protocol. A suitable maintenance
   execution/context is remaining reviewed wiring, not an existing capability
   claimed here. No operator shell or credential availability is assumed.
3. Run archive_migration.py plan with --expected-head SHA, --output NEW_PATH and
   optional --pin PATH for provenance blobs. Review the exact proposal, original
   historical evidence and immutable commit. The plan command has no mutation.
4. Supply separate trusted resolution/approval JSON files matching the validated
   schemas in archive_migration.py. Approval binds repository, expected head,
   canonical plan hash, resolution hash, explicit scope, exact first owner,
   issuer/reference, issuance and expiration. Resolution binds repository/head,
   evidence hash, restriction resolution, drained jobs, reviewer/evidence
   reference, drained_at and resolved_at. Approval follows resolution. Validity
   is at most one hour. Both apply and first admission require at least a full
   hour since the attested drained_at. Do not invent a record to fit the schema.
5. Only after the actual specific future authorization, execute
   archive_migration.py apply --plan PLAN --resolution RESOLUTION
   --approval APPROVAL --output NEW_RECEIPT in that maintenance execution.
   It uses existing GH_TOKEN and fixed repo/branch, CAS once, reads exact bytes
   back, and writes a fresh exclusive local receipt. No dispatch occurs.
6. If and only if that command succeeds and produces the complete receipt,
   a separately approved archive command in the SAME named execution may pass
   --migration-receipt NEW_RECEIPT to archive_evidence.py with --report-dir NEW_DIR.
   No additional branch writers are permitted between these steps. This command
   validates owner, expiry, receipt head/hash, exact pending state, immutable
   original evidence and unchanged current evidence, then reserves durably
   before constructing the archive client. The receipt cannot bypass budget,
   owner records, once-only execution or privacy verification.
7. Repeated owner, expired approval, changed head/evidence, replay, malformed
   files or absent receipt deny. Successful first completion uses the ordinary
   atomic final bundle. Subsequent distinct normal runs omit the receipt and
   obey the full completion-bundle check and cooldown.

## Uncertain acknowledgments and crash behavior

A failed/unknown apply call returns no receipt. If its commit actually landed,
the server remains migration_pending, not ready. Ordinary execution without a
receipt cannot proceed and repeating apply is rejected. A crash before local
receipt delivery, output failure, stale readback or concurrent writer similarly
requires fresh manual review; no automatic repair is provided.

A serialized receipt is not an unforgeable acknowledgment: a trusted operator
could reconstruct it. This implementation does NOT prove that every externally
reconstructed receipt followed an acknowledged write, and does not protect
against a malicious operator. Reconstructing/issuing a replacement is outside
this protocol and would require new explicit review/authorization. A complete
receipt already delivered before an unrelated process crash remains usable only
within its strict owner, head and expiration binding.

After first reservation, uncertain reservation and cancellation leave reserved.
Known failure leaves review_hold when diagnostic finalization succeeds, or
reserved if it cannot persist. Neither expires. Lost final-success acknowledgment
retains the prior adapter's honest semantics: a different later run can reconcile
only an authoritative complete normal success bundle plus cooldown. It is not a
migration receipt recovery route.

## Offline validation limits

Tests use synthetic GraphQL storage, no sockets/process launch. Coverage includes
old failures and legacy success, exact preserved evidence, stale heads, mutation
denial/lost acknowledgment, bad readback, absent/expired/tampered approval, owner
mismatch, concurrent migration, crash after commit, replay, exclusive CLI output,
no callbacks, first-run failure/cancellation and final-success lost ack.
This is not a live permission, GraphQL compatibility, branch-rule, consistency or
production dependency test. Full regression outcomes are recorded in the bundle.
