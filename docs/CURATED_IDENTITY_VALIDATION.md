# Curated Identity Queue Validation

Validation date: **2026-09-19**

## Purpose

Validate the persistent primary-evidence review queue that sits between strict automated identity resolution and matched-control/event-time modeling.

This layer exists because Data Proof 012 proved that GLEIF alone does not resolve enough named investors or parents to support modeling safely.

## Production path

The accepted validation executed the full current identity chain:

```bash
python -m atlanticbridge ingest-investment-canada \
  --db curated-identity-live.sqlite \
  --history \
  --workers 4

python -m atlanticbridge resolve-entry-identities \
  --db curated-identity-live.sqlite \
  --start-month 2019-01 \
  --end-month 2025-12 \
  --gold-limit 100 \
  --detail-limit 140

python -m atlanticbridge resolve-foreign-identities \
  --db curated-identity-live.sqlite \
  --page-size 20

python -m atlanticbridge build-curated-identity-queue \
  --db curated-identity-live.sqlite

python -m atlanticbridge summarize-curated-identity \
  --db curated-identity-live.sqlite
```

## Live acceptance result

Upstream evidence reproduced the accepted baseline:

- Investment Canada history: **32,369** unique records from **33,106** appearances
- recent EU new-business cohort: **382**
- detail-confirmed federal entry entities: **27**
- strict foreign-identity output: unchanged from Data Proof 012

The curated queue contained exactly **26 active tasks**:

| Task type | Records |
|---|---:|
| `NAMED_INVESTOR_IDENTITY` | 16 |
| `CANADIAN_VEHICLE_PARENT` | 9 |
| `NAMED_INVESTOR_PARENT` | 1 |

Initial review state:

- `OPEN`: **26**
- `CONFIRMED`: **0**
- evidence rows: **0**

The one Data Proof 012 record already confirmed as a foreign named entity is not re-queued.

## Stable identity

Queue IDs are deterministic from:

`outcome_record_id + task_type`

They do not depend on the transient foreign-identity run ID.

Rebuilding the queue therefore updates source evidence without destroying prior review decisions.

## Subject-type boundary

Curated decisions explicitly distinguish:

- `LEGAL_ENTITY`
- `NATURAL_PERSON`

Both require primary-source evidence before `CONFIRMED`.

Only confirmed `LEGAL_ENTITY` subjects count as:

`modeling_ready_curated_records`

A confirmed natural person remains a valid reviewed identity but is not promoted into the company-level modeling cohort.

This distinction is required because the Investment Canada outcome corpus contains named individual investors as well as companies.

## Evidence gate

Accepted primary-source evidence classes:

- official company site
- official registry
- official government filing
- official stock-exchange filing

`OTHER_REFERENCE` may be stored for context but cannot support a `CONFIRMED` decision by itself.

The database stores structured citations/identifiers and concise review notes rather than full copied webpages.

## Decision preservation

Explicit reviewed states are never overwritten by queue refresh:

- `CONFIRMED`
- `BLOCKED`
- `INSUFFICIENT_EVIDENCE`
- `REJECTED`

If a task disappears from a later upstream run, an unreviewed task becomes `RESOLVED_UPSTREAM` rather than being deleted.

## Acceptance conclusion

The production queue is suitable as the identity-quality gate for future predictive work.

It does **not** assign any Expansion Likelihood score.

Matched-control/event-time modeling remains blocked on improving confirmed legal-entity coverage through reviewed primary evidence and authorized provincial sources.
