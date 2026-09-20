# Outcome cohorts

Audit date: 2026-09-20

## Purpose

The 27 audited Investment Canada new-business notifications are not a homogeneous first-entry target.

This layer partitions them into reproducible research cohorts **without changing the canonical outcome classifications** and without promoting any censored case to a model-positive label.

Machine-readable cohort file:

`reviews/outcome_audit/2026-09-20-outcome-cohorts.json`

## Cohorts

### EXISTING_PRESENCE

Evidence supports Canadian operating/commercial presence before the notification month, or an equivalent prior-presence disposition.

These cases are excluded when the notification month is used as a candidate first-entry outcome.

Current cases: **6**.

This includes the five canonical prior-presence cases plus Trillium, whose operation-window audit now places the Caledon distribution-centre operation in January 2021, before its April 2021 notification.

### TRUE_NEW_ENTRY_CANDIDATE

No older Canadian operations are established, and the available establishment, market, project or operating sequence is temporally coherent with a plausible new entry around the Investment Canada notification.

These are **censored research candidates**. They are useful for matched-control construction and sensitivity analysis, but they are not training-positive labels.

Current cases: **7**:

- Antea Canada
- LINET Canada
- Digitary Canada
- HANECS Canada
- AIUT
- SiOO Wood Protection Industry Canada
- Leadership Pipeline Institute Canada

### ESTABLISHMENT_ONLY

Canadian establishment or project presence is corroborated, but a usable operating-entry outcome is not established.

Current cases: **2**:

- Britishvolt Canada
- Pegasi IAM Canada

### NON_OPERATING_VEHICLE

The named Canadian entity is non-operating by the audited business description, or no linked operating company is established.

Current cases: **1**:

- K-Rouge Holding

### UNRESOLVED

Evidence is insufficient to place the case in another cohort without additional assumptions.

Current cases: **11**.

## Training boundary

All 27 rows remain:

`training_positive_eligible = false`

The `TRUE_NEW_ENTRY_CANDIDATE` label means only that a case is suitable for **censored matching/research**, not that it is a confirmed first-entry positive.

This distinction is required for the next workstream: matched non-entrant controls can be built around the seven candidates while the exact first-operation target remains unresolved.
