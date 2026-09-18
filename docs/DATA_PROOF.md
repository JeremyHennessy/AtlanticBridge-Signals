# Data Proof 001

## Question

Can public evidence detect European companies before they establish a Canadian business?

The project will not publish an Expansion Score until this is tested historically.

## Outcome definition

The initial positive outcome is:

- Investment Canada Act
- Country of ultimate control is an EU-27 member
- Notification type is `Notification - new business`

Acquisitions are retained but treated as a separate outcome class.

## First analysis design

1. Ingest historical Investment Canada records.
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

## Score separation

Three values remain independent:

1. **Expansion Likelihood** — probability/strength of Canadian expansion evidence.
2. **Nova Scotia Fit** — how well the company matches Nova Scotia's non-military commercial clusters and infrastructure.
3. **Evidence Confidence** — confidence in source coverage and entity resolution.

No missing source is scored as a negative signal.
