# Backtest 002 — statistical sufficiency diagnostic

Accepted design date: 2026-09-21.
Matched-stratum correction: 2026-09-22.

## Purpose

Backtest 001 has one signal family, CIPO Canadian trademark evidence, with both
verified pre-anchor positives and authoritative absence coverage on the
identity-qualified subset. That is enough to open **weight design** mechanically.
It is not enough to justify publishing Expansion Score weights.

Backtest 002 adds an exploratory inferential uncertainty layer without changing
source semantics, identity decisions, score weights, or the commercial UI.

## Matched-stratum rule

The controls were selected inside entrant-specific risk sets. Identity
sensitivity must therefore preserve those strata.

At a given identity-confidence tier:

- an entrant is retained only when its foreign signal identity passes the tier;
- a control is retained only when the control itself passes the tier **and**
  its matched entrant candidate is retained at the same tier.

The earlier sensitivity calculation incorrectly kept controls matched to
LOW-confidence entrants after those entrants were excluded. In particular,
Andriani's CIPO-positive control row was matched to the LOW-confidence Antea
stratum and cannot be counted in the HIGH or HIGH+MEDIUM comparison.

The source state counts across the complete 12-entity research cohort are
unchanged. Only the identity-sensitivity comparison is corrected.

## Methods

For each matched identity-qualified CIPO comparison at the existing 24, 12, 6
and 3 month event-time cutoffs:

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

The offsets and identity tiers are exploratory diagnostics. No cutoff or tier
was predeclared as a primary endpoint before inspecting this cohort.

## Publication boundary

Backtest 002 **cannot open the Expansion Score publication gate**, even if an
exploratory row later crosses its local Fisher / Newcombe threshold. Allowing
the first significant row among several inspected cutoffs and overlapping
identity tiers to open publication would contradict the no-post-hoc-primary
rule.

The machine-readable output therefore sets:

- `publication_gate_mode =
  EXPLORATORY_NO_PREDECLARED_PRIMARY_ENDPOINT`;
- `expansion_score_1_0_weight_publication_allowed = false` unconditionally
  for this exploratory design.

A future publication gate requires a separate confirmatory design established
before evaluating its validation data, with a predeclared primary comparison
and an independent holdout cohort or equivalent prospective validation.

## Corrected current result

The CIPO counts are unchanged across the four cutoffs.

### HIGH identity confidence

Entrants: 2 present / 2 proven absent, positive rate 0.50.

Matched controls: 0 present / 2 proven absent, positive rate 0.00.

- entrant 95% Wilson interval: 0.150039 to 0.849961;
- control 95% Wilson interval: 0.000000 to 0.657620;
- risk difference: +0.50;
- Newcombe risk-difference 95% interval: -0.244941 to +0.849961;
- two-sided Fisher exact p = 0.466667.

### HIGH or MEDIUM identity confidence

Entrants: 2 present / 3 proven absent, positive rate 0.40.

Matched controls: 0 present / 2 proven absent, positive rate 0.00.

- entrant 95% Wilson interval: 0.117621 to 0.769276;
- control 95% Wilson interval: 0.000000 to 0.657620;
- risk difference: +0.40;
- Newcombe risk-difference 95% interval: -0.315683 to +0.769276;
- two-sided Fisher exact p = 1.0.

## Interpretation

The corrected point differences are larger because the CIPO-positive Andriani
control belonged to the excluded LOW-confidence Antea stratum. That does **not**
make the evidence stronger overall: the matched control denominator falls from
five to two, leaving even wider practical uncertainty.

Therefore:

- Backtest 001 weight **design** remains mechanically open;
- Expansion Score 1.0 weight **publication remains blocked**;
- no effect-size claim is promoted from this cohort;
- cohort expansion must preserve entrant-control strata rather than adding
  unmatched controls to a pooled denominator.

## Reproduction

Run:

```bash
python scripts/run_backtest_002.py --output /tmp/backtest-002.json
```

`tests/test_backtest_002.py` locks the Fisher reference tables, Wilson
intervals, Newcombe method 10 risk-difference intervals, candidate-signal
boundary, and the exploratory fail-closed publication gate.

## Next gate

Increase the number of **matched identity-qualified entrant strata**, not merely
the number of standalone controls. Expanded controls matched to LOW-confidence
entrants cannot increase the HIGH-tier denominator until the corresponding
entrant identity is independently resolved. Use the expanded exploratory cohort
to design a future predeclared confirmatory validation cohort; do not publish
Expansion Score weights from Backtest 002.
