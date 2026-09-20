# Curated Identity Batch 04 Validation

Validation date: **2026-09-20**

## Purpose

Validate the fourth primary-source curated identity batch against the complete accepted AtlanticBridge identity chain.

## Batch contents

Batch 04 resolves one previously OPEN `CANADIAN_VEHICLE_PARENT` task:

- Canadian vehicle: **Bolton BG Canada Inc.**
- Investment Canada outcome: **2025-10**
- country of ultimate control: **Italy**
- resolved foreign group holding parent: **Bolton Group S.r.l.**
- jurisdiction: **IT**
- VAT: **05983890152**

## Primary evidence

The decision is supported only by Bolton primary corporate materials:

1. Bolton's official 2020 sustainability report states that **Bolton Group is the Group's holding company** and explicitly includes **Bolton BG Canada** in the group organization.
2. Bolton's official 2023 sustainability report states that Group legal entities are managed under the industrial holding **Bolton Group S.r.l.**
3. Bolton's official legal page identifies **Bolton Group S.r.l.**, Milan, Italy, VAT **05983890152**.

## Full-chain production acceptance

The validator rebuilt the complete identity chain:

1. Investment Canada historical corpus;
2. federal Canadian entry entities;
3. foreign named-investor / GLEIF evidence;
4. curated queue;
5. Batch 01;
6. Batch 02;
7. Batch 03;
8. Batch 04;
9. cumulative curated summary.

Batch 04 import:

- review items processed: **1**
- evidence rows processed: **3**
- decisions processed: **1**

Cumulative curated state after Batches 01–04:

- active queue records: **26**
- confirmed reviews: **12**
- confirmed legal entities: **12**
- confirmed natural persons: **0**
- modeling-ready curated records: **12**
- remaining OPEN reviews: **14**

The validator explicitly confirmed:

- review status: **CONFIRMED**
- subject: **Bolton Group S.r.l.**
- jurisdiction: **IT**
- identifier type: **VAT**
- identifier value: **05983890152**

## Interpretation boundary

This review resolves the foreign **group holding parent** required by the queue.

It does **not** claim that Bolton Group S.r.l. is the immediate legal shareholder shown on Bolton BG Canada's Canadian share register. No intermediate ownership step is invented.

The curated confirmation is an identity/evidence gate only. It does not create an Expansion Likelihood score.

## Acceptance result

The full production identity chain completed successfully and the cumulative counts moved from **11 confirmed / 15 open** to **12 confirmed / 14 open** with no unrelated review changes.
