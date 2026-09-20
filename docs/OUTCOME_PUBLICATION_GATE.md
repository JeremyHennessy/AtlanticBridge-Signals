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


### Batch 02 — CIPO advertised dates

CIPO publication semantics are documented in [OUTCOME_PUBLICATION_BACKFILL_02_CIPO.md](OUTCOME_PUBLICATION_BACKFILL_02_CIPO.md).

CIPO filing dates are **not** used as historical public-availability dates. Batch 02 uses each record's `Advertised` date from CIPO Action History, corresponding to publication in the official Trademarks Journal.

After Batch 02:

- 14 `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- 2 `VERIFIED_DURING_NOTIFICATION_MONTH`
- 5 `VERIFIED_AFTER_NOTIFICATION_MONTH`
- 29 `UNVERIFIED`
- 11 cases with at least one verified pre-notification evidence row
- 0 model-eligible cases


### Batch 03 — Federal lobbying posted dates

Federal Registry of Lobbyists publication semantics are documented in [OUTCOME_PUBLICATION_BACKFILL_03_LOBBYING.md](OUTCOME_PUBLICATION_BACKFILL_03_LOBBYING.md).

The registration's effective/start date is **not** treated as a publication date. For Britishvolt, Batch 03 adds a separate monthly communication report whose Registry record explicitly gives a **Posted date of 2021-04-08**, before the June 2021 notification.

After Batch 03:

- 15 `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- 2 `VERIFIED_DURING_NOTIFICATION_MONTH`
- 5 `VERIFIED_AFTER_NOTIFICATION_MONTH`
- 29 `UNVERIFIED`
- 12 cases with at least one verified pre-notification evidence row
- 0 model-eligible cases


### Batch 04 — Toronto council archive

The City of Toronto publication cutoff for the TOPdesk primary evidence is documented in [OUTCOME_PUBLICATION_BACKFILL_04_TORONTO.md](OUTCOME_PUBLICATION_BACKFILL_04_TORONTO.md).

AtlanticBridge uses the **2016-06-07 City Council meeting date** as a conservative latest-by public cutoff for the linked Invest Toronto 2015 Annual Report. The report's 2016-05-09 origin date remains a separate source date.

After Batch 04:

- 16 `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- 2 `VERIFIED_DURING_NOTIFICATION_MONTH`
- 5 `VERIFIED_AFTER_NOTIFICATION_MONTH`
- 28 `UNVERIFIED`
- 12 cases with at least one verified pre-notification evidence row
- 0 model-eligible cases

### Batch 05 — residual source-family review

Batch 05 reviews every one of the **28** rows that remained `UNVERIFIED` after Batch 04. The full row-level disposition is documented in [OUTCOME_PUBLICATION_BACKFILL_05_REVIEW.md](OUTCOME_PUBLICATION_BACKFILL_05_REVIEW.md) and `reviews/outcome_audit/2026-09-20-publication-review-05.json`.

Six rows receive new defensible historical public cutoffs:

- two Bukwang DART annual-report rows: 2023-03-28;
- Trillium judicial decision: 2024-03-28;
- Britishvolt administrator proposal filing: 2023-03-22;
- Sorel-Tracy municipal resolution: 2025-03-31;
- Bolton government event invitation: conservative latest-by cutoff 2020-03-20.

The remaining **22 rows stay `UNVERIFIED`**. In particular, current pages, reporting periods, legal-event dates, approval dates and registry effective dates are not promoted merely because they are dated.

After Batch 05:

- 17 `VERIFIED_BEFORE_NOTIFICATION_MONTH`
- 2 `VERIFIED_DURING_NOTIFICATION_MONTH`
- 10 `VERIFIED_AFTER_NOTIFICATION_MONTH`
- 22 `UNVERIFIED`
- 13 cases with at least one verified pre-notification evidence row
- 0 model-eligible cases

This completes the explicit publication-semantics review of the current 51-row audit corpus without relaxing the fail-closed rule.

