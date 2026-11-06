# Private company UI and same-origin API

The private company worklist now reads and saves the actual company-level analyst
storage described in [company workspace persistence](COMPANY_WORKSPACE_PERSISTENCE.md).
It preserves the original five statuses, notes, next action and due date, with
exact company IDs and revision-checked saves. It does not use the evidence
foundation's source-record IDs/statuses and never maps companies by name.

This local interface is implemented and tested **in process**, not activated or
verified in a real browser/server. The public GitHub Pages UI remains unchanged
and still uses browser storage. There is no automatic synchronization between
the two copies.

## Operator usage, only where server access is permitted

The company database must already exist, pass private-file/schema/history checks,
and contain explicitly imported company entries. Use the separate CLI migration
preflight/import flow; this UI cannot create a database or import a backup.

```sh
python -m atlanticbridge.automation.company_workbench --company-db /private/companies.sqlite --port 8766
```

Open exactly `http://127.0.0.1:8766/` in a browser that supplies Fetch Metadata.
There is no configurable host. The port is validated in 1024–65535; the default
8766 keeps this separate from the source-record workbench's default port. The
launcher above has **not been run** in the restricted verification environment.
Do not run it there without resolution of the existing server/socket limitation.

The list supports the original five status filters and 25-company pages. Names
and countries are displayed as imported, not independently verified identities.
Details show declared source provenance separately from editable analyst work.
Source URLs are inert text. The status "Contacted" only records the analyst's
label and never sends a message. No source, import/export, backup, identity,
archive, schedule or delivery control is available through HTTP.

## Saving, interruption and recovery

Save accepts exactly status, notes (4,000 UTF-16 units), next action (500 UTF-16
units), due date, and an expected revision. Calendar dates and all limits are
checked by the API and store. Original company identity/metadata cannot change
through this endpoint. Audit actor is fixed to `local-company-workbench`.

The API confirms the exact committed save's revision and fields, not a later
read that could belong to another writer. The controller accepts success only
when identity, next revision, all submitted analyst fields and immutable metadata
match. A stale edit returns 409 and retains the draft. A network interruption,
malformed response or server error can mean the write committed but its response
was lost. The UI marks the outcome unknown and blocks blind retry. Copy needed
draft text, explicitly reload/discard, and check the persisted revision first.

Pending saves disable editing, repeated submits and navigation. Unsaved Back,
Forward, Close and Reload actions require Keep editing or Discard. A tab close
uses the browser's unload warning when available. Drafts are intentionally not
stored in local/session storage, cookies or another backup file; a browser crash
can lose unsaved edits. Saved work lives in the existing private SQLite database.

## Privacy and authentication boundary

This is for **one trusted local operator on a trusted machine**, not a shared or
multi-user service. There is no login, account identity, session, token or remote
authentication. Any other local process able to make HTTP requests can forge
Host/Origin/Fetch-Metadata headers and act as the operator. Do not use this server
where other local users/processes are untrusted. File ownership controls protect
the file, not callers who reach the running process. Browser-origin protections
are not substitutes for authentication.

The existing source-workbench transport policy is shared: fixed exact Host,
loopback peer, HTTP scheme, same-origin Fetch Metadata for all private APIs,
exact write Origin, duplicate-header and encoding rejection before WSGI
normalization, strict JSON, bounded content length, route/query allowlists,
no-store responses, no framing, no external assets, no CORS allowance and a
same-origin-only CSP. Use the supplied launcher because its raw-header policy is
part of this boundary. Generic WSGI hosting can omit those protections.

There is no proxy, tunnel, HTTPS/public-host option or cookie-based authority.
Do not expose this app on another host or make the public Pages UI call it using
permissive CORS. Neither serving it elsewhere nor changing the host checks is a
valid way to work around the archive release restriction.

Private note/action fields are absent from list summaries and appear only in the
selected company's private detail. All returned source metadata remains labelled
unverified. Request-detail logging is suppressed; errors contain no raw paths,
SQLite exception messages or analyst notes. Names, notes and source fields are
rendered with text APIs, never interpreted as HTML or activated as links.

Every read verifies a single WAL-aware database snapshot; writes use the existing
immediate transaction, semantic validation and revision lock. Missing databases
are never initialized by the server, and the evidence foundation/review journal
are not accepted in place of the company database. Files/sidecars must remain
owner-only and in a trusted private directory. The server cannot defend against
a malicious local process racing file replacement or rewriting all history.

The stdlib launcher is single-threaded and uses the existing 10-second idle-read
timeout. This is not a wall-clock request limit, scalable service or hostile
local-process denial-of-service defense. Full integrity checks inspect all local
history even though list output is paginated.

## Verified versus still required

Offline tests cover the actual WSGI routes, durable save/reopen, exact identity and
field preservation, source-store separation, malformed JSON/query/headers, origin
and host rejection, metadata/privacy projection, pagination, concurrent/stale
edits, committed-but-lost results and absent/unsafe database files. Controller and
mocked DOM/history tests exercise the shipped UI handlers, interrupted/repeated
flows, response validation, text rendering and explicit discard recovery. Wheel
checks verify packaged assets and the installed API path. All run under guards
that reject network/socket/child-process attempts.

Real HTTP parsing on a socket, browser Fetch Metadata/CSP behavior, visual layout,
accessibility and installed-browser operation remain **UNVERIFIED**. Those checks
must run in a permitted environment before calling this a usable tested local
browser application. Remote/cross-device use still needs a separately approved
hosting/authentication/per-user authorization and backup/retention design.

This change leaves all public UI files and existing workflows untouched. PR CI
may run the pre-existing live Investment Canada smoke. Main merge can still
trigger Pages → delivery guard → company monitoring → evidence retention/archive.
Do not merge or indirectly retry the previously denied archive privacy operation.
The original anonymous HTTP-404 requirement remains unchanged; HTTP403 is not
success. No server, browser, source, archive request, external activation or
deployment is part of this preparation.
