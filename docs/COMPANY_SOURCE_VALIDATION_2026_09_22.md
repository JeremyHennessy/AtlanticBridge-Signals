# Company-source and commercial-validation package — 22 September 2026

## Authorization and preservation checkpoint

The user authorized the source-expansion and commercial-validation work on 2026-09-22 at 20:03 UTC. Starting main is `c522a167684308188ae4a0a64d6dc9035ef3ecda`, tree `82c325593ac9a50e6f74985f85784095be91c8ad`. Work is isolated on `feature/company-source-validation-20260922`.

PR #100 separately owns the company dossier and analyst worklist. This package does not change its files, the approved UI, `ui/data`, existing source collectors, dependencies, historical identity approvals, outcome reviews, backtests, score weights, or publication gates. Original evidence remains immutable. No claim of hosted visual acceptance is made for this backend-only package.

## What is implemented

- Public Greenhouse and Ashby job-board parsers, with ATS identity discovered only from actual links/embeds on the manifest's reviewed official careers page.
- Bounded official announcement-index, article and RSS/Atom parsers.
- A separate persistent SQLite observation ledger. Initial collection is a quiet baseline; new source-local records and material revisions enter a review queue, not the public alert feed.
- Raw HTTP response capture, SHA-256 verification, reviewed-host HTTPS allowlisting, bounded requests and robots.txt enforcement.
- Three documentary calibration cases illustrating announced first establishment, expansion of an established Canadian business, and a membership milestone.
- Validation diagnostics for corporate-group leakage, post-hoc holdouts, unsupported absence labels, historical availability, reviewer denominators and incremental usefulness.
- An independent source-proof workflow, leaving expensive historical proofs and production builds unchanged.

Parser support is not proof of live availability. The initial manifest tests six specific paths at Mistral AI, Montreal International and Payments Canada. Only Mistral's careers page is selected for the initial live ATS binding. Greenhouse and RSS/Atom support is initially fixture-tested; neither should be advertised as live-proven without its own successful source proof.

## Source clocks and identity boundaries

Greenhouse's list `updated_at` is not an original publication timestamp. Ashby's `publishedAt` is the last publication time, not necessarily the first posting. Atom `updated` is not substituted for `published`. An article date currently visible on a webpage does not establish that an identical record was publicly available before an old backtest cutoff.

Official API references reviewed on 2026-09-22:

- Greenhouse Job Board API: https://docs.greenhouse.io/job-board.html
- Ashby public job posting API: https://developers.ashbyhq.com/docs/public-job-posting-api

Canada relevance for job records uses location/title, not generic worldwide company-description text. Remote Canadian work does not establish an office. Source-local brands and named subsidiaries are not automatically promoted to reviewed foreign legal identities or joined to an existing research company.

The manifest's agency news index contains companies from multiple origins. Those records remain discovery candidates until the existing EU-27, civilian-scope and legal-identity requirements are independently satisfied. Geographic keyword rules are candidate filters, not exhaustive geographic classification. A military-text hold is a conservative review exclusion, not an assertion about an entire company.

## Baseline, outage and replay contract

Keep the same `--state` database across actual monitoring runs. The first successful source collection records a baseline and emits no changes. Later new records are labelled `NEWLY_OBSERVED_RECORD`, never automatically newly published; material revisions are `RECORD_CHANGED`. All are review-required with `public_alert_allowed=false`.

A failed download or parser never replaces the previous successful source state. An empty page/window does not delete remembered record identities, so disappearance/reappearance does not create false new events. Updated-at-only changes are ignored. A changed source identity/contract, backwards observation clock, duplicate key or future-dated publication fails closed. Each successful source update is transactional; exact replay must emit no additional event.

The isolated proof workflow starts its own ledger unless an existing state path is explicitly supplied. It does not establish ongoing scheduled monitoring or production persistence. Its raw responses, report and ledger are retained as a workflow artifact for 90 days, not as a permanent historical archive.

## Run and inspect

```bash
python -m pip install -e .
python -m unittest tests.test_company_sources tests.test_commercial_validation -v
python scripts/check_commercial_validation.py
python scripts/probe_company_sources.py --output artifacts/company-sources
# Subsequent local/manual collection using the retained baseline:
python scripts/probe_company_sources.py --output artifacts/company-sources-next \
  --state artifacts/company-sources/observations.sqlite
```

The live proof records per-source results and preserves all fetched raw bytes before normalization. Any requested-source failure returns a non-zero exit status; other sources are still attempted and their diagnostics retained. Source failures remain unverified, not zero records. Schema and raw-evidence failures must be repaired in the failing layer, not hidden by changing success thresholds.

Public accessibility and robots permission are not commercial reuse approval. Broad production coverage requires a separate rights/access decision for each source, appropriate retention, operational scheduling and durable storage. The proof does not bypass authentication, access restrictions or TLS verification.

## Calibration, not validation

The initial examples are:

1. Mistral AI's Montreal announcement, published 2026-06-25: an announced first establishment; no independently verified operational opening date.
2. Giesecke+Devrient's Montreal announcement: announced 2026-06-16 and published 2026-06-17; the source explicitly describes Canadian presence since 1962. It is not first Canadian entry.
3. Adyen Canada Ltd.'s Payments Canada membership, published 2026-07-14: a membership milestone, not incorporation, first operation or independently verified foreign-parent identity.

Exact source URLs and review qualifications are in `reviews/commercial_validation/calibration-outcomes-2026-09-22.json`. These already inspected, assistant-curated examples are not an independent holdout and do not increase any accepted historical backtest denominator. Source-publication date and operational opening remain separate fields.

The plan targets 100 development outcomes, 200 matched comparisons and a prospective 300–500-company workflow pilot with 3–5 users. Those are research targets, not completed recruitment. No pilot reviews or confirmatory cohort are invented. Six to eight weeks can evaluate workflow usefulness and monitoring reliability, not a twelve-month forecast. The design file is expressly a development plan, not a confirmatory preregistration.

Before claiming a viable predictive product, collect independent identity/outcome review, preserve matched strata, freeze a primary comparison before independent evaluation, retain contemporaneous source evidence, test against announcement-only/CIPO-only/human-research baselines, and observe actual customer value and paid commitment. Use reported sample sizes and uncertainty, not point thresholds alone.

## Rollback and next promotion gate

This is additive research infrastructure. Revert its isolated commit(s) to remove the code; preserve exported raw evidence and any observation ledger before removing files. No approved production data or UI restoration is required because they are not modified here.

Promotion into the live product requires a reviewed identity binding, reviewed scope, source-rights decision, evidence-quality acceptance, persistent monitoring, and an explicitly tested feed integration with PR #100's contract. That integration is not silently included in this source proof. Expansion Score publication remains blocked regardless of any diagnostic result from this package.
