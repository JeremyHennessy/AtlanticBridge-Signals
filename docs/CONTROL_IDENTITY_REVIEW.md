# Control identity review — Cohort 001 qualification

Review date: 2026-09-20.

## Purpose

Control Cohort 001 deliberately selected time-indexed future entrants before it
attempted legal-entity qualification. The accepted raw queue therefore contained
natural persons, Canadian vehicles, and ambiguous names alongside plausible
foreign operating companies.

This review resolves every one of the 21 distinct raw control entities without
rewriting the source queue.

## Decision rule

A row is **QUALIFIED** only when explicit primary evidence supports the exact
selected named investor as a foreign operating legal entity.

A row is **REJECTED** when the selected entity is demonstrably outside that
universe, including:

- a natural person;
- the Canadian investee/vehicle itself; or
- a Canadian legal name where primary evidence shows a different foreign
  operating legal entity.

A row is **UNRESOLVED** when a foreign legal entity exists but the exact legal
identity or operating-company role is not sufficiently established.

No unresolved row is promoted by suffix heuristics, locality, group branding, or
country of ultimate control.

## Result

Across all **21** raw entities:

- **5 QUALIFIED**
- **14 REJECTED**
- **2 UNRESOLVED**
- **5 backtest-control eligible**
- **0 negative labels**

Qualified foreign operating companies:

1. SENZOMATIC, s.r.o. — Czechia
2. Global Wind Service A/S — Denmark
3. Andriani S.p.A. — Italy
4. Gilardoni S.p.A. — Italy
5. SD2 Engineering Services S.T.P. a R.L. — Italy

The unresolved rows are Doku Asia Limited and Nothing Technology Inc. Both remain
ineligible.

## Backtest Control Cohort 002

`2026-09-20-backtest-controls.json` is generated only from QUALIFIED rows and
retains their original time-indexed risk-set assignments.

The result is:

- **5 eligible control assignments**
- **5 distinct qualified controls**
- eligible controls for **3 of 7** TRUE_NEW_ENTRY_CANDIDATE strata
- **4 of 7** candidate strata deliberately remain without an eligible control
- **0 negative labels**

The five assignments are:

- Antea / 2019-08 → Andriani S.p.A., later entry 2023-03
- Antea / 2019-08 → Gilardoni S.p.A., later entry 2023-03
- Antea / 2019-08 → SD2 Engineering Services, later entry 2022-04
- LINET / 2019-10 → Senzomatic, later entry 2026-02
- Leadership Pipeline / 2023-09 → Global Wind Service, later entry 2026-04

Every later entry occurs strictly after the candidate's 24-month risk horizon.

## Interpretation boundary

`backtest_control_eligible = true` means only:

1. the exact control identity is a defensible foreign operating legal entity;
2. the original Investment Canada risk horizon is complete;
3. the entity has no Investment Canada record through that horizon; and
4. the entity is later observed as a new-business entrant.

It does **not** mean the company was proven absent from Canada, and it is not a
permanent negative outcome.

Source-specific historical coverage is a separate gate. CIPO, CORDIS,
procurement, and registry signals can enter an event-time comparison only when
their own publication/coverage semantics are established at the requested
cutoff.

## Durable artifacts

- Raw queue:
  `reviews/control_cohorts/2026-09-20-risk-set-control-identity-review.json`
- Explicit decisions:
  `reviews/control_cohorts/2026-09-20-control-identity-decisions.json`
- Eligible time-indexed controls:
  `reviews/control_cohorts/2026-09-20-backtest-controls.json`
- Validator/generator:
  `src/atlanticbridge/control_identity.py`
- Build command:
  `python scripts/build_backtest_controls.py`

The raw queue remains immutable evidence of what Control Cohort 001 selected.
