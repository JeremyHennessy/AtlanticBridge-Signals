# BODACC bounded collector candidate

Status: collector passed focused contract tests and one bounded live API smoke query; source-specific terms and production suitability remain under review. Reviewed 4 November 2026.

## Why this source

BODACC is France's official commercial-notice service. The French government data-service listing describes the API as free/open and the data under Etalab Open Licence 2.0, subject to the API's terms. Notices cover dated commercial events such as registrations, modifications, cessations and insolvency. Some notices contain personal data, so this collector requests a minimal field list and discards notice text and personal/address fields.

Sources:
- API access, licence, scope and terms: https://www.data.gouv.fr/dataservices/api-bulletin-officiel-des-annonces-civiles-et-commerciales-bodacc
- Dataset schema: https://bodacc-datadila.opendatasoft.com/explore/dataset/annonces-commerciales/information/
- API v2 records and query documentation: https://help.opendatasoft.com/apis/ods-explore-v2/explore_v2.0.html

The catalogue says API availability and call limits are not documented. Review the endpoint-specific terms and reasonable request limits before recurring use.

## Bounded ingestion contract

The branch adds a manual `collect-bodacc-context` CLI candidate. It requires one verified nine-digit SIREN and publication-date lower bound; requests a single page of at most 100 rows; does not paginate or retry; caps response size at 5 MB; blocks redirects; and never writes to the application database or production state.

It retains a small allowlist of notice metadata, official notice URL, retrieval time, query URL and response hash. It rechecks exact SIREN and date bounds locally, validates official URLs, and fails closed on schema inconsistencies. The output records registry field type(s) as metadata for diagnostics without retaining the raw value. It states when API results have further pages and that a bounded zero-result query is not evidence of absence.

The notices provide French corporate-event context. They do not establish Canadian operations, expansion intent, a site-selection mandate or market fit. Publication-age labels describe the notice's publication date only; they do not measure source processing lag or query completeness.

## Verification

The branch-only workflow passed all nine focused BODACC tests and one bounded live API query on 4 November 2026: SIREN `752461681`, since `2020-01-01`, limit 1. One record was returned and passed exact-SIREN validation. Its `registre` field was a JSON list. The API indicated further results beyond that page. No raw response or notice body was retained in CI artifacts. See [the workflow run](https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/41926479745).

This is one successful request shape, not evidence of completeness, uptime, broader schema coverage or source freshness. The full project suite and hosted browser acceptance were not run on this latest collector head. The local environment could not resolve the BODACC hostname and did not have a working Python interpreter; the branch workflow provided focused test and live-query verification.

The collector remains a manual candidate, not scheduled or wired into production monitoring, the UI or the database. Source-specific API terms/call limits and analyst review of sample records remain open before any recurring or production use. Registry status remains VERIFY.
