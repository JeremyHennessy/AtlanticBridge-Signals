# Backtest 001 — event-time signal diagnostic

Accepted run date: 2026-09-21.

## Scope

Backtest 001 compares seven audited `TRUE_NEW_ENTRY_CANDIDATE` rows with five
identity-qualified, time-indexed future-entrant controls at 24, 12, 6 and 3
months before each candidate's Investment Canada notification month.

The notification month remains a **censored event-time anchor**, not a proven
first Canadian operating date. Controls are future entrants observed at risk
through the matched horizon; they are not permanent negative labels.

## Accepted Step 3 input

The accepted historical-snapshot workflow run `35552301164` at
`6d5ef1b60fc6299e65c008bac1d5cad85f0cec1b` produced:

- 12 entities;
- 5 signal families;
- 240 event-time rows;
- 12 `PRESENT` rows;
- 228 `UNKNOWN_UNVERIFIED_COVERAGE` rows;
- 0 `ABSENT_WITH_PROVEN_COVERAGE` rows.

Artifact digest:
`sha256:4202d1b13679f63092a81ebd990d0067c29d9fbbb646feaac2079000c55552ad`.

Only CIPO produced accepted historical positives. CIPO is explicitly
**presence-only** because the official Sioo trademark record demonstrated a
coverage gap in the bulk/search datasets. A CIPO non-hit therefore remains
`UNKNOWN`; it is never treated as absence.

## CIPO result

At **all four cutoffs (24/12/6/3 months)**:

| Metric | Entrants | Controls |
| --- | ---: | ---: |
| Cohort size | 7 | 5 |
| Verified PRESENT | 2 | 1 |
| UNKNOWN | 5 | 4 |
| Proven ABSENT | 0 | 0 |
| Observed-positive lower bound | 28.6% | 20.0% |

These percentages are **lower bounds on observed positives**, not prevalence
estimates. Source non-hits cannot currently be interpreted as negatives.

Only 3 of 12 entity rows are observable at each cutoff, giving a source
observable fraction of **25%**. Across all four cutoffs CIPO contributes 12
observable positive rows and 36 unknown rows.

### Lead time to the censored anchor

For the two entrant entities with verified pre-anchor CIPO evidence:

- median: **2,955 days (~97.1 months)**;
- p25: **2,308.5 days (~75.8 months)**;
- p75: **3,601.5 days (~118.3 months)**.

The one control with verified pre-anchor CIPO evidence has an anchor lead time
of **1,121 days (~36.8 months)**.

These are signal-to-notification-anchor lead times. They are **not**
first-operation lead times.

### Identity-confidence sensitivity

At each cutoff:

- HIGH-confidence entrants: 2/4 observed positive = **50% lower bound**;
- HIGH-confidence controls: 1/5 observed positive = **20% lower bound**;
- HIGH-or-MEDIUM entrants: 2/5 observed positive = **40% lower bound**;
- HIGH-or-MEDIUM controls: 1/5 observed positive = **20% lower bound**.

This sensitivity result is descriptive only because absence coverage remains
unproven.

## Other signal families

The following remain fully unknown in Backtest 001:

- `FEDERAL_CORPORATION_EVENT` — historical public-availability clock not proven;
- `CORDIS_CANADA_RELATIONSHIP` — first-publication clock not proven;
- `TED_CONTRACT_AWARD` — exact historical winner-query completeness not yet live-proven;
- `CANADABUYS_AWARD` — historical award coverage not yet collected.

For each of these families all 48 entity/cutoff rows remain
`UNKNOWN_UNVERIFIED_COVERAGE`.

## Error-rate result

False-positive and false-negative point estimates are **NOT ESTIMABLE** for all
current signals.

Reason: no signal family currently has complete enough historical source
coverage to distinguish a true non-hit from missing/unavailable source
evidence. Reporting a numeric FPR or FNR would convert unknown source coverage
into false negatives/negatives.

## Expansion Score 1.0 gate

**Score weighting remains disabled.**

Backtest 001 has:

- 5 signal families;
- 1 family with any verified historical positive evidence;
- 0 families with proven historical absence coverage;
- 0 families with estimable false-positive/false-negative rates.

No Expansion Likelihood weights can be justified from this result. Evidence
Confidence remains a separate dimension and does not substitute for predictive
discrimination.

## Reproduction

Run:

```bash
python scripts/run_backtest_001.py --output /tmp/backtest-001.json
```

`tests/test_backtest_001.py` locks the fail-closed interpretation, CIPO counts,
lead-time quantiles and identity-confidence sensitivity.

## Next gate

The highest-value next task is to establish at least one source with defensible
historical **presence and absence** coverage. TED is the next candidate because
its award notices have an explicit publication date and the API supports
historical search; exact winner-query semantics and complete result retrieval
must be proven live before non-hits can become absences.
