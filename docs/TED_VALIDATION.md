# TED Contract-Award Validation

Validation date: **2026-09-18**

## Purpose

Validate the production TED Search API v3 ingestion path and quantify how often winner identity fields can be safely aligned without guessing across independent arrays.

## Request contract

Production retrieval uses:

- `POST https://api.ted.europa.eu/v3/notices/search`
- search scope `ALL`
- page-number pagination
- page size 250
- `checkQuerySyntax: false`
- contract-award notice types
- `winner-selection-status IN (selec-w)`

During source probing, the same valid historical query returned no notice payload when `checkQuerySyntax: true`. Changing only that flag to `false` returned normal results. The production implementation encodes the working contract and tests it.

## Live production acceptance

Tested publication window:

- start date: **2024-01-25**
- end date: **2024-01-25**
- scope: **ALL**

Production CLI:

```bash
python -m atlanticbridge ingest-ted-awards \
  --db ted-live.sqlite \
  --start-date 2024-01-25 \
  --end-date 2024-01-25 \
  --scope ALL \
  --page-size 250

python -m atlanticbridge summarize-ted --db ted-live.sqlite
```

Observed result:

- TED-reported notices: **618**
- notices returned and stored: **618**
- search runs: **1**
- winner mentions: **957**
- distinct normalized winner names: **933**
- `SINGLE_WINNER_ALIGNED` mentions: **367**
- `NAME_ONLY_UNALIGNED` mentions: **590**
- query SHA-256: `4e44636b37e99e814677049455af3d9e80ea1922d9f0b57b419e72aafedd6e26`
- response SHA-256: `9796ff51ba6776163d4191196e871b74f52222b44812b65f15df2543cd7c87d5`

Notice types in the validated window:

| Notice type | Notices |
|---|---:|
| can-standard | 589 |
| can-social | 24 |
| can-desg | 5 |

The largest safely aligned winner-country counts included Germany (100), France (73), Spain (49), Poland (20), Latvia (19), Netherlands (16), Estonia (14), and Slovenia (11).

## Winner-alignment boundary

TED exposes winner names as a multilingual map while winner country, identifier and decision-date fields are separate arrays.

AtlanticBridge does **not** assume those structures share positional alignment.

A winner mention is marked `SINGLE_WINNER_ALIGNED` only when a notice contains:

1. exactly one unique normalized winner name;
2. no more than one winner country;
3. no more than one winner identifier; and
4. no more than one winner decision date.

All other winner names are stored as `NAME_ONLY_UNALIGNED`. Their source arrays remain preserved in the notice record for future evidence-based reconciliation.

## Acceptance result

The production client paginated through the complete tested result set and persisted all 618 notices. The stored notice count matched TED's reported count exactly. No multi-winner field alignment was inferred.
