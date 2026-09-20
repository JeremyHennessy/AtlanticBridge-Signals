# Outcome publication backfill 01

Audit date: 2026-09-20.

## Purpose

This batch adds explicit historical public-availability dates only where the existing audited provenance already establishes a dated public filing or dated published page.

It does not change any outcome classification, first-operation date, model eligibility, score, identity decision, collector, resolver or schema.

## Included source semantics

Batch 01 accepts these evidence families when the audited record has an exact day:

- SEC EDGAR filing date;
- official gazette publication date;
- dated official/public-institution announcement pages;
- dated project-owner/university/company announcement pages;
- dated regulatory decision pages;
- dated contemporaneous news publication pages;
- dated industry-membership publication pages.

The added fields are:

- `publicly_available_date`
- `publicly_available_date_precision = DAY`

## Deliberate exclusions

This batch does **not** convert the following fields into public-availability dates:

- CIPO filing or registration dates, until CIPO historical publication/search visibility semantics are verified separately;
- current company pages that assert historical events but expose no historical page-publication date;
- report years or report months without a demonstrated publication date;
- event dates, meeting dates or scheduled-event dates when publication timing is not established;
- `observed_at`.

Those rows remain `UNVERIFIED` under the gate.

## Batch 01 result

- audited cases: **27**
- total evidence rows: **50**
- evidence rows given explicit public availability: **16**
- verified before notification month: **11**
- verified during notification month: **2**
- verified after notification month: **3**
- cases with at least one verified pre-notification evidence row: **10**
- model-eligible cases: **0**

This is an anti-leakage provenance improvement only. A verified pre-notification source does not by itself make a case model-eligible.
