# Expanded control research — checkpoint and batch 01

Review date: 2026-09-22.

## Expansion checkpoint

The research-only max-controls=20 workflow completed successfully on its second
attempt after the first attempt encountered an Investment Canada HTTP 504.
No code change was required; the exact rerun succeeded, supporting a transient
source-transport diagnosis.

Accepted research run:

- workflow run: 35670976267;
- successful attempt: 2;
- workflow head: `d26f3abf3f015385f5c71da3a8f826da0ddfbfe1`;
- 36 Investment Canada buckets;
- 681 pages;
- 32,369 unique records;
- 33,106 source appearances;
- 737 duplicate appearances;
- source snapshot manifest SHA-256:
  `cbc9978f5b980157fe22efd3a8ace31b39b42659846ac919abb9116aacff7ffb`.

Expanded result:

- 7/7 candidate strata with complete follow-up;
- 48 raw assignments / 48 distinct future-entrant entities;
- 21 country+activity matches;
- 27 country-only fallbacks;
- 48/48 identities UNREVIEWED;
- 0 backtest-control eligible;
- 0 negative labels.

The durable raw queue is
`reviews/control_cohorts/2026-09-22-risk-set-control-expansion.json`.

The accepted five-control baseline remains unchanged.

## Identity review batch 01

Six newly surfaced entities have unusually clean primary-source identity and
operating-company evidence:

1. Deutsche Bahn International Operations GmbH — HRB 190316 B — later entry 2023-03;
2. innoscripta SE — HRB 302244 — later entry 2026-03;
3. RWE Supply & Trading GmbH — HRB 14327 — later entry 2023-04;
4. SKS Welding Systems GmbH — HRB 31381 — later entry 2023-04;
5. General Medical Merate S.p.A. — VAT 00225500164 — later entry 2025-10;
6. Leaf Space S.p.A. — VAT 08710160964 — later entry 2024-07.

All six are recorded as:

`QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY`

for **research identity purposes only**.

They are **not yet promoted to the accepted backtest control set**. This keeps
identity review separate from the later decision to compose an expanded
exploratory backtest and from source-specific event-time evidence coverage.

The machine-readable batch is
`reviews/control_cohorts/2026-09-22-expanded-control-identity-batch-01.json`.

## Why these six

The batch prioritizes rows where primary evidence directly identifies the
selected foreign legal entity and independently demonstrates an operating
business, rather than relying on suffixes, locality or ultimate-control country.

Each row also has a later Investment Canada new-business record strictly after
the assigned entrant's 24-month risk horizon.

The batch therefore adds useful identity-qualified research candidates while
preserving the existing risk-set semantics:

- future entrant, not permanent negative;
- complete Investment Canada risk horizon;
- no claim of Canadian absence;
- no source signal inferred from identity evidence;
- no Expansion Score weight change.

## Statistical implication

If all six ultimately pass the remaining expanded-control integration gates, the
distinct control pool could increase from 5 to 11. That is useful, but it is
still far below the exact power-planning targets in
`docs/BACKTEST_POWER_PLAN.md`.

The project should continue reviewing the expanded queue and broadening the
entrant cohort rather than treating this batch as sufficient for confirmation.
