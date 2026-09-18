# Statistics Canada Trade Context Validation

Validation date: **2026-09-18**

## Purpose

Validate the production Statistics Canada trade-context layer used by AtlanticBridge to describe Nova Scotia/Canada market activity without treating aggregate trade as company-specific expansion intent.

## Source design

Two official customs-basis tables are required because no single table provides both monthly provincial timeliness and full EU-country breadth.

### Monthly major EU markets

Statistics Canada table **12-10-0175-01**  
PID: `12100175`

Role:

- monthly trend context
- province/territory
- NAPCS merchandise sections
- imports / domestic exports / re-exports
- six named EU principal trading partners:
  Belgium, France, Germany, Italy, Netherlands, Spain

Live source observed:

- archive bytes: **50,062,431**
- archive SHA-256: `d9ce5cf72b6b15c9da4b8cef16eb25cb3b2068618501abe03ba461060d9b7638`
- full source rows: **3,860,857**
- filtered AtlanticBridge rows: **138,450**
- earliest reference month: **1997-01**
- latest reference month: **2026-07**
- filtered geographies: **Canada, Nova Scotia**
- partner coverage: **6/6**

### Annual full EU-27 markets

Statistics Canada table **12-10-0173-01**  
PID: `12100173`

Role:

- full EU-country breadth by province
- annual trend context
- NAPCS merchandise sections
- imports / exports
- all EU-27 countries

Live source observed:

- archive bytes: **26,815,786**
- archive SHA-256: `f6db51b7a6855859177efc67c1a15d871d70de3b72795c767e62b102956755dc`
- full source rows: **2,545,452**
- filtered AtlanticBridge rows: **37,908**
- earliest reference year: **1999**
- latest reference year: **2025**
- filtered geographies: **Canada, Nova Scotia**
- partner coverage: **27/27**

## Production acceptance

Commands exercised:

```bash
python -m atlanticbridge ingest-statcan-trade \
  --db statcan-live.sqlite \
  --source both

python -m atlanticbridge summarize-statcan-trade \
  --db statcan-live.sqlite
```

The production collector:

1. resolved both full-table download URLs through the official Statistics Canada WDS;
2. downloaded and hashed both ZIP archives;
3. validated the exact observed 17-column schemas;
4. scanned more than six million source rows;
5. transactionally replaced current AtlanticBridge rows;
6. retained only Canada/Nova Scotia + applicable EU partner rows;
7. preserved raw selected rows, statuses, symbols and source values;
8. produced separate monthly and annual summaries.

## Example current context

These examples are **aggregate market context**, not company signals.

July 2026 Nova Scotia total-merchandise imports:

- Germany: **$381.186M**, +35.89% vs July 2025
- France: **$48.208M**, +87.54%
- Italy: **$30.208M**, +35.24%
- Netherlands: **$28.399M**, -7.45%
- Spain: **$19.620M**, +166.94%
- Belgium: **$54.310M**, +10.99%

July 2026 Nova Scotia domestic exports:

- Germany: **$5.749M**, -38.17% YoY
- France: **$6.648M**, -51.87%
- Italy: **$4.364M**, -13.43%
- Netherlands: **$6.554M**, -24.22%
- Spain: **$3.204M**, -42.72%
- Belgium: **$5.219M**, -3.33%

The annual table provides the corresponding full-country coverage for all EU-27 markets.

## Interpretation boundaries

Statistics Canada values are contextual market evidence only.

They must **not**:

- create a company Expansion Likelihood signal by themselves;
- be interpreted as a specific company entering Canada;
- substitute for entity-level evidence;
- be combined across monthly/annual tables as though their trade definitions and cadence were identical.

Annual exports remain distinct from monthly domestic exports.

The source publishes these dollar series with a scalar factor of thousands. AtlanticBridge preserves the published value and derives a CAD amount for summaries.

## Non-military scope

The broad NAPCS sections:

- `Aircraft and other transportation equipment and parts [C21]`
- `Special transactions trade [C23]`

are preserved for source integrity but are explicitly excluded from future scoring. The categories are too broad to reliably isolate non-military commercial activity.

## Acceptance result

The production ingest completed successfully. Both source hashes and byte counts were captured, both coverage gates passed, all 27 EU countries are present in the annual context layer, and no aggregate trade data was promoted into a company-level expansion signal.
