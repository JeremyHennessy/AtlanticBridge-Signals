# AtlanticBridge Signals

AtlanticBridge Signals is a source-backed commercial intelligence system for detecting European companies that are likely to establish, acquire, hire, invest, partner, or materially expand in Canada — and then estimating whether Nova Scotia is a strong landing location.

## Current phase: Data Proof

The first releases intentionally prioritize source proof over UI. The core question is:

> Can public signals identify European companies before they enter Canada?

The first outcome source is the **Investment Canada Act Decisions and Notification Index**, which provides explicit historical `Notification - new business` labels. Forward-looking evidence now includes daily **Corporations Canada** change detection, the **CORDIS Horizon Europe** project graph linking Canadian organizations to European partners, a conservative **GLEIF candidate-resolution layer** for legal-entity identity, **TED** contract-award evidence for commercial maturity, targeted **CIPO** trademark ownership/filing evidence, **CanadaBuys** federal award/supplier evidence, and **Statistics Canada** Nova Scotia/EU trade context.

### Principles

- Expansion likelihood and Nova Scotia fit are separate models.
- Evidence confidence is separate from either score.
- No score is accepted without source-backed evidence.
- Raw source text is preserved before normalization.
- Historical predictive value is measured before weights are assigned.
- A notification month is not a verified first-operation date. Federal timing is reported against the notification month only.
- Identity confirmation is separate from model eligibility; historical outcome and evidence-availability review are still required.
- Failed or unavailable sources remain unverified; they never become zero.
- Source absence is not interpreted as a negative event without completeness proof.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

python -m atlanticbridge init-db --db data/atlanticbridge.sqlite

# Historical outcome labels
python -m atlanticbridge ingest-investment-canada \
  --db data/atlanticbridge.sqlite \
  --history

# First federal-corporation snapshot
python -m atlanticbridge ingest-corporations-canada \
  --db data/atlanticbridge.sqlite \
  --mode baseline

# On subsequent source updates
python -m atlanticbridge ingest-corporations-canada \
  --db data/atlanticbridge.sqlite \
  --mode diff

# Monthly EU-Canada Horizon relationship snapshot
python -m atlanticbridge ingest-cordis \
  --db data/atlanticbridge.sqlite
python -m atlanticbridge summarize-cordis \
  --db data/atlanticbridge.sqlite

# Resolve a bounded batch of CORDIS source identities to GLEIF candidates
python -m atlanticbridge resolve-cordis-gleif \
  --db data/atlanticbridge.sqlite \
  --limit 50

python -m atlanticbridge summarize-gleif \
  --db data/atlanticbridge.sqlite

# EU contract-award evidence for a bounded publication window
python -m atlanticbridge ingest-ted-awards \
  --db data/atlanticbridge.sqlite \
  --start-date 2024-01-25 \
  --end-date 2024-01-25

python -m atlanticbridge summarize-ted \
  --db data/atlanticbridge.sqlite

# Current CIPO owner search + bounded detail enrichment
python -m atlanticbridge ingest-cipo-owner \
  --db data/atlanticbridge.sqlite \
  --owner "Siemens Aktiengesellschaft" \
  --detail-limit 10

python -m atlanticbridge summarize-cipo \
  --db data/atlanticbridge.sqlite

# Current CanadaBuys fiscal-year federal award notices
python -m atlanticbridge ingest-canadabuys-awards \
  --db data/atlanticbridge.sqlite

python -m atlanticbridge summarize-canadabuys \
  --db data/atlanticbridge.sqlite

# Aggregate Nova Scotia/Canada EU trade context
python -m atlanticbridge ingest-statcan-trade \
  --db data/atlanticbridge.sqlite \
  --source both

python -m atlanticbridge summarize-statcan-trade \
  --db data/atlanticbridge.sqlite

# Resolve recent positive outcomes to federal Canadian entry entities
python -m atlanticbridge resolve-entry-identities \
  --db data/atlanticbridge.sqlite \
  --start-month 2019-01 \
  --end-month 2025-12 \
  --gold-limit 100

python -m atlanticbridge summarize-entry-identities \
  --db data/atlanticbridge.sqlite

# Resolve named foreign investors and GLEIF accounting-parent evidence
python -m atlanticbridge resolve-foreign-identities \
  --db data/atlanticbridge.sqlite

python -m atlanticbridge summarize-foreign-identities \
  --db data/atlanticbridge.sqlite

# Build a stable audited queue for unresolved named investors / parents
python -m atlanticbridge build-curated-identity-queue \
  --db data/atlanticbridge.sqlite

python -m atlanticbridge summarize-curated-identity \
  --db data/atlanticbridge.sqlite

# Apply reviewed primary-source evidence/decisions
python -m atlanticbridge apply-curated-identity-review \
  --db data/atlanticbridge.sqlite \
  --file review.json
```

## Implemented

- SQLite evidence/provenance store
- Investment Canada historical outcome collector
- EU-27 normalization
- Corporations Canada daily active-business streaming collector
- Corporations Canada baseline/diff event detection
- CORDIS Horizon project/participation relationship graph
- Canada ↔ EU-27 shared-project coverage summaries
- GLEIF legal-entity candidate search with explicit ambiguous/review-ready states
- TED contract-award notices with conservative winner alignment
- CIPO current-owner trademark search with explicit detail-enrichment coverage
- CanadaBuys federal award notices with normalized EU-27 supplier evidence
- Statistics Canada monthly major-EU and annual full-EU trade context for Nova Scotia + Canada benchmarks
- Federal entry-entity resolution using active + inactive Corporations Canada legal names
- Official federal corporation detail verification and notification-relative certificate timing
- Reviewable federal entry-entity gold cohort
- Named-investor legal-entity resolution requiring exact legal name + source locality, with Canadian and foreign entities separated
- GLEIF direct/ultimate accounting-parent relationship or reporting-exception evidence
- Persistent curated identity-review queue with primary-source evidence and audited decisions
- source snapshots with SHA-256 hashes
- deterministic record IDs/hashes
- unit tests and live source checks

## Next source sequence

1. Audit notification outcomes against actual Canadian presence and resolve flagged identity-evidence gaps
2. Obtain authorized provincial registry access for unresolved non-federal entry entities
3. Historical CIPO bulk backfill once secure bulk transport is available
4. Build matched non-entrant controls and event-time backtests on confirmed identities before any score weights

See [docs/DATA_PROOF.md](docs/DATA_PROOF.md) and [docs/SOURCE_REGISTRY.md](docs/SOURCE_REGISTRY.md).

The outcome audit and confirmation-gate changes are documented in [docs/OUTCOME_TIMING_AUDIT.md](docs/OUTCOME_TIMING_AUDIT.md).
