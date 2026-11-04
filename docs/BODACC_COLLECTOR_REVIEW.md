# BODACC bounded collector candidate

Status: source and schema reviewed; candidate code and fixture tests added; **live API request not verified**, so do not treat this collector as operational. Reviewed 4 November 2026.

## Why this source

The French government data service says its BODACC API is free, open access, and subject to Licence Ouverte 2.0 and the API's terms. The official API page links a BODACC dataset with about 51 million notices, supports query filtering and JSON, and documents the published fields used here. The dataset includes company creation, registration, modification, cessation, insolvency and filing notices. Some notices may contain personal data; the collector therefore requests a minimal field list and retains no free text or person/address fields.

Sources:
- API access, license, scope and terms: https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-civiles-et-commerciales-bodacc
- Dataset description and current schema fields: https://bodacc-datadila.opendatasoft.com/explore/dataset/annonces-commerciales/information/
- API v2.0 records and ODSQL documentation: https://help.opendatasoft.com/apis/ods-explore-v2/explore_v2.0.html

The data.gouv.fr listing says API availability and call limits are not documented. That source-specific documentation and the API terms still need review before any recurring or production use.

## Bounded ingestion contract

The branch adds `collect-bodacc-context`, a manual CLI candidate that accepts one verified nine-digit SIREN and a required lower bound for publication date. It makes one GET request, asks for no more than 100 rows, does not paginate or retry, caps the response at 5 MB, and never writes to the application database or production state.

The collector keeps only record ID, SIREN, bulletin edition, publication date, notice type/family, official notice URL, publication-age label, collector retrieval time, exact query URL, and SHA-256 of the selected-field response. It rechecks SIREN equality and the lower publication-date bound locally and rejects non-official result URLs or response-shape drift. The envelope says whether more API query results exist; it does not claim the locally exact SIREN subset is complete. Output says explicitly that a bounded zero-result query is not proof of absence. Results are French corporate-event context; they do not establish Canadian operations, expansion intent, a site-selection mandate or market fit.

Freshness labels refer only to the notice's BODACC publication date relative to `retrieved_at`. They do not measure dataset processing lag or prove that the query covered every potentially relevant notice.

## Verification boundary

A one-row API request was attempted from the current execution environment and failed before reaching BODACC because the hostname could not be resolved (`HttpRequestException: No such host is known`). A bounded query from the branch runner reached the API and its six offline tests passed, but the collector rejected the live `registre` field because it was not a scalar. The exact live value is not retained; the runner smoke logs only the JSON type. This is a schema integration fix in progress; the collector is not operational until the updated parser and same bounded smoke check pass. The tests added in `tests/test_bodacc_collector.py` exercise query construction, bounding, exact-SIREN filtering, field minimization, provenance, freshness labels, and fail-closed behavior against fixtures. They do not establish live endpoint compatibility. This environment lacks an installed Python interpreter, so the new Python suite has not been executed here.

The branch contains a push-only GitHub Actions check scoped to this exact working branch. It runs the focused unit tests and makes one one-row public API query without uploading or retaining the response artifact. This check is verification only, not a production schedule. Before calling the collector functional or activating automation, inspect the completed check, confirm the real response shape and exact SIREN match behavior, review the API terms and rate limits, and have an analyst review sample records. Until those steps pass, the registry status remains VERIFY.
