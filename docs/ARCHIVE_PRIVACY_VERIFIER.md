# Draft archive privacy verification

New successful runs and asset records identify their method as
`direct-api-404-no-redirect-v2`. The older `anonymous_access_status: 404`
field alone does not establish this stronger method. Historical manifests and
last-good health are not rewritten or promoted; failed attempts only update
attempt records and do not replace last-good health.

The dedicated anonymous transport accepts only bounded numeric release/asset
paths at the exact GitHub API origin. It sends no origin token or cookie, preserves configured proxy routing,
never follows redirects, and inspects the original response URL
before urllib can replace it with the request URL in an HTTPError. Only a direct,
integer HTTP 404 from the exact requested endpoint succeeds. Missing or different
response URLs, redirects, all other statuses (including 403 and 429), malformed
responses, and transport errors fail closed. No response body is read. There is
no retry or automatic backoff.

Failed attempts retain method, endpoint role/path, status and a fixed outcome.
Diagnostic headers have strict format and length limits: GitHub's hexadecimal
request ID, decimal rate-limit/retry fields and a small rate-resource enum.
Duplicate or malformed fields are omitted. Bodies, Location, arbitrary headers,
cookies, credentials, raw exception text and full URLs are never retained by the
privacy verifier. A rate-limit field is diagnostic, not proof of the historical
failure's cause.

Authenticated archive byte download redirects and cross-host authorization
stripping are unchanged, as are exact byte comparison, draft checks and the
no-overwrite rule. Verification caching is in-memory within one client and only
contains fresh successes from the new method; legacy caches are ignored.
A per-client 48-attempt ceiling and failure/cancellation latch bound direct calls.
Cross-run admission remains unactivated; see `ARCHIVE_REQUEST_ADMISSION.md` for
the tested component and required durable workflow integration contract. This
change provides no claim that the current run schedule fits anonymous limits.

Run offline regressions with `python -m unittest discover -s tests -v` in a
network-denied environment. New tests use synthetic urllib HTTPS responses and
exercise the shipping opener without a listening server. Publishing, workflows
and live verification require separate authorization and release review. A local
test pass does not establish current privacy of any remote archive or refresh
historical evidence.

## Local durable-adapter update (2026-11-08)

The newer local candidate now routes the archive CLI through the concrete exact-head
GraphQL adapter and atomic completion bundle described in ARCHIVE_REQUEST_ADMISSION.md.
Earlier statements in this historical verifier note about no adapter/workflow
change describe the preceding candidate only. Nothing is published or activated;
the historical 403 remains held, live authorization is untested, and fresh privacy
verification, proxy routing, the 48-request cap and no-overwrite behavior remain.
