# Risk-set controls

AtlanticBridge does not currently have verified negative labels for companies that
"did not enter Canada." Provincial registry coverage is incomplete and absence
from Investment Canada is not proof of absence from the Canadian market.

Control Cohort 001 therefore uses **future entrants as censored risk-set
controls**.

## Design

For each audited `TRUE_NEW_ENTRY_CANDIDATE` at notification month `t`:

1. set a 24-month risk horizon ending at `t + 24 months`;
2. require the historical Investment Canada corpus to extend through that
   horizon;
3. find EU investors with the same country of ultimate control;
4. require **no Investment Canada record of any type** for that investor through
   the horizon;
5. require a later observed `Notification - new business` in the same complete
   Investment Canada corpus;
6. rank the eligible future entrants using retrospective Canadian-business
   activity-text overlap, then future-entry lag;
7. retain at most five controls per candidate.

A company with an acquisition or any other Investment Canada record inside the
risk window is excluded even if its first new-business notification occurs
later.

A later audited entry candidate may serve as a control for an earlier candidate
before its own event. This is intentional risk-set sampling: control status is
time-indexed, not a permanent company label.

## Interpretation

A matched control means only:

> this investor had no Investment Canada record through the candidate's
> 24-month risk horizon and was later observed as a new-business entrant.

It does **not** mean:

- the company had no Canadian operations;
- no provincial corporation existed;
- the company was a true non-entrant;
- the control is a negative training label.

Every control therefore carries
`negative_label_eligible = false`.

## Matching metadata is not a signal

The matcher uses the future entrant's eventual Canadian-business activity text
only to improve retrospective comparability. That text is learned from the
future outcome record and is **never** a pre-entry feature. It cannot be used in
an Expansion Likelihood model or in any event-time signal calculation.

Country is matched exactly because the Investment Canada outcome source already
records country of ultimate control for both candidate and future entrant.

## Why this design comes before general "never-entered" controls

The current complete Investment Canada history gives a common outcome source and
a verifiable future event for both sides of the risk set. A general company
universe would require proving that source coverage and Canadian entry absence
were adequate at each historical cutoff. AtlanticBridge has not yet established
that proof and therefore does not create conventional negative labels.

## Next research use

The risk-set cohort is suitable for:

- source-specific historical coverage analysis;
- publication-cutoff-safe signal prevalence comparisons;
- sensitivity analysis with 12/24/36-month horizons;
- identifying which seven censored entry candidates have enough comparable
  controls for a first backtest.

It is not sufficient to publish model weights. Each candidate signal still
requires its own historical publication semantics before event-time values can
be compared.
