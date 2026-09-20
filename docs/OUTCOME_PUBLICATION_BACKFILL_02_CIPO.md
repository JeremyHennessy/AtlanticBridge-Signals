# Outcome publication backfill 02 — CIPO advertised dates

Audit date: 2026-09-20.

## Source semantics

CIPO distinguishes:

- **Date Filed** — when a completed application is received/filed by the Trademarks Office;
- **Date Advertised** — when the application is advertised under section 37(1)(d) of the Trademarks Act;
- the **Trademarks Journal** — CIPO's official publication for applications approved for advertisement.

For leakage control, this batch uses the `Advertised` action date as the defensible public-availability date. It does **not** use the filing date.

Official CIPO references:

- Trademarks guide: https://ised-isde.canada.ca/site/canadian-intellectual-property-office/en/trademarks/trademarks-guide
- Description of Dates: https://ised-isde.canada.ca/site/canadian-intellectual-property-office/en/trademarks/description-dates

## Records

| Application | Signal | Filed | Advertised / public cutoff | Notification | Gate result |
|---|---|---:|---:|---:|---|
| 1022072 | conTeyor FITBOX | 1999-07-13 | 2002-03-13 | 2021-03 | Before |
| 1799092 | SIOO:X | 2016-09-07 | 2018-12-12 | 2023-07 | Before |
| 2233219 | SANLLO | 2022-11-24 | 2024-05-22 | 2022-10 | After |
| 2198269 | Tiandingfeng / TDF | 2022-07-14 | 2024-03-27 | 2023-10 | After |
| 1912733 | VAXXINOVA | 2018-08-01 | 2021-05-05 | 2025-05 | Before |

The distinction is material: the Tiandingfeng application was filed well before the 2023 notification but was not advertised until March 2024, so it must **not** be counted as historically public pre-entry evidence under the current conservative gate.

## Result after Batch 02

Across the current 50 evidence rows:

- `VERIFIED_BEFORE_NOTIFICATION_MONTH`: **14**
- `VERIFIED_DURING_NOTIFICATION_MONTH`: **2**
- `VERIFIED_AFTER_NOTIFICATION_MONTH`: **5**
- `UNVERIFIED`: **29**
- cases with at least one verified pre-notification evidence row: **11**
- model-eligible cases: **0**

No outcome classification, first-operation date, identity decision or model eligibility changes in this batch.
