# Curated Identity Batch 03 Validation

Validation date: **2026-09-20**

## Purpose

Validate the third primary-source curated identity batch against the complete accepted AtlanticBridge identity chain.

## Batch contents

Batch 03 confirms three previously OPEN queue tasks:

| Queue task | Resolution | Jurisdiction | Primary evidence |
|---|---|---|---|
| NAMED_INVESTOR_PARENT — Bayer CropScience Inc. | Bayer AG | DE | Bayer official Canadian Modern Slavery filing |
| NAMED_INVESTOR_IDENTITY — Quista Technology Pte. Ltd. | QUISTA TECHNOLOGY PTE. LTD. / UEN 201933043D | SG | Reebelo official terms + CIPO trademark record |
| NAMED_INVESTOR_IDENTITY — SD2 Engineering Services S.T.P. A R.L | SD2 Engineering Services società tra professionisti a R.L. / VAT 12368010018 | IT | Città Metropolitana di Torino procurement act + official company site |

## Full-chain production acceptance

The validator rebuilt the production chain from primary sources:

1. complete Investment Canada historical corpus;
2. federal Canadian entry-entity resolution;
3. foreign named-investor / GLEIF evidence;
4. curated identity queue seed;
5. Batch 01 review import;
6. Batch 02 review import;
7. Batch 03 review import;
8. cumulative curated summary.

Batch 03 import result:

- review items processed: **3**
- evidence rows processed: **5**
- decisions processed: **3**

Cumulative curated state after Batches 01–03:

- active queue records: **26**
- confirmed reviews: **11**
- confirmed legal entities: **11**
- confirmed natural persons: **0**
- modeling-ready curated legal entities: **11**
- remaining OPEN reviews: **15**

The full-chain assertions also confirmed the three new resolved jurisdictions:

- Bayer AG — **DE**
- QUISTA TECHNOLOGY PTE. LTD. — **SG**
- SD2 Engineering Services società tra professionisti a R.L. — **IT**

## Identity boundaries

### Bayer

The curated task resolves the parent relationship requested by the queue. Bayer's official filing identifies Bayer CropScience Inc. as a Canadian Bayer Group operating entity and Bayer AG as ultimate parent.

### Quista

The named legal entity is Singapore-incorporated even though Investment Canada reports Germany as the country of ultimate control. AtlanticBridge keeps those two facts separate.

### SD2

The Investment Canada spelling differs slightly from the Italian official/legal presentation. The government procurement evidence supplies the stable Turin address and VAT/P.IVA identifier used for confirmation.

## Modeling boundary

Batch 03 expands the verified company identity cohort. It still does not create an Expansion Likelihood score.

The remaining 15 OPEN tasks continue to require primary-source review or explicit insufficient-evidence/blocking decisions before they may enter the curated modeling cohort.
