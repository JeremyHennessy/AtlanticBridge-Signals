# Entry Identity and Federal Incorporation Validation

Validation date: **2026-09-19**

## Purpose

Establish a high-confidence bridge between recent EU-controlled Investment Canada new-business outcomes and the actual Canadian entry corporation, then measure whether a federal incorporation/amalgamation/continuance event was observable before the Investment Canada outcome month.

This layer deliberately separates:

1. **Canadian entry entity identity**, which can be confirmed from Canadian registries; and
2. **foreign operating/parent identity**, which remains a separate resolution problem.

A Canadian entry vehicle is never promoted to a European parent merely because the Investment Canada record reports European ultimate control.

## Cohort

Recent positive cohort:

- window: **2019-01 through 2025-12**
- EU-27 new-business outcomes: **382**
- source: complete Investment Canada historical corpus

The production acceptance rebuilt the complete Investment Canada history first:

- buckets: **36**
- pages: **681**
- row appearances: **33,106**
- unique structural records: **32,369**

## Federal sources

### Active CBCA corporations

- bytes: **103,581,765**
- SHA-256: `ccb35c240c48dadea7b00b0bd37dd364cd4199ac9f239216422ab06a7e546331`

### Inactive/dissolved CBCA corporations

- bytes: **157,007,950**
- SHA-256: `d4e6d05c61b3e9f316b02801b193deecb45ed8c4bef7c187f09ccbcd91d87db8`

The production resolver scanned active and inactive federal corporations, matched only exact normalized legal names, used city/province only as corroboration, and then required the selected Canadian legal name to be present on the official Corporations Canada JSON detail record.

## Federal identity result

| Result | Outcomes |
|---|---:|
| UNIQUE_EXACT_GEO | 25 |
| UNIQUE_EXACT_NAME_ONLY | 2 |
| AMBIGUOUS_EXACT | 1 |
| NO_FEDERAL_EXACT_MATCH | 354 |

Detail verification:

- **27 / 27** selected federal candidates were confirmed by official corporation detail data.
- confirmed share of the 382-outcome cohort: **7.07%**
- federal gold records retained: **27**
- requested gold target: **100**

The 100-record target was **not** reached at the federal layer. That is a source-coverage limitation, not a reason to weaken matching standards.

Corporations Canada explicitly excludes provincially incorporated corporations, so `NO_FEDERAL_EXACT_MATCH` is treated as **unresolved at the federal layer**, not as evidence that no Canadian legal entity exists.

## Incorporation timing

Among the 27 confirmed federal entry entities:

- **25** had a federal incorporation/amalgamation/continuance event before the Investment Canada outcome month.
- **2** had their event in the same month.
- median pre-entry lead: **94 days**
- p25: **46 days**
- p75: **287 days**

Examples:

- Vaxxinova Canada, Inc. — incorporation **2024-07-18**, Investment Canada outcome **2025-05**: **287 days** lead.
- Linet Canada Inc. — incorporation **2019-02-21**, outcome **2019-10**: **222 days** lead.
- conTeyor Canada Ltd. — incorporation **2020-11-27**, outcome **2021-03**: **94 days** lead.
- HANECS Canada Inc. — incorporation **2021-01-28**, outcome **2021-02**: **4 days** lead.

The outcome source is month-granular. Same-month incorporation events are therefore not labeled as pre-entry.

## Investor-role boundary

Among the confirmed federal records:

- `CANADIAN_VEHICLE_CONFIRMED`: **9**
- `DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION`: **18**

This validates an important modeling constraint: the Investment Canada investor field is not consistently the foreign operating/legal parent.

## Provincial unresolved queue

The production store preserves the original Canadian-business JSON for every unresolved outcome so the next resolver can target the exact source geography.

Distinct unresolved outcome/province pairs:

| Province/territory | Outcomes |
|---|---:|
| ON | 164 |
| QC | 120 |
| BC | 50 |
| AB | 15 |
| NS | 12 |
| SK | 3 |
| UNKNOWN | 3 |
| MB | 2 |
| NB | 2 |
| PE | 1 |

An outcome can appear in more than one province if the Investment Canada source lists multiple Canadian businesses in different jurisdictions. The queue is explicitly a set of distinct outcome/province pairs, not a claim that these counts sum to unique unresolved outcomes.

## Interpretation

Federal incorporation timing is now an evidence-supported candidate pre-entry signal.

It is **not yet assigned an Expansion Likelihood weight** because:

1. provincial coverage is still incomplete;
2. a matched non-entrant control cohort has not yet been constructed; and
3. false-positive prevalence among comparable EU firms is not yet measured.

## Next acceptance target

Expand the entry-entity gold cohort using official provincial registry evidence, beginning with the largest unresolved jurisdictions:

1. Ontario
2. Quebec
3. British Columbia
4. Alberta
5. Nova Scotia

Do not lower the identity threshold merely to reach 100 records.
