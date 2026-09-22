# Backtest cohort power planning

Planning date: 2026-09-22.

## Purpose

Backtest 002 established that the current CIPO entrant/control comparison is far
too small for a stable inferential conclusion. This document converts "expand
the cohort" into quantitative planning targets.

These are **exploratory planning calculations**, not evidence that the current
point estimates are true and not permission to publish Expansion Score weights.

## Method

The planner computes unconditional statistical power for the same two-sided
Fisher exact test definition used in Backtest 002. For each assumed true
entrant/control positive rate it enumerates all possible binomial outcome
tables and sums the probability of tables whose two-sided Fisher exact p-value
is at most 0.05.

The equal-group target is the first group size whose exact power is at least
80%.

Reproduce with:

```bash
python scripts/plan_backtest_power.py --output /tmp/backtest-power.json
```

## Current cohort power

### HIGH identity scenario

Backtest 002 currently observes:

- entrants: 2/4 = 0.50;
- controls: 1/5 = 0.20.

If 0.50 vs 0.20 were the true underlying rates, the current 4-vs-5 cohort has
only **12.85% exact power** at alpha 0.05.

The first equal-group design reaching 80% exact power is:

- **44 entrants**;
- **44 controls**;
- 88 total observations;
- exact power 0.802089515244.

### HIGH or MEDIUM scenario

Backtest 002 currently observes:

- entrants: 2/5 = 0.40;
- controls: 1/5 = 0.20.

If 0.40 vs 0.20 were the true rates, the current 5-vs-5 cohort has only
**3.33% exact power**.

The first equal-group design reaching 80% exact power is:

- **90 entrants**;
- **90 controls**;
- 180 total observations;
- exact power 0.801679998874.

### Stronger-effect sensitivity

For a hypothetical true 0.60 entrant rate versus 0.20 control rate:

- the first 80%-power equal-group design is **27 + 27**;
- total 54 observations;
- exact power 0.802432204664.

This sensitivity scenario is not an observed effect estimate.

## Interpretation

The project should not optimize around getting from five controls to six or
seven. That may improve descriptive stability, but it is not enough to make the
current CIPO result confirmatory.

The practical research objective is now:

1. broaden the audited censored-entry cohort substantially;
2. create a much larger time-indexed control pool;
3. keep legal-identity and source-coverage gates unchanged;
4. use the expanded cohort for exploratory feature/cutoff selection;
5. freeze a confirmatory design before evaluating a separate holdout cohort.

The current Backtest 002 cohort remains useful for discovering whether CIPO is
worth carrying forward as a candidate feature. It is not large enough to
estimate a reliable production weight.

## Guardrail

Observed Backtest 002 rates are being reused here only as effect-size planning
scenarios. That reuse makes the calculation unsuitable as independent
validation. Final publication requires the separate confirmatory boundary
already enforced by Backtest 002.
