# Curated Identity Review Batch 01 Validation

Validation date: **2026-09-19**

## Purpose

Apply the first real primary-source curated decisions to the persistent Data Proof 013 identity queue.

## Production acceptance

The accepted run rebuilt the full identity chain before applying the review file:

1. complete Investment Canada historical backfill;
2. federal entry-entity resolution;
3. strict foreign named-entity resolution;
4. curated queue seed;
5. Batch 01 primary-source review import;
6. curated identity summary.

Accepted review file:

`reviews/curated_identity/2026-09-19-primary-batch-01.json`

## Result

- review items processed: **4**
- primary-source evidence rows processed: **4**
- decisions processed: **4**
- active queue records: **26**
- confirmed reviews: **4**
- confirmed legal entities: **4**
- confirmed natural persons: **0**
- modeling-ready curated legal entities: **4**
- remaining open reviews: **22**

Every confirmed record had at least one primary-source evidence row.

## Confirmed named investors

| Investment Canada named investor | Confirmed subject | Jurisdiction | Identifier |
|---|---|---|---|
| Power by Britishvolt Limited | POWER BY BRITISHVOLT LIMITED | GB | Companies House 12381543 |
| LINET spol. s.r.o. | LINET spol. s r.o. | CZ | IČ 00507814 |
| Aiut sp. z.o.o. | AIUT Sp. z o.o. | PL | KRS 0000136839 |
| Vaxxinova International B.V. | Vaxxinova International BV | NL | — |

## Evidence sources

- Companies House official company register for Power by Britishvolt Limited
- official LINET legal/contact information
- official AIUT legal/contact information
- official Vaxxinova global headquarters/contact information

The review JSON stores the exact URLs and structured evidence notes.

## Boundaries

These decisions confirm the identity of the **named investor** only.

They do not independently establish:

- the ultimate accounting parent;
- the Investment Canada ultimate-control entity;
- first entry into Canada;
- any Expansion Likelihood score.

In particular, Power by Britishvolt is a GB legal entity while the Investment Canada outcome records Sweden as the country of ultimate control. AtlanticBridge preserves that distinction.

## Acceptance conclusion

Batch 01 applied successfully through the production review importer. Four additional curated legal entities are now eligible for company-level modeling identity, subject to the normal event-time/data-availability gates.
