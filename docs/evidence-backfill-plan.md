# Offline evidence backfill planning

Run from the repository root with `PYTHONPATH=src:. python scripts/plan_evidence_backfill.py`. With no inputs the report contains all seven existing pinned artifact IDs and unchanged SHA-256 values, each **uncertain**. This is a diagnostic plan, not an archive repair or evidence of current remote availability.

Optional inputs:

- `--inventory LOCAL_JSON`: a previously supplied inventory with schema `{"schema_version": 1, "observations": [{"artifact_id": 10718724645, "http_status": 200, "expired": true}]}`. Only the seven pinned IDs are supported. Duplicate/unknown IDs and invalid types fail closed. Omitted IDs stay uncertain. Extra fields are ignored and never copied into the report.
- Repeat `--retained ARTIFACT_ID=LOCAL_ZIP` for explicitly supplied local copies. Their entire ZIP SHA-256 must match the existing immutable pin, and the existing archive inspector also checks raw response hashes and unsafe/oversized ZIP entries. No path is emitted in the report. Original files are never modified.

Interpretation:

- `verified_retained`: the supplied local ZIP passes verification. This does not verify a remote archive, access controls, current availability, or checkpoint restore. Preserve this exact copy.
- `missing_local_copy`: an explicitly supplied local path does not exist. Remote absence is not inferred.
- `needs_manual_review`: supplied local bytes cannot be read or fail verification. Do not replace or regenerate evidence.
- `observed_expired`: supplied HTTP 200 metadata explicitly marks the artifact expired.
- `observed_unavailable`: supplied HTTP 404/410. This cannot distinguish expired/deleted evidence from authentication or visibility problems.
- `metadata_only_not_byte_verified`: supplied HTTP 200 metadata without verified bytes. It does not mean the artifact is still downloadable.
- `uncertain`: no observation, incomplete inventory, authentication/rate-limit/server error or other inconclusive status. API errors never become confirmed absence.

Source observations remain separate from local verification, so a verified local copy can coexist with historical source expiry. Every unverified item requires manual review before any backfill. Inventory observations have no freshness guarantee. The planner never makes requests, downloads, uploads, creates releases, regenerates source evidence, dispatches workflows or executes backfill. It emits deterministic JSON to stdout and a generic, redacted error with exit status 2 for invalid inventory/CLI inputs. An item needing review is a successful diagnostic report, not a CLI failure.

To proceed later, an operator must independently establish current access, locate original exact bytes, verify the pinned hashes and follow the existing archive and privacy checks. This diagnostic authorizes none of those actions and makes no claim that historical proof was recovered. No dependency or workflow changes are needed.

## Production checkpoint reader

The production archiver now requests raw checkpoint bytes from GitHub at the immutable data commit recorded in each monitoring artifact. This supports checkpoints above the Contents API's 1 MB inline-content limit. It rejects failed, empty or over-16-MiB downloads before storing that artifact, then validates the checkpoint checksum, captured health and exact SQLite restoration. The saved checkpoint is the original byte sequence, not a reserialized substitute.

This repair does not extend the existing 20-run production scan or recover the historical gap. Merging the reliability release triggers the existing Pages deployment and production archive attempt. Their outcomes must be checked separately; successful PR retention verification does not prove that production archival ran.
