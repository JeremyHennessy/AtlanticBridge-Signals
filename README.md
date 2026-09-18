# AtlanticBridge Signals

AtlanticBridge Signals is a source-backed commercial intelligence system for detecting European companies that are likely to establish, acquire, hire, invest, partner, or materially expand in Canada — and then estimating whether Nova Scotia is a strong landing location.

## Current phase: Data Proof

The first releases intentionally prioritize source proof over UI. The core question is:

> Can public signals identify European companies before they enter Canada?

The first outcome source is the **Investment Canada Act Decisions and Notification Index**, which provides explicit historical `Notification - new business` labels. Forward-looking evidence now includes daily **Corporations Canada** change detection and the **CORDIS Horizon Europe** project graph linking Canadian organizations to European partners.

### Principles

- Expansion likelihood and Nova Scotia fit are separate models.
- Evidence confidence is separate from either score.
- No score is accepted without source-backed evidence.
- Raw source text is preserved before normalization.
- Historical predictive value is measured before weights are assigned.
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
  --buckets all

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
```

## Implemented

- SQLite evidence/provenance store
- Investment Canada historical outcome collector
- EU-27 normalization
- Corporations Canada daily active-business streaming collector
- Corporations Canada baseline/diff event detection
- CORDIS Horizon project/participation relationship graph
- Canada ↔ EU-27 shared-project coverage summaries
- source snapshots with SHA-256 hashes
- deterministic record IDs/hashes
- unit tests and live source checks

## Next source sequence

1. GLEIF — legal-entity and parent-company resolution
2. TED — EU procurement/commercial maturity
3. CIPO trademarks — pre-entry Canadian market intent
4. CanadaBuys — Canadian procurement activity
5. Statistics Canada trade — sector/geography context

See [docs/DATA_PROOF.md](docs/DATA_PROOF.md) and [docs/SOURCE_REGISTRY.md](docs/SOURCE_REGISTRY.md).
