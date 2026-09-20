# Outcome publication backfill 04 — Toronto council archive

Audit date: 2026-09-20.

## Purpose

Establish a conservative historical public-availability date for the primary municipal evidence supporting TOPdesk's Canadian presence.

## Evidence chain

The existing evidence is the City of Toronto-hosted **Invest Toronto 2015 Annual Report, Building a Global Toronto**, which states that Invest Toronto assisted with establishment of TOPdesk's first Canadian location in Toronto in 2015.

The report itself is attached to City item **EX15.3 — Invest Toronto - Annual General Meeting and 2015 Audited Financial Statements**.

The City Council agenda for the meeting beginning **2016-06-07**:

- identifies EX15.3;
- states that the Invest Toronto 2015 Annual Report forms Attachment 1;
- links the exact annual-report PDF retained by AtlanticBridge;
- records the report's origin as 2016-05-09.

AtlanticBridge uses **2016-06-07** as a conservative latest-by public cutoff. It does not assume that the May 9 report date was itself the publication date, even though the attachment was necessarily available no later than its public Council consideration.

Official agenda:
https://secure.toronto.ca/council/report.do?meeting=2016.CC19&type=agenda

## Treatment

For the existing TOPdesk `OFFICIAL_MUNICIPAL_ANNUAL_REPORT` evidence row:

- `source_date` remains **2016-05-09**;
- `publicly_available_date` becomes **2016-06-07**;
- precision is **DAY**;
- notification month is **2022-07**;
- publication status is therefore `VERIFIED_BEFORE_NOTIFICATION_MONTH`.

No outcome classification, first-operation date, identity decision or model eligibility changes.

## Result after Batch 04

Across the audited corpus:

- evidence rows: **51**
- `VERIFIED_BEFORE_NOTIFICATION_MONTH`: **16**
- `VERIFIED_DURING_NOTIFICATION_MONTH`: **2**
- `VERIFIED_AFTER_NOTIFICATION_MONTH`: **5**
- `UNVERIFIED`: **28**
- cases with at least one verified pre-notification evidence row: **12**
- model-eligible cases: **0**

TOPdesk already had one verified pre-notification secondary source; this batch upgrades the primary municipal source's publication provenance and therefore does not increase the case-level count.
