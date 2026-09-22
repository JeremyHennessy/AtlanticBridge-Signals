# Backtest 001 — event-time signal diagnostic

Accepted result date: 2026-09-21.

## Scope

Backtest 001 compares seven audited `TRUE_NEW_ENTRY_CANDIDATE` rows with five
identity-qualified, time-indexed future-entrant controls at 24, 12, 6 and 3
months before each candidate's Investment Canada notification month.

The notification month remains a **censored event-time anchor**, not a proven
first Canadian operating date. Controls are future entrants observed at risk
through the matched horizon; they are not permanent negative labels.

## Accepted source-proof state

The accepted Backtest 001 result is pinned in
`reviews/backtests/2026-09-21-backtest-001.manifest.json`.

Current event-time composition:

- 12 entities;
- 5 signal families;
- 240 event-time rows;
- 12 `PRESENT` rows;
- 108 `ABSENT_WITH_PROVEN_COVERAGE` rows;
- 120 `UNKNOWN_UNVERIFIED_COVERAGE` rows.

Source-family state counts:

| Signal family | PRESENT | Proven absent | UNKNOWN |
| --- | ---: | ---: | ---: |
| CIPO Canadian trademark | 12 | 28 | 8 |
| CanadaBuys award | 0 | 40 | 8 |
| TED contract award | 0 | 40 | 8 |
| Federal corporation event | 0 | 0 | 48 |
| CORDIS Canada relationship | 0 | 0 | 48 |

The two remaining fully unknown families have not had their required historical
public-availability semantics proven. They therefore remain unknown rather than
being converted to negative evidence.

## CIPO authoritative Journal proof

CIPO historical absence inference is now backed by the accepted official
Trademarks Journal completeness proof:

- 1,221 / 1,221 in-scope official Journal issues complete;
- coverage from 2000-01-05 through 2023-05-31;
- 824,204 Advertised Applications rows parsed;
- 0 issue failures;
- 0 unresolved reviewed-alias occurrences;
- 16 exact evidence records across 5 entities;
- required LINET, Sioo application `1799092`, and Andriani known cases
  recovered;
- absence inference enabled only after complete unambiguous exact-alias
  coverage was established.

CIPO event-time rows are therefore:

- 12 `PRESENT`;
- 28 `ABSENT_WITH_PROVEN_COVERAGE`;
- 8 `UNKNOWN_UNVERIFIED_COVERAGE`.

The eight unknown rows come from the two entrant entities whose foreign legal
identity is still unresolved. Source absence is not inferred for those rows.

## Identity-qualified CIPO result

The current CIPO counts are the same at all four event-time cutoffs.

Identity sensitivity preserves the original risk-set match. When an entrant
stratum is excluded at a confidence tier, controls selected for that entrant
stratum are excluded at the same tier. A control cannot remain in the HIGH
comparison merely because the control itself has HIGH identity confidence when
its matched entrant is LOW-confidence.

This corrects the earlier unpaired sensitivity calculation that retained all
five controls after excluding LOW-confidence entrants.

### HIGH identity confidence

Entrants:

- 4 identity-qualified entrant strata;
- 2 present;
- 2 proven absent;
- observed positive rate 0.50;
- false-negative rate relative to the censored anchor target: 0.50.

Matched controls:

- 2 controls across 2 retained entrant strata;
- 0 present;
- 2 proven absent;
- observed positive rate / false-positive rate: 0.00.

The three Italian controls matched to the LOW-confidence Antea stratum are not
part of the HIGH sensitivity comparison.

### HIGH or MEDIUM identity confidence

Entrants:

- 5 identity-qualified entrant strata;
- 2 present;
- 3 proven absent;
- observed positive rate 0.40;
- false-negative rate relative to the censored anchor target: 0.60.

Matched controls:

- 2 controls across 2 retained entrant strata;
- 0 present;
- 2 proven absent;
- false-positive rate 0.00.

The MEDIUM Digitary stratum currently has no accepted matched control, so adding
it changes the entrant denominator but not the matched control denominator.

These rates are estimable only on the matched identity-qualified subset. The
full seven-entrant cohort still contains two unresolved foreign identities, so
the full-cohort CIPO false rates remain fail-closed.

## CanadaBuys and TED

CanadaBuys and TED both have proven historical absence coverage for the
identity-qualified subset, but neither currently has a verified pre-anchor
positive in this 12-entity cohort.

For each family:

- 0 `PRESENT`;
- 40 `ABSENT_WITH_PROVEN_COVERAGE`;
- 8 `UNKNOWN_UNVERIFIED_COVERAGE`.

On the matched HIGH and HIGH-or-MEDIUM identity-qualified subsets, each
therefore has:

- 2 matched controls, both proven absent;
- false-positive rate 0.0;
- false-negative rate 1.0.

That makes the rates mechanically estimable, but does **not** establish useful
predictive discrimination.

## Lead time to the censored anchor

For the two entrant entities with verified pre-anchor CIPO evidence:

- median: 2,955 days (~97.1 months);
- p25: 2,308.5 days (~75.8 months);
- p75: 3,601.5 days (~118.3 months).

The one control with verified pre-anchor CIPO evidence has an anchor lead time
of 1,121 days (~36.8 months).

These are signal-to-notification-anchor lead times. They are **not**
first-operation lead times.

## Expansion Score gates

Backtest 001 now mechanically opens the **weight-design** gate because at least
one signal, CIPO, has both verified positive evidence and proven absence
coverage with estimable identity-qualified false rates.

Accepted Backtest 001 summary:

- 5 signal families;
- 1 family with any verified historical positive evidence;
- 3 families with proven historical absence coverage;
- 3 families with identity-qualified estimable false rates;
- 1 family with both verified positive and proven absence evidence;
- `expansion_score_1_0_weighting_allowed = true`.

This flag means only that empirical weight design may be investigated. It does
**not** mean Expansion Score weights are statistically justified or ready for
publication.

Backtest 002 adds the statistical-sufficiency layer. Its current result keeps
**Expansion Score weight publication blocked** because the CIPO entrant-control
difference is not statistically resolved and the 95% risk-difference intervals
include zero.

See `docs/BACKTEST_002.md`.

## Reproduction

Run:

```bash
python scripts/run_backtest_001.py --output /tmp/backtest-001.json
python scripts/run_backtest_002.py --output /tmp/backtest-002.json
```

`tests/test_backtest_001.py` locks the source-state counts, identity-qualified
false-rate interpretation, lead-time diagnostics and Backtest 001 design gate.

`tests/test_backtest_002.py` separately locks the Fisher exact tests,
uncertainty intervals and fail-closed publication gate.

## Next gate

Increase the identity-qualified sample without weakening source or identity
standards.

Priority order:

1. resolve the two LOW-confidence entrant foreign identities with explicit
   primary evidence;
2. expand the audited time-indexed control / entrant cohort;
3. rerun Backtest 002 on the enlarged cohort;
4. do not publish Expansion Score weights until the statistical-sufficiency
   result supports a defensible signal effect.
