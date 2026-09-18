# Investment Canada Historical Backfill Validation

Validation date: **2026-09-18**

## Purpose

Establish a complete, deduplicated historical outcome corpus from the Investment Canada Act Decisions and Notification Index before any AtlanticBridge predictive weights are defined.

The earlier first-page collector was suitable only as a live source smoke test. It returned 50 rows from the current page and was not a historical corpus.

## Official source coverage

AtlanticBridge validated and crawled all **36 alphanumeric investor index buckets**:

- `0` through `9`
- `a` through `z`

The source is paginated at 50 rows per non-terminal page.

Live production acceptance observed:

- buckets: **36**
- pages: **681**
- source row appearances: **33,106**
- duplicate appearances across bucket/page views: **737**
- unique structural records: **32,369**
- page snapshots/hashes stored: **681**
- earliest certification month: **1984-04**
- latest certification month: **2026-07**

## Durable record identity

Page URL and bucket are provenance, not identity.

The historical index can expose the same source record more than once:

- in more than one bucket;
- in more than one page view;
- and, in some cases, repeated within the same rendered page.

Plain display text is also insufficient as an identifier because different source entities can share the same rendered text.

Production identity therefore uses:

1. certification month;
2. notification type;
3. investor Drupal source node ID;
4. normalized country of ultimate control; and
5. ordered Canadian-business source node IDs.

The live validation found investor source node IDs on **32,369 / 32,369** deduplicated records.

The crawler fails closed if:

- a non-terminal page does not contain the expected 50 rows;
- a historical row lacks an investor node ID;
- a page returns zero rows unexpectedly; or
- two rows resolve to the same structural identity but have different raw content.

No structural-content conflict occurred in the accepted live crawl.

## Outcome cohort

After structural deduplication:

- total unique historical records: **32,369**
- EU-27 records: **5,507**
- EU-27 `Notification - new business` records: **1,706**
- distinct investor source node IDs among EU new-business outcomes: **1,706**

Largest EU new-business cohorts:

| Country | New-business outcomes |
|---|---:|
| France | 583 |
| Germany | 420 |
| Netherlands | 140 |
| Italy | 102 |
| Sweden | 74 |
| Austria | 74 |
| Denmark | 51 |
| Spain | 51 |
| Belgium | 48 |
| Ireland | 35 |
| Finland | 30 |
| Luxembourg | 27 |

The positive cohort spans **1985–2026**.

Recent deduplicated EU new-business counts include:

- 2019: 57
- 2020: 46
- 2021: 42
- 2022: 38
- 2023: 62
- 2024: 57
- 2025: 80
- 2026 through July: 34

## Structured source fields

In addition to preserving the original display text, the production parser now stores:

- investor name;
- investor locality;
- investor source node ID;
- structured Canadian-business records;
- Canadian-business source node IDs;
- source page and bucket;
- canonical extracted record JSON;
- raw record hash;
- first/last observation timestamps.

This provides a defensible input for later entity resolution without reverse-parsing concatenated display text.

## Transactional behavior

The full-history command:

```bash
python -m atlanticbridge ingest-investment-canada \
  --db data/atlanticbridge.sqlite \
  --history \
  --workers 4
```

fetches and validates the complete source before replacing the historical outcome state.

The database replacement is transactional:

- new/changed structural records are upserted;
- stale pre-backfill or no-longer-present records are removed;
- prior `first_observed_at` is preserved for stable records;
- page-level source hashes are stored as provenance;
- any failure rolls back the historical outcome replacement.

The original first-page mode remains available and is still used by CI as a lightweight live-source smoke test.

## Acceptance result

Production run on exact tested head completed successfully with:

- **33,106** appearances fetched;
- **737** duplicate appearances collapsed;
- **32,369** unique records stored;
- **681** source-page snapshots;
- **1,706** deduplicated EU new-business positive outcomes;
- complete investor-node coverage;
- no structural identity conflict.

This establishes a usable historical positive-outcome corpus. It does **not** establish predictive performance by itself.

The next model step is to resolve a time-bounded subset of these historical investors to durable company identities, reconstruct signals that were observable before each outcome month, build comparable controls, and measure lead time / false-positive / false-negative behavior before defining Expansion Score 1.0.
