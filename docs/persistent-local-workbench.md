# Private persistent workbench (offline-validated prototype)

This is a separate, single-operator local interface to an **existing** private schema-2 automation foundation. It is not a replacement for the public app, does not read or migrate its browser-local worklist, and does not merge identities. It creates no foundation, source, fixture or staging journal. Existing public `ui/` files remain unchanged.

## Operator usage, when local server access is permitted

The launcher below is provided for future operator use. It has **not been run or browser-tested** in this review environment. No screenshots or live source claims are available.

```sh
python -m atlanticbridge.automation.workbench --foundation /absolute/private/foundation.sqlite --port 8765
# Optional: --journal /absolute/private/existing-review.sqlite
```

Open `http://127.0.0.1:8765/` in a browser that supplies Fetch Metadata (`Sec-Fetch-Site`). Use exactly that address, not localhost. Ports 1024–65535 are supported. There is no host option. Keep the foundation and optional journal owner-only in an operator-private directory; existing file/sidecar ownership and permissions are checked. The foundation must already satisfy the schema-2 integrity checks. No initialization or migration is offered.

The list supports source/status filters and 25-item pages. A detail contains immutable source facts, provenance, fixture/context notices, and separately labeled import, publication and event clocks. Edit only analyst status, notes (16,000-character maximum), due date and needs-review. Saves use optimistic revisions and fixed audit actor `local-workbench`; another edit causes a conflict rather than an overwrite. Source health and optional staged history are read-only. Source and license URLs are text, not active external links.

Pending saves lock the editor. A stale revision keeps your draft. An interrupted request, malformed response, or server error can mean the save committed but its confirmation was lost: the UI says the result is unknown and blocks blind retries. Copy any draft text you need, then explicitly reload/discard to read the current persisted record. Unsaved navigation offers Keep editing or Discard. Closing the tab/reloading the page relies on the browser's unsaved-change warning; drafts are deliberately not persisted in browser storage. A browser crash can lose an unsaved draft. There is no delivery action.

## Boundary and threat model

One trusted local OS operator, no multi-user authentication, cookies, tokens or public hosting. Do not reverse-proxy, tunnel, embed, bind publicly or deploy this launcher. Exact Host, loopback peer, HTTP scheme, Fetch Metadata, and write Origin checks mitigate browser cross-origin/DNS-rebinding requests; they do **not** authenticate against other local processes that can forge headers or access the operator's files. Browser extensions and compromised local processes are outside this boundary.

Use the included launcher rather than a generic WSGI host: its request handler rejects duplicate security-sensitive headers and transfer/content encoding before WSGI normalization. Request detail logging is suppressed. An inactive connection read times out after 10 seconds; this is not a total connection-lifetime limit or a defense against hostile local-process denial of service. The API requires JSON and a strict 100,000-byte maximum content length (including JSON encoding overhead), rejects unknown/duplicate keys, exposes only explicit routes, and never accepts a filesystem path through HTTP. Reads verify and consume a single SQLite backup snapshot (including committed WAL). Writes open only an existing database with SQLite `mode=rw`, verify the live connection under a write transaction, then use the foundation's audited update. No evidence blobs, input paths or lease credentials are returned. Private notes intentionally appear only in the trusted local workbench. Errors are sanitized. CSP permits only same-origin scripts/styles/connections, no inline scripts/eval/external assets; all responses are no-store and framing is denied.

Full database verification on each request prioritizes integrity over throughput. The stdlib server is single-threaded, and large foundations can be slow; this is not a scalable/multi-user service. OS-level replacement by an actor with filesystem access is not prevented by browser protections. The optional journal is independently verified historical data, may be superseded, and does not claim current matching foundation state. No source registration/resumption/ticks, ingestion, archive access, raw export, backup/restore, transport, delivery or account endpoints exist.

## Validation

In-process WSGI tests and mocked frontend/controller tests only, under network/socket/subprocess-denying guards. Real server parsing, socket binding, browser CSP/Fetch Metadata behavior, actual visual rendering/accessibility and installed-wheel browser operation are **UNVERIFIED**. Raw-header policy is unit-tested as a pure function and through fake parser streams, and the read timeout through a fake connection, never on a listening server. Package resources are included through setuptools package-data; a wheel can be built in process for archive/resource inspection. Do not treat offline tests as live-source, deployed, or end-to-end evidence.
