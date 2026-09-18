# CanadaBuys Award Validation

Validation date: **2026-09-18**

## Purpose

Validate the production CanadaBuys current-fiscal-year award collector and establish the amount of direct EU-27 supplier evidence currently visible in the official federal award feed.

## Source

Current official award notice CSV:

`https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv`

Observed source evidence:

- bytes: **14,079,894**
- SHA-256: `2912c321aed256b9a47122771b726dfecbd69f649ddfdc6c6f69e0c2e52986cd`
- columns: **80**
- records: **3,925**
- duplicate `(referenceNumber, amendmentNumber)` keys: **0**

The public file endpoint requires the public session established by the CanadaBuys procurement-data page. The production collector reproduces that session flow and does not use credentials.

## Production acceptance

Commands exercised:

```bash
python -m atlanticbridge ingest-canadabuys-awards --db canadabuys-live.sqlite
python -m atlanticbridge summarize-canadabuys --db canadabuys-live.sqlite
```

Observed production result:

- records stored: **3,925**
- EU-27 supplier award records: **34**
- snapshots: **1**
- stored source bytes/hash exactly matched the downloaded source

EU-27 award-record counts:

| Country | Award records |
|---|---:|
| Ireland | 6 |
| France | 5 |
| Denmark | 4 |
| Spain | 4 |
| Germany | 3 |
| Netherlands | 3 |
| Belgium | 2 |
| Austria | 1 |
| Greece | 1 |
| Hungary | 1 |
| Italy | 1 |
| Latvia | 1 |
| Romania | 1 |
| Sweden | 1 |

Examples of direct current supplier evidence include:

- VMware International Unlimited Company — Ireland
- LinkedIn Ireland Unlimited Company — Ireland
- Elsevier B.V. — Netherlands
- Becker Marine Systems GmbH — Germany
- Black Bull Logistics S.L. — Spain
- Bruhn NewTech A/S — Denmark

These are source records, not entity-resolution decisions and not evidence by themselves that the supplier intends to establish a Canadian business.

## Source boundaries

Supplier country values are inconsistent in the source (for example `CA`, `Canada`, `CANADA`; `US`, `USA`, and full names). AtlanticBridge preserves the raw value and stores a normalized country separately.

The primary record key is the observed unique pair:

`(referenceNumber, amendmentNumber)`

The parser fails closed on duplicate keys or a changed 80-column schema.

## Non-military product scope

CanadaBuys is a broad federal procurement source and can contain military/defence procurement among unrelated commercial records.

AtlanticBridge preserves source records losslessly for evidence integrity, but **military/defence records are outside the product scope and must not contribute to Expansion Likelihood, Nova Scotia Fit, opportunity ranking, or customer-facing commercial recommendations.**

A dedicated classification/exclusion control must be applied before CanadaBuys evidence is used in scoring or product surfaces.

## Acceptance result

The production collector downloaded, parsed, stored, and summarized the complete current source snapshot. The stored record count, byte count and source hash matched the independently probed source exactly.
