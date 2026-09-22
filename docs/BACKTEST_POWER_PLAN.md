# Backtest cohort power planning

Planning date: 2026-09-22.
Matched-stratum correction: 2026-09-22.

## Purpose

Backtest 002 is too small for a stable inferential conclusion. This document
converts "expand the cohort" into quantitative planning targets using the
corrected matched-stratum comparison.

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

## Corrected current cohort

Identity sensitivity preserves matched risk-set strata. The HIGH and
HIGH+MEDIUM comparisons currently retain only two controls, because three of the
five accepted controls are matched to the LOW-confidence Antea entrant stratum.

### HIGH observed point-estimate scenario

Current matched counts:

- entrants: 2/4 = 0.50;
- controls: 0/2 = 0.00.

If 0.50 vs 0.00 were the true underlying rates, the current 4-vs-2 design has
**0% exact Fisher power** at alpha 0.05: with only two controls, no possible
table at those margins can reach the two-sided rejection threshold often
enough to provide useful power.

The first equal-group design reaching 80% exact power under that extreme effect
assumption is:

- **12 entrants**;
- **12 controls**;
- 24 total observations;
- exact power 0.806152343750.

The observed 0/2 control rate is far too unstable to use as a planning truth.

### HIGH or MEDIUM observed point-estimate scenario

Current matched counts:

- entrants: 2/5 = 0.40;
- controls: 0/2 = 0.00.

Under a true 0.40 vs 0.00 effect, the current 5-vs-2 design has only
**1.024% exact power**.

The first equal-group design reaching 80% exact power is:

- **16 entrants**;
- **16 controls**;
- 32 total observations;
- exact power 0.833432615649.

Again, the zero control rate is an unstable two-observation estimate.

## Conservative control-rate sensitivity

Because 0/2 is not a credible stable population estimate, the planner retains
20% control-positive-rate scenarios.

For 0.50 entrant vs 0.20 control:

- first 80%-power equal-group design: **44 + 44**;
- 88 total observations;
- exact power 0.802089515244.

For 0.40 entrant vs 0.20 control:

- first 80%-power equal-group design: **90 + 90**;
- 180 total observations;
- exact power 0.801679998874.

A stronger hypothetical 0.60 vs 0.20 effect still requires **27 + 27** for at
least 80% exact power.

## Interpretation

The primary bottleneck is not "number of controls" in isolation. It is the
number of **matched entrant strata that survive the identity gate**.

Controls matched to Antea or HANECS cannot increase the HIGH-tier comparison
while those entrants remain LOW-confidence. A new control is statistically
useful only when its matched entrant stratum is also eligible at the tier being
analyzed.

The practical research objective is therefore:

1. broaden the audited censored-entry cohort;
2. resolve entrant identities where primary evidence permits;
3. build controls within those retained entrant strata;
4. keep legal-identity and source-coverage gates unchanged;
5. use the enlarged matched cohort for exploratory feature/cutoff selection;
6. freeze a confirmatory design before evaluating a separate holdout cohort.

## Guardrail

Corrected Backtest 002 rates are reused here only as effect-size planning
scenarios. The observed control rate is 0/2, so explicit conservative
sensitivity scenarios are required. None of these calculations constitutes
independent validation.
