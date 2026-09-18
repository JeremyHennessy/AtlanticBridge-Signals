# AtlanticBridge Signals

AtlanticBridge Signals is a source-backed commercial intelligence system for detecting European companies that are likely to establish, acquire, hire, invest, partner, or materially expand in Canada — and then estimating whether Nova Scotia is a strong landing location.

## Current phase: Data Proof 001

The first release is intentionally not a UI build. It establishes the historical outcome dataset needed to answer a more important question:

> Can public signals identify European companies before they enter Canada?

The first implemented source is the **Investment Canada Act Decisions and Notification Index**, which provides historical labels for foreign investment activity including explicit `Notification - new business` outcomes.

### Principles

- Expansion likelihood and Nova Scotia fit are separate models.
- Evidence confidence is separate from either score.
- No score is accepted without source-backed evidence.
- Raw source text is preserved before normalization.
- Historical predictive value is measured before weights are assigned.
- Failed or unavailable sources remain unverified; they never become zero.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .

python -m atlanticbridge init-db --db data/atlanticbridge.sqlite
python -m atlanticbridge ingest-investment-canada --db data/atlanticbridge.sqlite --buckets all
python -m atlanticbridge summarize-investment-canada --db data/atlanticbridge.sqlite
```

## Implemented

- SQLite evidence store with provenance and idempotent ingestion
- EU-27 country normalization
- Investment Canada Act index fetch/parser
- new-business and EU-27 outcome labels
- source snapshots with SHA-256 hashes
- deterministic summary command
- unit tests and CI

## Next source sequence

1. Corporations Canada — Canadian subsidiary formation/change signals
2. CORDIS — EU company ↔ Canadian research/innovation relationships
3. GLEIF — legal-entity and parent-company resolution
4. TED — EU procurement/commercial maturity
5. CIPO trademarks — pre-entry Canadian market intent
6. CanadaBuys — Canadian procurement activity
7. Statistics Canada trade — sector/geography context

See [docs/DATA_PROOF.md](docs/DATA_PROOF.md) and [docs/SOURCE_REGISTRY.md](docs/SOURCE_REGISTRY.md).
