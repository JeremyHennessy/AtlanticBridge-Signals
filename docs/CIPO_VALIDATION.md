# CIPO Trademark Validation

Validation date: **2026-09-18**

## Purpose

Validate a secure, credential-free current trademark evidence path after the official IP Horizons bulk HTTPS host failed certificate-chain verification from standard GitHub Linux runners.

## Bulk-source limitation

Official quarterly CSV and weekly ST.96 downloads are published from `opic-cipo.ca`.

On 2026-09-18:

- Python/OpenSSL failed with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`
- system `curl` failed with certificate error 60 for the same host
- AtlanticBridge did **not** disable TLS verification

CIPO documents SFTP as another delivery mechanism, but CIPO-issued credentials are required. Historical bulk backfill therefore remains unavailable through an unattended secure path until the web certificate chain is corrected or SFTP credentials are obtained.

## Secure live database contract

The public Canadian Trademarks Database at:

`https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng`

was securely reachable. CIPO's own public JavaScript was inspected to establish the request contract:

1. establish the public search session/cookie;
2. POST JSON to `/cipo/trademark-search/srch`;
3. use `searchfield1 = "ownname"` for current-owner searches;
4. receive JSON with `numFound`, `numReturned`, and `docs`;
5. follow a result `id` to `/cipo/trademark-search/{id}?lang=eng` for detail evidence.

The public UI supports a maximum result return of 5,000. The production collector requests 5,000 and fails closed when the response is incomplete or the result count exceeds that cap.

## Search precision finding

The owner endpoint is **not** an exact legal-name identity lookup.

Live comparisons:

| Query | CIPO results |
|---|---:|
| `Siemens` | 1,876 |
| `Siemens Aktiengesellschaft` | 671 |
| `"Siemens Aktiengesellschaft"` | 668 |

Quoting the legal name therefore does not make the search exact enough to use as identity proof.

## Detail-page evidence

A live detail page for application **2319647** exposed:

- trademark: **Depot360**
- application number: **2319647**
- registration number: **TMA1409253**
- international registration number: **1783639**
- filed date: **2024-02-06**
- registered date: **2026-05-08**
- registered owner: **Siemens Aktiengesellschaft**
- registered-owner country: **Germany**
- EUIPO priority claim: **October 17, 2023**, application **018938623**

This establishes that the current detail route provides the filing/owner evidence needed for the pre-entry signal model.

## Production acceptance

Production CLI:

```bash
python -m atlanticbridge ingest-cipo-owner \
  --db cipo-live.sqlite \
  --owner "Siemens Aktiengesellschaft" \
  --detail-limit 5 \
  --detail-offset 0 \
  --detail-delay-seconds 0.1

python -m atlanticbridge summarize-cipo \
  --db cipo-live.sqlite
```

Observed result:

- search records found: **671**
- search records returned: **671**
- search completeness: **complete**
- search response SHA-256: `8853bfec4fc34f3a3a3e7750cfe9acc6fc2f71c822403d765e96956303a8dcfd`
- detail records requested: **5**
- detail records succeeded: **5**
- detail records failed: **0**
- exact detail-owner matches: **5**
- total detail-enriched records: **5**
- detail enrichment complete: **false**

## Interpretation boundary

The 671-record owner search was complete for the tested query. The five detail records were deliberately only a bounded sample, so the detail layer remains explicitly **partial**.

Search hits alone are candidates. `EXACT_DETAIL_OWNER` is emitted only when the normalized owner on the detail page exactly matches the owner query.

A CIPO filed date is evidence of a Canadian trademark record. For Madrid Protocol records, AtlanticBridge also preserves the international-registration date and priority claims and does not mislabel the record as a direct Canadian national filing without additional source evidence.

No CIPO score weight has been assigned yet.
