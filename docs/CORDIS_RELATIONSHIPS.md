# CORDIS Relationship Validation

Validation date: **2026-09-18**

Source: CORDIS Horizon Europe bulk CSV archive  
Source URL: `https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip`

## Production ingest proof

The production AtlanticBridge CLI was run end-to-end against the live CORDIS archive:

```bash
python -m atlanticbridge ingest-cordis --db cordis-live.sqlite
python -m atlanticbridge summarize-cordis --db cordis-live.sqlite
```

Observed archive evidence:

- archive bytes: **36,672,015**
- archive SHA-256: `f91d5b6d7f952a4eeb725f4917576ffba652b6b03739d2ba763fa67b5dee6d22`
- projects ingested: **23,451**
- participation rows ingested: **145,274**

Observed Canada/EU relationship coverage:

- Canadian participation rows: **499**
- distinct Canadian CORDIS organization IDs: **159**
- projects with Canadian participation: **423**
- EU-27 participation rows on Canadian projects: **4,646**
- distinct EU-27 CORDIS organization IDs on Canadian projects: **2,553**
- distinct EU-27 organization IDs with raw activity code `PRC`: **1,038**
- projects containing both a Canadian and at least one EU-27 participant: **412**

Largest EU-27 participation-row counts on Canadian projects in this snapshot:

| Country code | Rows |
|---|---:|
| FR | 696 |
| DE | 656 |
| ES | 530 |
| IT | 498 |
| NL | 378 |
| BE | 325 |
| SE | 204 |
| FI | 197 |
| PT | 158 |
| DK | 150 |

## Interpretation boundary

These are **direct project-participation relationships**, not proof that a company intends to enter Canada.

A shared Horizon project is a candidate pre-entry signal. Its predictive value must be measured against historical Investment Canada outcomes before it receives any Expansion Likelihood weight.

CORDIS `organisationID` is source-local. Entity resolution to durable legal-company identities is deferred to the GLEIF/entity-resolution workstream.

Activity codes are stored raw. AtlanticBridge does not infer a business type from `PRC`, `HES`, `REC`, `PUB`, or `OTH` until an authoritative code mapping is incorporated.

## Verification result

The independent schema/coverage probe and the production CLI produced the same Canada/EU relationship counts for the live archive. This validates the implemented project/participation joins for this source snapshot.
