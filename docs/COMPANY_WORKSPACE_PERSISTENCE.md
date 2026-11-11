# Preserve the existing app's analyst workspace

## Why a separate company store is required

The deployed GitHub Pages app stores analyst work in the browser under
`atlanticbridge.analyst-workspace.v1`. Its identity is the feed's exact 64-character
`company_id`. Its five analyst statuses are `new`, `researching`, `contacted`,
`follow_up`, and `closed`; it also has notes, next action, and due date.

The evidence foundation instead identifies a source-specific record and uses
`TRIAGE`, `ACTIVE`, `HOLD`, and `DONE`. Neither namespace nor status vocabulary is
equivalent. Treating the same company name, arbitrary 64-character ID, or a
browser's declared source hash as proof of identity would attach notes to the
wrong record or falsely verify evidence. Do not connect these stores by name,
hash shape, or an automatic status mapping.

`atlanticbridge.automation.company_workspace` provides the missing **private
company-level persistence boundary**, plus an explicit migration path from the
existing app's exported backup. It is a separate SQLite database, not an evidence
foundation or review journal. It does not create companies/leads, infer identity,
verify source metadata, publish notes, or modify any source evidence. Two equal
company names with different IDs remain two entries. All five original statuses,
notes, next actions and declared metadata are preserved on import.

## Safe local preparation

The storage/migration module has no HTTP routes. A separately launched
[private company worklist](PRIVATE_COMPANY_WORKBENCH.md) now supplies a same-origin
loopback read/edit API over an existing company database, tested in process only.
It has no import/export routes, remote service, accounts, credentials, CORS
allowance, automatic browser extraction or background schedule. The public UI
still uses its original browser store. No actual user backup was imported during
development; all tests use clearly invented data exported by that unchanged UI.

Use a trusted operator-private directory, outside the public site/repository.
The CLI creates owner-only files and refuses existing destinations. It does not
change permissions to make an unsafe existing file acceptable. A useful local
sequence, after the operator explicitly exports their browser workspace, is:

```sh
python -m atlanticbridge.automation.company_workspace --db /private/companies.sqlite init
python -m atlanticbridge.automation.company_workspace --db /private/companies.sqlite plan-import --backup /private/browser-backup.json
python -m atlanticbridge.automation.company_workspace --db /private/companies.sqlite import-backup --backup /private/browser-backup.json --expected-state STATE_TOKEN --expected-backup BACKUP_TOKEN --actor operator
python -m atlanticbridge.automation.company_workspace --db /private/companies.sqlite verify
python -m atlanticbridge.automation.company_workspace --db /private/companies.sqlite export --output /private/new-browser-backup.json
```

Use the two tokens returned by `plan-import`; the import transaction checks both
again under an immediate write lock. The plan is read-only at the application
level and contains counts/conflicting IDs, never notes or source paths. SQLite
may maintain sidecars during reads. A changed workspace or selected backup is a
conflict, requiring a new plan. A repeated identical import using a fresh plan is
a no-op. An existing ID with any differing field causes the **whole import** to
fail; no existing notes are overwritten and no partial batch is accepted. Resolve
differences explicitly, preserving both versions first. There is no force option.

The API's `save` accepts exactly the four original editable analyst fields and an
expected per-company revision. Concurrent stale edits fail, and a lost response
must be reconciled by reading persisted state before retrying. `updated_at` is
the audited save timestamp; original imported timestamps remain in immutable
history. Source metadata and identity cannot be changed through this save path.
All audit history is private and includes prior notes. There is no deletion or
retention-policy feature in this preparation.

Exports use the existing browser backup format. Internal revisions/audit fields
do not enter that format. Restoring into the current public app obeys its existing
`mergeNew` behavior: it adds missing identities and does **not** overwrite existing
browser entries, even if the imported backup is newer. It is not an automatic
sync/restore-overwrite mechanism. Keep the original browser copy until a future
UI integration and its acceptance checks have been completed.

## Validation and recovery boundaries

- Exact known fields, all original statuses, 500 total entries, existing UTF-16
  string limits, valid dates, declared HTTP(S) URLs and hash shape are checked.
  URL/hash validation is structural, not evidence verification. No URL is fetched.
- JSON duplicate keys, nonfinite numbers, unknown fields and unpaired Unicode
  surrogates are rejected rather than silently discarded or normalized.
- The importer conservatively requires explicit zoned ISO timestamps and a 2 MiB
  UTF-8/canonical JSON bound. Old browser data accepted by more permissive
  `Date.parse` or byte-size behavior may need explicit reconciliation; it is never
  silently transformed. Combined imports and saves retain capacity for a browser
  compatible export.
- Reads validate a single WAL-aware SQLite backup snapshot. Writes open existing
  databases with `mode=rw`, verify schema and audit/materialized-state consistency
  under the write transaction, then commit all changes together. Missing files
  are not created by reads/imports/saves; evidence-foundation databases are rejected.
- All changes use explicit private local files. Final-component symlinks, hard
  links and unsafe existing sidecars are rejected. Trusted owner-only directories
  are required. This is not protection against a malicious local process with
  the operator's filesystem access, nor cryptographic proof against rewritten
  history. Full history checks are unbounded by import batch size; this is not a
  scalable hosted database design.
- Errors after a write may have uncertain outcomes. The CLI returns a sanitized
  `REJECTED_OR_UNCERTAIN` result instead of raw exceptions/paths. Verify state and
  re-plan before retrying. An interrupted export can leave a partial private file;
  never treat an unvalidated file as a completed backup or overwrite it blindly.

## Path to an actually persistent UI

The local worklist integration uses the **company** storage contract rather than
source-record workbench identities. Keep read-only public evidence separate from private
analyst data. For a local single-operator app, serve the UI and a narrowly scoped
company API from the same loopback origin, retaining the existing exact-host,
origin, request-size and revision controls. Do not make the public Pages app call
an unrestricted localhost API, add permissive CORS, expose a loopback service via
tunnel, or publish the private database/assets as part of a Pages artifact.

A remotely hosted/cross-device service additionally needs a chosen hosting and
authentication design, per-user data ownership enforcement, authenticated
same-origin writes/CSRF protection, durable storage/backup and retention choices,
and explicit approval of any credentials, persistent access or spending. The
local file ownership and Origin checks are **not** user authentication and must
not be repurposed as such. No provider or account has been provisioned here.

Required acceptance before claiming the UI is persistent:

1. Export from the real public store, import into the separate private company
   store, reopen it, edit with revision checks, export and validate with the
   unchanged browser importer. Exercise all statuses, equal names/different IDs,
   Unicode, notes and next actions without leaking analyst content into evidence.
2. Test two clients/tabs, stale revisions, changed migration tokens, simultaneous
   imports, unavailable storage, transaction interruption, lost confirmations,
   reload/back/close/navigation while editing and browser restart recovery.
3. Exercise actual HTTP/server parsing and real browser security/visual behavior
   only in an authorized environment. In-process/mock coverage is not proof of
   socket, browser or deployment behavior.
4. Inspect the exact release trigger chain and resolve the existing archive-probe
   restriction before merging a branch that can start it. Run the original
   privacy and publication checks without weakening, disabling or routing around
   them. Do not use another host/deployment route to evade that restriction.

The current concrete release blocker remains: main push → Pages completion →
delivery guard → possible company-monitor dispatch → evidence retention/archive,
which may retry the previously denied archive operation. Publishing code to the
existing draft PR is preparation; it is not permission to merge that chain. The
specific denied operation must be resolved under its applicable authorization
requirements before it or a dependent release is attempted.
