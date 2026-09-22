# Independent outcome discovery extension — 22 September 2026

## Preserved accepted state

Base: `c5d251938e781b6eb445a74b3882bcd4cdd42521` (PR #101), including
PR #100's company dossiers/worklist and PR #102's hosted timing test correction.

The parallel company-source package was independently checked before reuse:
its exact exported repository passes all 303 Python tests, and artifact
`10717489758` has SHA-256
`003c42f02705066074a87bc5cac33ac0c72833d1c4a03bed3b01a1c5b660874a`.
All 17 retained response hashes were independently verified.

This extension reuses `company_sources.record`, `Ledger`, `parse_article` and
`probe_company_sources.Capture`. It introduces no competing collector ledger,
commercial-validation framework or UI. All existing files remain unchanged.
The earlier branch-only exploratory implementation was not promoted because
PR #101 supplied the overlapping capability while this work was in progress.

## Additional primary-source evidence

1. **Invest in Canada investment cards:** 71 records observed in the bounded
   current `/news` page. Desktop/mobile controls are reconciled against unique
   source card IDs; missing or duplicate cards fail the source instead of
   turning an incomplete response into an apparently complete cohort.
2. **Vonage Canadian product availability announcement:** company page dated
   30 June 2026, observed 22 September. It identifies Vonage as part of Ericsson.
   This is an additional calibration example, not a first-office or first-entry
   label. The source's asserted June date does not prove historical availability
   from a September capture.

Initial rights-aware raw probe: workflow `35779853056`, artifact `10717906195`.
Both paths allowed the actual collector user agent in the retrieved robots
policies and returned HTTP 200. Runtime collection checks policies again.
Public access/robots permission is not commercial redistribution approval.

Initial exact source hashes:

- Investment page: `43e40cb9bd8e5d825edf89e217e6735949281f9e8c4178fa493d2987de54b1ee`
- Vonage article: `7d8cd3d93ebe6e723d18044606e83a8f8ab2f41c6115703d151ff26a69a96ceb`

The agency dataset includes source-country labels for Germany, France, Sweden,
Ireland, Netherlands, Denmark, Italy, the UK, Switzerland, Norway and multiple
non-European origins. Mixed origin labels remain mixed. None is silently treated
as confirmed EU-27 corporate control. Sector scope, legal identity, prior
Canadian presence and event timing remain required case-level reviews.

Amounts and job counts are retained as source-published strings, **not** verified
realized expenditure or jobs created. Undated cards retain unknown publication
and outcome dates. All 71 remain unreviewed discovery candidates, with zero
confirmed first-entry labels and zero independent holdout rows.

## Reproduction and outputs

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
node --test tests/test_workspace.cjs
python scripts/probe_investment_discovery.py \
  --state data/outcome-discovery.sqlite \
  --output artifacts/investment-discovery
```

The CLI writes retained raw responses, a report, a source-local observation
ledger and `outcome-review-queue.json`. Passing the same `--state` preserves first
observations across calls; first capture and exact replay are quiet baselines.
Every snapshot is validated completely before the accepted ledger is updated.
Source failures remain explicit and do not erase previous source evidence.

The isolated proof workflow performs two live collections using one ledger,
checks all response hashes and retains the tested source plus outputs for 90
days. It does not deploy a new feed, run the heavy historical CIPO scan, or
replace the production evidence payload.

## Acceptance boundary

Before remote acceptance, the integrated local package passes **319 Python
tests**, including **16 additional investment-discovery tests** beyond PR #101.
The existing 28 Node worklist tests are included in the independent workflow.
The remote proof must pass from the exact PR head before merge.

The 71 records are an actual research queue, not fulfillment of the proposed
100 independently audited outcomes / 200 comparison companies. The additional
company article is not an independent holdout. Existing paid-pilot enrollment,
reviewed metrics, sustained monitoring and predictive-publication gates remain
unchanged and incomplete. No accuracy or commercial viability is claimed.

## Next source/value gates

Qualify the discovered companies and outcome types against primary documents;
separate announcements, openings, acquisitions, product availability and prior
presence. Then construct eligible matched groups and a predeclared holdout.
Broaden source/industry/province coverage based on incremental useful leads,
not raw record counts. Production storage, recurring retention, editorial
approval, legal-entity joins and source rights must precede public feed release.

## Export-clock correction found during artifact review

The initial export attached the current capture timestamp under a first-proof
label. The accepted export instead reads committed payloads from the existing
ledger, preserving `first_observed_at`, `last_observed_at` and raw provenance.
Regression tests require unchanged first observation after a second capture and
reject uncommitted records. No existing ledger or historical clock was changed.
