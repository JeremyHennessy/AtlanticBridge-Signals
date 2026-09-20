# Outcome publication backfill 05 — full residual source-family review

Audit date: 2026-09-20.

## Purpose

Review every evidence row that remained `UNVERIFIED` after Batch 04 and populate a historical public-availability clock only where a source-family rule is defensible.

The input queue contained **28 evidence rows**.

## Decision rules

This batch does **not** copy any of the following into `publicly_available_date` merely because they exist:

- business-event dates;
- source/report dates;
- observation dates;
- registry effective dates;
- approval dates;
- reporting periods;
- dates asserted retrospectively on current company pages.

A row receives a public cutoff only when either:

1. the source family exposes an explicit filing/publication date; or
2. a public proceeding or invitation establishes a conservative latest-by date by which the retained evidence necessarily had to be public.

The complete row-by-row review is retained in:

`reviews/outcome_audit/2026-09-20-publication-review-05.json`

## Newly verified rows

### Bukwang annual report — 2 rows

The same Bukwang annual report is used in the Ocellaris and Acanthas audits.

The report's first page is addressed to the Korean Financial Services Commission and Korea Exchange and is dated **2023-03-28**. The PDF itself carries DART electronic-disclosure footers.

Batch 05 therefore uses:

- `publicly_available_date = 2023-03-28`
- precision `DAY`

The older source metadata remains separate and is not used as the leakage clock.

Both rows are after their 2019 Investment Canada notification months.

### Trillium judicial decision — 1 row

`2024 ONSC 1853` is dated **2024-03-28**. The retained reproduction identifies the CanLII decision and reproduces the court-file date.

The decision remains retrospective evidence and its pleaded-history limitation is unchanged.

Publication status: after the April 2021 notification.

### Britishvolt administrator proposals — 1 row

EY's Joint Administrators' proposals were delivered to creditors on 2023-03-13, but delivery date is not used as the public clock.

UK Companies House filing history records the **Statement of administrator's proposal (AM03)** as filed on **2023-03-22**.

Batch 05 therefore uses 2023-03-22 as the defensible public filing date.

Publication status: after the June 2021 notification.

### Sorel-Tracy municipal resolution — 1 row

The official public council minutes record resolution 2025-03-197 at the **2025-03-31** council meeting.

The meeting date is used as a conservative latest-by public cutoff for that municipal resolution.

Publication status: after the October 2023 notification.

### Bolton public government event page — 1 row

The Italian Cultural Institute Toronto public invitation was for a 2020-03-26 event and required public RSVP by **2020-03-20**.

The invitation therefore necessarily had to be public no later than 2020-03-20. Batch 05 uses that RSVP deadline as a conservative latest-by public cutoff.

This is the only Batch 05 row that becomes verified before its notification month. Bolton's Investment Canada notification is October 2025.

## Rows deliberately left unverified

**22 rows remain `UNVERIFIED`.**

These include:

- current company/history/contact pages with retrospective assertions but no historical page-publication date;
- an investor deck whose reporting period is known but original publication day is not;
- a Workforce WindsorEssex monthly report where report month is known but original posting day is not;
- a current association relationship page;
- a federal lobbying registration whose effective date is not its posting date;
- a federal corporation activity date that is a legal-event date rather than a public-posting clock;
- an AIUT announcement whose accessible copy does not expose a defensible original publication date;
- a PMRA label whose approval date is not automatically treated as the public archive date;
- a Torino administrative determination whose document date is not proven to be its posting date;
- a Virk annual report whose adoption date is not automatically treated as the registry publication date;
- Bolton's 2020 reporting-year document where an exact original publication day is not established.

These rows are not considered failures. They remain fail-closed because leakage prevention is more important than maximizing the number of dated rows.

## Result after Batch 05

Across the current 51 evidence rows:

- `VERIFIED_BEFORE_NOTIFICATION_MONTH`: **17**
- `VERIFIED_DURING_NOTIFICATION_MONTH`: **2**
- `VERIFIED_AFTER_NOTIFICATION_MONTH`: **10**
- `UNVERIFIED`: **22**
- cases with at least one verified pre-notification evidence row: **13**
- model-eligible cases: **0**

The publication review is complete for the current 51-row evidence corpus. Future evidence can still introduce new rows or stronger historical clocks; this batch does not freeze those possibilities.
