# Curated Identity Review Batch 02 Validation

Validation date: **2026-09-19**

## Purpose

Apply a second set of primary-source legal-entity reviews through the Data Proof 013 curated identity gate and verify the cumulative review state.

## Production acceptance

The accepted run rebuilt the complete current identity chain, seeded the 26-task curated queue, applied Batch 01, then applied:

`reviews/curated_identity/2026-09-19-primary-batch-02.json`

## Batch 02 result

- review items processed: **4**
- primary-source evidence rows processed: **4**
- decisions processed: **4**

Batch 02 confirmed:

- Framework Computer Consultants Ltd — IE
- ConTeyor International NV — BE
- SiOO WoodProtection Industry AB — SE
- Pegasi Oy — FI

## Cumulative curated state

After Batch 01 + Batch 02:

- active queue records: **26**
- confirmed reviews: **8**
- confirmed legal entities: **8**
- confirmed natural persons: **0**
- modeling-ready curated legal entities: **8**
- remaining open reviews: **18**

Every confirmed review has at least one primary-source evidence record.

## Evidence classes

Batch 02 uses:

- official CIPO government filing for Framework Computer Consultants Ltd;
- official USPTO government filing for ConTeyor International NV;
- official SiOO company-hosted regulatory document;
- official Pegasi company-domain document.

The filing identifiers in trademark evidence are treated as evidence-document identifiers, not corporate-registry identifiers.

## Modeling boundary

These confirmations establish named legal-entity identity only. They do not establish:

- accounting parent;
- Investment Canada ultimate-control entity;
- first Canadian presence;
- Expansion Likelihood.

The separate strict Data Proof 012 Backbase B.V. confirmation is not included in the curated-review count. It can be combined with curated confirmed legal entities later when constructing the modeling identity cohort.

## Acceptance conclusion

The cumulative curated review mechanism is stable with eight confirmed legal entities and eighteen unresolved tasks. The next modeling step may use these eight plus strict automated confirmed legal entities, but any backtest remains low-N and must be labeled feasibility-only until coverage expands.
