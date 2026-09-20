# Outcome publication-cutoff gate

## Purpose

The historical audit separates three different clocks:

1. when an underlying business event happened;
2. the date printed on or associated with a source;
3. when the evidence was demonstrably public and therefore available to a historical model.

Only the third clock is valid for leakage control.

AtlanticBridge therefore does **not** infer historical public availability from `event_date`, `source_date`, `source_date_basis`, or `observed_at`.

## Explicit evidence contract

An evidence row may add:

```json
{
  "publicly_available_date": "2024-05-20",
  "publicly_available_date_precision": "DAY"
}
```

Allowed precision values are:

- `DAY` — `YYYY-MM-DD`
- `MONTH` — `YYYY-MM`
- `YEAR` — `YYYY`

The gate compares the full precision interval with the Investment Canada notification month.

Statuses:

- `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- `VERIFIED_DURING_NOTIFICATION_MONTH`
- `VERIFIED_AFTER_NOTIFICATION_MONTH`
- `OVERLAPS_NOTIFICATION_MONTH`
- `UNVERIFIED`

A year-level date in the same year as the notification deliberately becomes `OVERLAPS_NOTIFICATION_MONTH`; it is not forced before or after.

## Fail-closed rule

Evidence without both explicit public-availability fields is `UNVERIFIED`.

The current audit contains source dates, event dates and observation dates collected for provenance. Those fields are intentionally **not** migrated automatically into public-availability dates. Each source family must establish its historical-publication semantics independently.

## Model-eligibility guard

CI runs:

```sh
python -m atlanticbridge summarize-outcome-publication-gate \
  --file reviews/outcome_audit/2026-09-20-cases.json \
  --strict-model-eligibility
```

The strict guard fails if a case is marked `model_eligible = true` without at least one evidence row whose explicit public-availability interval ends before the first day of the notification month.

This is a minimum anti-leakage guard, not sufficient proof of model readiness. Identity, outcome definition, event-time precision, feature scope and matched-control validity remain separate requirements.

## Current baseline

At introduction of this gate:

- audited cases: **27**
- evidence rows: **50**
- model-eligible cases: **0**

Existing evidence rows are not retrospectively declared historically available. The next data-proof step is source-family-by-source-family verification of publication semantics, followed by explicit availability dates only where those semantics are defensible.


## Verified backfill batches

### Batch 01 — 2026-09-20

The first manual source-family pass is documented in [OUTCOME_PUBLICATION_BACKFILL_01.md](OUTCOME_PUBLICATION_BACKFILL_01.md).

It adds explicit day-level public availability to 16 evidence rows. The resulting gate state is:

- 11 `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- 2 `VERIFIED_DURING_NOTIFICATION_MONTH`
- 3 `VERIFIED_AFTER_NOTIFICATION_MONTH`
- 10 cases with at least one verified pre-notification evidence row
- 0 model-eligible cases

CIPO filing/registration dates and undated historical company pages remain unverified pending separate source-semantics proof.
