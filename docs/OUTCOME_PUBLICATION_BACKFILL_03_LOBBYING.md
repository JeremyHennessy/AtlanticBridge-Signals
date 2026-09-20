# Outcome publication backfill 03 — Federal lobbying posted dates

Audit date: 2026-09-20.

## Source semantics

The federal Registry of Lobbyists distinguishes the **effective/start date** of a registration from when a filing is **posted/published**.

Office of the Commissioner of Lobbying guidance states that:

- a consultant registration is due within 10 days after agreeing to lobby;
- the effective date is the date of the lobbying undertaking, not the publication date;
- after a registration is submitted and accepted, it is published in the Registry;
- recent registrations and monthly communication reports are displayed by **Posted date**.

Therefore AtlanticBridge does **not** convert a registration's initial/effective date into a historical public-availability date.

## Britishvolt Canada

The existing Britishvolt registration remains unverified for historical publication timing:

- initial registration start/effective date: **2021-03-09**
- public-posted date of that registration: not established from the retained registration page

A separate monthly communication report has an explicit public clock:

- client: **Britishvolt Canada Inc.**
- communication: **2021-03-18**
- public office holders: François-Philippe Champagne and Sarah Hussaini, ISED
- subject matter: Industry; Science and Technology
- communication number: **368941-500855**
- **Posted date: 2021-04-08**
- Investment Canada notification month: **2021-06**

AtlanticBridge therefore records **2021-04-08** as the public-availability date for this communication report. It does not rewrite the registration start date.

## Result after Batch 03

Across the audited corpus:

- evidence rows: **51**
- `VERIFIED_BEFORE_NOTIFICATION_MONTH`: **15**
- `VERIFIED_DURING_NOTIFICATION_MONTH`: **2**
- `VERIFIED_AFTER_NOTIFICATION_MONTH`: **5**
- `UNVERIFIED`: **29**
- cases with at least one verified pre-notification evidence row: **12**
- model-eligible cases: **0**

This is a publication-provenance improvement only. Britishvolt's first Canadian operating/manufacturing date remains unresolved.
