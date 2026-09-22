# Backtest 002 — statistical sufficiency diagnostic

Accepted design date: 2026-09-21.

## Purpose

Backtest 001 now has one signal family, CIPO Canadian trademark evidence, with
both verified pre-anchor positives and authoritative absence coverage on the
identity-qualified subset. That is enough to open **weight design** mechanically.
It is not enough to justify publishing Expansion Score weights.

Backtest 002 adds an inferential uncertainty layer without changing Backtest
001, source semantics, identity decisions, score weights, or the commercial UI.

## Methods

For each identity-qualified CIPO comparison at the existing 24, 12, 6 and
3 month event-time cutoffs:

- positive-rate uncertainty is reported with a 95% Wilson score interval;
- entrant minus control risk difference uses the 95% Newcombe (1998) method 10
  hybrid score interval for two independent proportions, combining the two
  Wilson intervals without continuity correction;
- association is tested with a two-sided Fisher exact test;
- alpha is 0.05.

Reference: Robert G. Newcombe, *Statistics in Medicine* 17 (1998), 873-890,
"Interval estimation for the difference between independent proportions:
comparison of eleven methods", DOI
10.1002/(SICI)1097-0258(19980430)17:8<873::AID-SIM779>3.0.CO;2-I.

The offsets remain descriptive diagnostics. No cutoff is promoted after seeing
the data as a predeclared primary endpoint.

## Current result

The CIPO counts are unchanged across the four cutoffs in the current cohort.

### HIGH identity confidence

Entrants: 2 present / 2 proven absent, positive rate 0.50.

Controls: 1 present / 4 proven absent, positive rate 0.20.

- entrant 95% Wilson interval: 0.150039 to 0.849961;
- control 95% Wilson interval: 0.036224 to 0.624465;
- risk difference: +0.30;
- Newcombe risk-difference 95% interval: -0.250130 to +0.686387;
- two-sided Fisher exact p = 0.523810.

### HIGH or MEDIUM identity confidence

Entrants: 2 present / 3 proven absent, positive rate 0.40.

Controls: 1 present / 4 proven absent, positive rate 0.20.

- entrant 95% Wilson interval: 0.117621 to 0.769276;
- control 95% Wilson interval: 0.036224 to 0.624465;
- risk difference: +0.20;
- Newcombe risk-difference 95% interval: -0.309813 to +0.603964;
- two-sided Fisher exact p = 1.0.

## Interpretation

The observed CIPO direction is entrants > controls, but the uncertainty is very
wide. Both 95% risk-difference intervals include zero and neither Fisher test is
significant at alpha 0.05.

Therefore:

- Backtest 001 weight **design** remains mechanically open;
- Expansion Score 1.0 weight **publication remains blocked**;
- no effect-size claim is promoted from this cohort;
- CIPO can remain a candidate feature while the identity-qualified cohort is
  expanded.

This is a sample-size/evidence problem, not a reason to weaken source or
identity standards.

## Reproduction

Run:

```bash
python scripts/run_backtest_002.py --output /tmp/backtest-002.json
```

`tests/test_backtest_002.py` locks the Fisher reference tables, Wilson
intervals, Newcombe method 10 risk-difference intervals, candidate-signal
boundary, and fail-closed publication gate.

## Next gate

Increase the number of identity-qualified entrant/control entities without
changing source semantics. Resolve the remaining low-confidence entrant
identities first, then expand the audited risk-set cohort. Re-run Backtest 002
only after those identity decisions are source-backed.
