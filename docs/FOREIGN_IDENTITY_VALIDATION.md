# Foreign Named-Entity and Parent Validation

Validation date: **2026-09-19**

## Purpose

Validate whether the detail-confirmed federal entry-entity cohort can be resolved to the legal entity named by Investment Canada and, where available, to GLEIF direct/ultimate accounting-parent evidence.

This layer deliberately separates:

1. the **Canadian entry entity**;
2. the **named Investment Canada investor**; and
3. the **foreign / accounting parent**.

These are not assumed to be the same entity.

## Production path

The accepted run executed:

```bash
python -m atlanticbridge ingest-investment-canada \
  --db foreign-identity-live.sqlite \
  --history \
  --workers 4

python -m atlanticbridge resolve-entry-identities \
  --db foreign-identity-live.sqlite \
  --start-month 2019-01 \
  --end-month 2025-12 \
  --gold-limit 100 \
  --detail-limit 140

python -m atlanticbridge resolve-foreign-identities \
  --db foreign-identity-live.sqlite \
  --page-size 20

python -m atlanticbridge summarize-foreign-identities \
  --db foreign-identity-live.sqlite
```

The upstream federal entry-identity acceptance again produced **27 detail-confirmed federal entry entities**.

## Named-investor resolution result

Targets:

- detail-confirmed entry outcomes: **27**
- distinct named investors queried in GLEIF: **18**
- Canadian-vehicle investor rows not queried as foreign entities: **9**

Final states:

| State | Records |
|---|---:|
| CANADIAN_VEHICLE_PARENT_UNRESOLVED | 9 |
| CONFIRMED_FOREIGN_NAMED_ENTITY | 1 |
| CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED | 1 |
| REVIEW_READY_EXACT_NAME | 1 |
| NO_RESULTS | 15 |
| QUERY_ERROR | 0 |

## Confirmed foreign named entity

### Backbase B.V.

Investment Canada investor:

- name: **Backbase B.V.**
- locality: **Amsterdam**
- country of ultimate control: **Netherlands**

GLEIF exact-name + locality evidence:

- LEI: `9845007KCB45A7E08A67`
- legal name: **Backbase B.V.**
- jurisdiction: **NL**
- classification: `CONFIRMED_FOREIGN_NAMED_ENTITY`

Parent evidence:

- direct accounting parent: reporting exception `NATURAL_PERSONS`
- ultimate accounting parent: reporting exception `NATURAL_PERSONS`

No parent LEI was asserted.

## Confirmed Canadian named investor

### Bayer CropScience Inc.

Investment Canada investor:

- name: **Bayer CropScience Inc.**
- locality: **Calgary**
- country of ultimate control: **Germany**

GLEIF exact-name + locality evidence:

- LEI: `549300QG5ON80NW8DV29`
- legal name: **Bayer CropScience Inc.**
- jurisdiction: **CA-AB**
- classification: `CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED`

This is the key boundary proven by the live run:

> A named Investment Canada investor can be distinct from the newly listed Canadian business and still itself be a Canadian legal entity, even when country of ultimate control is European.

Parent evidence:

- direct accounting parent: reporting exception `NO_KNOWN_PERSON`
- ultimate accounting parent: reporting exception `NON_CONSOLIDATING`

No foreign parent LEI was asserted.

## Matching rules

Automatic legal-entity confirmation requires:

1. exact normalized legal-name match; and
2. unique match between the Investment Canada investor locality and the GLEIF legal-address or headquarters city.

A unique exact legal-name result without locality corroboration remains:

`REVIEW_READY_EXACT_NAME`

Investment Canada's **country of ultimate control is not used as the legal jurisdiction of the named investor**.

## Parent relationship rules

AtlanticBridge follows only the Level 2 relationship links advertised by GLEIF.

- If GLEIF publishes a relationship record, the start node is the child and the end node is the accounting parent.
- If GLEIF publishes a reporting exception, the reason is preserved verbatim.
- A 404 on a guessed relationship route is never treated as evidence that no parent exists.
- GLEIF accounting-parent evidence is not re-labelled as beneficial ownership.

## Acceptance conclusion

The production resolver is behaving conservatively and correctly, but GLEIF coverage is insufficient to resolve the foreign identity/parent layer by itself.

Among 18 distinct named investors:

- confirmed foreign entity: **1**
- exact-name review candidate: **1**
- no GLEIF result: **15**
- confirmed named entity that was actually Canadian: **1**

No direct or ultimate parent LEI was materialized for the confirmed entities in this acceptance run.

## Next workstream

The next resolver should be a **curated primary-evidence foreign identity queue** for the unresolved named investors.

It should:

- preserve the exact Investment Canada name/locality/control-country evidence;
- prioritize official company websites, official national registries / EU BRIS where legally accessible, and other primary identifiers;
- store evidence as explicit reviewed decisions rather than scraping restricted registries;
- never promote a company domain or parent merely from name similarity;
- feed confirmed foreign legal identities into the later matched-control/event-time backtest.

Matched non-entrant controls should wait until identity coverage improves; otherwise the control test would be dominated by entity-resolution error rather than signal quality.
