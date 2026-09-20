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


## Accepted live proof — Control Cohort 001

The accepted live build on exact branch head before pinning used the complete
Investment Canada history and produced:

- **681** source pages across **36** buckets;
- **32,369** unique records from **33,106** source appearances;
- **737** duplicate source appearances deduplicated by stable identity;
- source snapshot-manifest SHA-256:
  `ee6eb157b2431cf5ed4d7f674e11f3bf4632b3ad650a2fc95582ce674ddd0238`;
- **7/7** audited `TRUE_NEW_ENTRY_CANDIDATE` rows with complete 24-month follow-up;
- **21** raw risk-set assignments covering **21** distinct future-entrant entities;
- **8** country + activity-overlap matches and **13** country-only fallbacks;
- **21/21** identity rows `UNREVIEWED`;
- **0** backtest-eligible controls;
- **0** negative labels.

Accepted run: https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35544368650

The pinned manifest records the canonical full-payload SHA-256
`8649a3f0ccbaa749a23c07bc48e62d1b64aa71dadf62aed0fc55d4e96e140888`.
The pinned identity-review queue SHA-256 is
`c0aa14e81ac71c3cffe48420bb3066c5c8baf0991517bcc3cfff11b86a484e20`.

Inspection of the raw queue confirmed that the named-investor field can contain
natural persons and Canadian vehicles despite an EU country-of-ultimate-control
attribute. This is treated as evidence that the separate identity gate is
required, not as a reason to introduce heuristic suffix filtering.
