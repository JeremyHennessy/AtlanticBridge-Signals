# Operation-window audit

Audit date: 2026-09-20

## Purpose

The canonical 27-case outcome audit intentionally leaves `first_canadian_operations_date` empty because no reviewed source establishes the absolute first Canadian operation at day precision.

That does not mean all timing information is equally unknown.

This audit records **interval-censored operating-history evidence** separately from the exact first-operation target. It answers a narrower question:

> What is the strongest defensible operating, establishment, project, or market milestone that can be placed on a historical clock without converting it into a false first-operation date?

Machine-readable audit:

`reviews/outcome_audit/2026-09-20-operation-windows.json`

## Rules

- `OPERATING_BY_DATE` is a **no-later-than bound**, not a claim that operations began on that day.
- `OPERATING_DURING_PERIOD` preserves month/year precision instead of inventing a day.
- Establishment, public market activity, recruitment, project development and IP signals remain separate from operations.
- Foreign-group or predecessor activity does not prove that the named Canadian vehicle was operating at the same time.
- `first_canadian_operations_date` is populated only if an absolute first Canadian operation is explicitly established.
- Timing alone cannot make a case model-eligible unless the exact target event is established independently.

## Result

Across all 27 canonical cases:

- exact first-operation dates: **0**
- cases with a defensible operating upper bound: **6**
- model-eligible cases from timing: **0**
- `OPERATING_BY_DATE`: **3**
- `OPERATING_DURING_PERIOD`: **3**
- establishment-only bounds: **5**
- market activity / market-signal-only: **4**
- project/recruitment activity: **5**
- non-operating holding vehicle: **1**
- fully unresolved: **6**

### Strongest operating bounds

**Backbase — operating by 2018-10-29, group scope.** Central 1 launched Forge in Canada using Backbase technology. This proves Canadian commercial activity by that date, while Backbase separately says its Canadian head office has been scaling since 2018. It does not prove the first Backbase Canada operation.

**Trillium Supply Chain — operating during 2021-01, project scope.** LCBO transition material and later litigation history strongly bound management of the Caledon distribution centre to January 2021, before the April notification. The evidence does not establish Trillium's absolute first Canadian operation.

**AIUT — operating during 2021, Canadian-entity scope.** AIUT's official branch announcement describes an open Waterloo competence centre, local specialists, direct daily customer contact, project supervision and service support. The accessible page does not expose a defensible opening day/month, so the audit preserves year precision.

**Bayer / 2022 Environmental Science — predecessor operating by 2018-06-13.** A PMRA-approved Canadian commercial label identifies Bayer CropScience Inc. in Calgary as registrant/supplier. This is predecessor-business activity and therefore evidence against treating the 2022 notification as first Canadian market entry, not an exact date for the later vehicle.

**Reebelo — operating by 2023-07-05, group scope.** Reebelo's official Canada help centre states that it currently sells in Canada. This is a precise no-later-than commercial bound before the August notification, not the first Canadian sale.

**Bolton BG Canada — operating during 2017, Canadian-entity scope.** An Italian government page states that the Toronto subsidiary was established in 2017 and that from then onward Rio Mare grew to national distribution across Canadian retailers. Year precision is retained.

## Other useful bounds

- LINET: first public Canadian market appearance announced 2019-09-11; commercial/support first operation still unresolved.
- Digitary: national MyCreds project award 2020-06-15; first Canadian service day unresolved.
- Britishvolt: project-development activity by 2021-03-09; manufacturing never inferred.
- SD2: federal engineering-consulting contract by 2024-12-06; later activity only.
- SiOO: successful Canadian establishment publicly confirmed by 2023-06-21; first sale/service unresolved.
- Vaxxinova: group-level Canada-facing aquaculture activity documented 2024-03-04; local-vehicle operation unresolved.
- K-Rouge: Investment Canada describes the vehicle as a holding company, so an operating-business first-entry target is not assigned.

## Consequence for modeling

The interval audit is useful for:

- rejecting false notification-month first-entry labels;
- defining censored/ambiguous outcome cohorts;
- identifying cases needing more research;
- preventing later backtests from treating a later observed operation as the first operation.

It is **not** sufficient to unlock exact-date first-entry training. The exact first-operation count remains zero.
