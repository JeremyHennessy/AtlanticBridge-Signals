# Documentary qualification of investment discoveries — 22 September 2026

## Exact preservation checkpoint

User continuation authorized at 20:49:04 UTC. Baseline main is
`0411539cac380bef2c9df6a3ce466a3993736e6b` (PR #103), preserving PR #101
company source contracts and PR #100/#102 UI/worklist acceptance. This package
is six additive files. No existing collector, accepted source manifest, UI,
production payload, historical audit, backtest, dependency or scoring gate changes.

PR #103 was accepted after independently reproducing 319 Python / 28 Node tests,
verifying artifact 10718503237 (SHA-256
`489ab9504befa2bca96c994f6df141c0e53792c2a9cad7cb1cc822f534a15847`), all eight
raw-response hashes across two captures and unchanged first observation clocks.
All pre-existing files were byte-identical to the accepted PR #101 source.

## Actual research deliverable

The existing 71-card source is triaged by its published country label, not
assumed corporate control. Every card is preserved; unknown and mixed labels
remain explicit. Exact names, locations and project descriptions bind six
selected reviews to discovered cards. Any changed binding requires review.

Six projects are checked against eight primary documents: Volkswagen/PowerCo
St. Thomas, Sanofi Toronto influenza, Air Liquide Becancour, The Cultivated B.
Burlington, Klarna Toronto and Avanade Halifax. The manifest records exact URLs,
dates, event-specific literal anchors, interpretation limits and unresolved
legal-identity/first-entry status. Research selection is purposive, not a
representative cohort or an independently selected holdout.

### Distinctions under test

- PowerCo's March 2023 announcement and December 2023 implementation update do
  not establish an operating factory. 2027 is the plan stated then, not an
  independently verified current schedule.
- Sanofi's 2021 influenza announcement and September 16, 2026 Charles Best
  inauguration concern the influenza project. The 2021 source identifies a
  separate diphtheria/tetanus/pertussis facility. Do not use a different facility
  or same-company announcement as its opening evidence. An inauguration is not
  automatically first production; the company release still says will manufacture.
- Air Liquide's January 26, 2021 source reports that the unit is producing at
  an existing complex. That establishes an operating-by upper bound, not an
  exact first-production date or first Canadian group entry.
- The Cultivated B. announces an October 27, 2022 opening while describing the
  ceremony in future tense. It is not independent proof the ceremony occurred.
- Klarna's February 2022 release reports service availability and a Toronto hub;
  planned hiring is not actual job creation or proof of first Canadian presence.
- Avanade's dated June 28, 2022 agency subsection reports an established Halifax
  office. Qualification uses only that subsection, not other companies on the
  annual page. Conditional payroll-agreement job counts are not realized jobs.

## Reproduction

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
node --test tests/test_workspace.cjs
python scripts/probe_outcome_qualification.py \
  --output artifacts/outcome-qualification --state data/qualification.sqlite
```

The script reuses the accepted raw Capture, article/card parsers and Ledger.
It retains raw responses, hashes, both source dates and first/last observations.
Missing documents, dates, names, event anchors or required subsection boundaries
block qualification. Retrieval failures remain unverified and never become zero.
It does not weaken robots or network restrictions to pass a source.

The independent workflow collects twice on one ledger. On a disposable copy of
that ledger it also injects an incomplete snapshot, an empty success window and
a process restart, then replays the actual captured records. Failed snapshots
must leave the database unchanged, old records must not reappear as new, and
original observation dates must survive. The real retained ledger is untouched
by fault injection. This is a tested recovery path, not sustained production
monitoring. Artifacts expire after 90 days unless independently retained.

## Qualification and publication boundaries

PRIMARY_DOCUMENTS_CHECKED_LEGAL_IDENTITY_PENDING means precisely that. Source
asserted legal names are retained but not promoted into approved legal identities.
Scope review concerns the specific civilian project, not all company activities;
existing military-review holds are not overridden. Historical references do not
establish today's project status. No absence, probability, validated lead time,
first-operation date or realized job/investment figure is invented.

The six reviews improve the outcome research queue. They do not satisfy the
100/200 cohort targets, independent holdout, source-reuse approvals, durable
scheduled monitoring or paid-pilot acceptance gates. All new public-alert and
backtest-eligibility flags remain false. Issue #104 tracks the remaining work.

## Rollback

Revert only the additive qualification commit. Retain its artifact/ledger before
removing code. No production data restoration or UI rollback is needed.
