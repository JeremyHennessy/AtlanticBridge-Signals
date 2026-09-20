# Risk-set controls

AtlanticBridge does not currently have verified negative labels for companies that
"did not enter Canada." Provincial registry coverage is incomplete and absence
from Investment Canada is not proof of absence from the Canadian market.

Control Cohort 001 therefore begins with **future entrants as censored risk-set
control candidates**. The risk-set clock is proven here; legal-entity
comparability is a separate gate.

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
7. retain at most five risk-set candidates per audited entry candidate;
8. mark every selected row `identity_qualification_status = UNREVIEWED` and
   `backtest_control_eligible = false`.

A company with an acquisition or any other Investment Canada record inside the
risk window is excluded even if its first new-business notification occurs
later.

A later audited entry candidate may serve as a control for an earlier candidate
before its own event. This is intentional risk-set sampling: control status is
time-indexed, not a permanent company label.

## Interpretation

A raw risk-set candidate means only:

> this investor had no Investment Canada record through the candidate's
> 24-month risk horizon and was later observed as a new-business entrant.

It does **not** mean:

- the company had no Canadian operations;
- no provincial corporation existed;
- the company was a true non-entrant;
- the control is a negative training label.

Every row therefore carries `negative_label_eligible = false`. In Control
Cohort 001 it also carries `identity_qualification_status = UNREVIEWED` and
`backtest_control_eligible = false`.

This extra gate is necessary because Investment Canada's country of ultimate
control does not prove that the named investor is itself a foreign operating
company. The named investor may be a natural person or a Canadian vehicle.
Those cases must not enter the comparable-company backtest until explicit
foreign legal-entity identity evidence resolves them.

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

The unreviewed risk-set candidate cohort is suitable for:

- source-specific historical coverage analysis;
- publication-cutoff-safe signal prevalence comparisons;
- sensitivity analysis with 12/24/36-month horizons;
- identifying the raw future-entrant pool that must pass the next foreign
  legal-entity identity review.

It is **not** yet a comparable-company control cohort. No row is backtest
eligible until the identity gate confirms the named investor is a foreign legal
entity and records the supporting evidence.

It is not sufficient to publish model weights. Each candidate signal still
requires its own historical publication semantics before event-time values can
be compared.


## Durable acceptance artifacts

The live workflow retains the complete generated risk-set payload as an artifact.
The repository pins two smaller durable files:

- `2026-09-20-risk-set-controls.manifest.json`: canonical SHA-256 of the full
  semantic payload, source snapshot-manifest hash, and accepted summary.
- `2026-09-20-risk-set-control-identity-review.json`: deduplicated legal-entity
  review queue for every raw risk-set entity, including Investment Canada
  investor node, source locality, ultimate-control country and candidate
  assignments.

After those files are pinned, the workflow rebuilds the complete live history and
requires exact manifest and review-queue reproduction.
