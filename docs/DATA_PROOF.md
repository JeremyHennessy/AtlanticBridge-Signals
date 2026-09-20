# Data Proof 001

## Question

Can public evidence detect European companies before they establish a Canadian business?

The project will not publish an Expansion Score until this is tested historically.

## Historical outcome baseline

The complete Investment Canada historical backfill was production-validated on 2026-09-18:

- 681 paginated source pages across 36 index buckets;
- 32,369 deduplicated historical outcome records;
- coverage from 1984-04 through 2026-07;
- 5,507 EU-27 records;
- 1,706 deduplicated EU-27 new-business outcomes;
- 100% investor source-node coverage in the accepted corpus.

See [INVESTMENT_CANADA_HISTORY_VALIDATION.md](INVESTMENT_CANADA_HISTORY_VALIDATION.md).

## Outcome definition

The initial positive outcome is:

- Investment Canada Act
- Country of ultimate control is an EU-27 member
- Notification type is `Notification - new business`

Acquisitions are retained but treated as a separate outcome class.

These are notification labels, not yet validated first-entry labels. A company may already have Canadian operations before a new-business notification. Before a record enters a first-entry evaluation, audit its prior Canadian presence, the meaning of the notified business event, and the public availability dates of candidate signals. Incorporation, amalgamation and continuance dates are distinct from first-operation dates. Unresolved cases are excluded from model eligibility, not relabelled as negative outcomes.

## First analysis design

1. Ingest the complete paginated Investment Canada historical index and deduplicate source views using stable source node IDs.
2. Isolate EU-27 investors and classify new-business vs acquisition outcomes.
3. Resolve investors to durable company identities.
4. For each positive company, reconstruct signals available 3, 6, 12 and 24 months before the outcome month.
5. Construct comparable EU control companies that did not enter Canada in the same observation window.
6. Measure signal prevalence and lead time.
7. Only then define Expansion Score 1.0.

## Candidate pre-entry signals

- Canadian federal corporation created or changed
- Canadian trademark application
- Canadian patent/public IP activity
- Canadian procurement tender/award
- Horizon/CORDIS relationship with a Canadian organization
- Canadian hiring
- Canadian distributor/partner announcement
- Canada-specific website/localization
- Canadian acquisition
- Investment Canada notification

## Required evaluation outputs

For every candidate signal:

- source coverage
- false-positive rate
- false-negative rate
- median lead time before entry
- p25/p75 lead time
- prevalence among entrants
- prevalence among controls
- identity-match confidence
- source availability over historical time

## Audited outcome cohorts

The current 27-case outcome audit is partitioned separately from the canonical source classifications so prior-presence cases are not mixed with plausible new-entry cases. See [OUTCOME_COHORTS.md](OUTCOME_COHORTS.md).

The current partition contains seven `TRUE_NEW_ENTRY_CANDIDATE` rows suitable for censored matching research, but **zero** confirmed training-positive labels.

## Score separation

Three values remain independent:

1. **Expansion Likelihood** — probability/strength of Canadian expansion evidence.
2. **Nova Scotia Fit** — how well the company matches Nova Scotia's non-military commercial clusters and infrastructure.
3. **Evidence Confidence** — confidence in source coverage and entity resolution.

No missing source is scored as a negative signal.
