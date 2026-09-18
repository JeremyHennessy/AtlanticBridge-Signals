# GLEIF Resolution Validation

Validation date: **2026-09-18**

## Purpose

Validate the production CORDIS → GLEIF candidate-resolution path without auto-confirming legal identities.

## Production path exercised

A fresh database was built from the current official CORDIS Horizon archive, then a bounded batch of real EU organizations sharing projects with Canadian participants was resolved through the production CLI:

```bash
python -m atlanticbridge ingest-cordis --db gleif-live.sqlite
python -m atlanticbridge resolve-cordis-gleif \
  --db gleif-live.sqlite \
  --limit 10 \
  --page-size 5 \
  --delay-seconds 0.05
python -m atlanticbridge summarize-gleif --db gleif-live.sqlite
```

## Live evidence

CORDIS source used by the validation:

- projects: **23,451**
- participation rows: **145,274**
- source bytes: **36,672,015**
- source SHA-256: `f91d5b6d7f952a4eeb725f4917576ffba652b6b03739d2ba763fa67b5dee6d22`

GLEIF Golden Copy evidence:

- Golden Copy publish timestamp: **2026-09-18T08:00:00Z**
- source organizations queried: **10**
- candidate rows returned: **9**
- unique LEIs persisted: **9**

Resolution states:

| State | Entities |
|---|---:|
| REVIEW_READY | 4 |
| NO_RESULTS | 5 |
| UNRESOLVED | 1 |
| AMBIGUOUS | 0 |
| CONFIRMED | 0 |
| REJECTED | 0 |

Candidate match classes:

| Match class | Candidate rows |
|---|---:|
| EXACT_NAME_COUNTRY | 4 |
| CANDIDATE | 5 |

## Interpretation

A `REVIEW_READY` record means exactly one returned GLEIF candidate had both:

1. an exact normalized legal-name match; and
2. a matching legal jurisdiction.

It **does not** mean that AtlanticBridge has confirmed the legal identity.

No source entity in this validation was automatically changed to `CONFIRMED`.

The live GLEIF API also exposed direct-parent, ultimate-parent and child relationship endpoints. Those links are preserved as candidate evidence, but parent/child graph materialization remains blocked behind explicit source-identity confirmation so that ownership evidence cannot be attached to an incorrect candidate.

## Acceptance result

The production resolution path completed successfully and persisted an explicit state for every queried CORDIS organization. No queried organization silently disappeared from the pipeline, and no candidate was auto-confirmed.
