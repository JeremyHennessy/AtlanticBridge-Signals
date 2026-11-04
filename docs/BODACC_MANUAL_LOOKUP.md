# BODACC manual lookup

Status: the official-site manual lookup is separate from a bounded CLI collector candidate, which passed one live API smoke query. Browser acceptance and production suitability are not verified. Reviewed 4 November 2026.

## User flow and provenance

An analyst verifies the French legal entity and its nine-digit SIREN in independently reviewed evidence. The opportunity review panel constructs a fixed BODACC search URL. The analyst opens it deliberately, checks the returned legal entity, captures the notice URL and publication/event dates, and records relevant facts and counter-evidence in case notes. The browser opens the official search in a separate tab without a referrer.

The browser lookup does not send the SIREN to an AtlanticBridge server, make API requests, persist the identifier, copy notice text, or treat a result as a signal. A no-result search is not evidence of absence. The CLI collector candidate is separate, manual-only, and not scheduled or connected to the UI or production database.

## Source and interpretation

- Official BODACC commercial notices: https://www.bodacc.fr/pages/annonces-commerciales-recherche/
- Official open-data/API overview: https://www.bodacc.fr/pages/donnees-ouvertes-et-api/
- Dataset page: https://www.bodacc.fr/explore/dataset/annonces-commerciales/
- The official data-service listing describes Etalab Open Licence 2.0 and separate API terms. Recheck terms before automated or retained use.
- Public Huwise API documentation describes querying public datasets without an API key; availability does not establish source-specific quotas or suitability for recurring ingestion.

French legal notices can establish dated French corporate events or legal facts within the notice's scope. They do not establish Canadian operations, a Canada-directed expansion, an uncommitted site-selection mandate, investment intent or market fit. Check event and publication dates separately, verify entity identity and parent-control relationships, and record contradictory or later evidence. Keep French corporate context separate from Canadian-specific evidence and analyst assessments.

## Validation and next step

Run `node --test tests/test_bodacc_search.cjs` for the lookup URL behavior. Browser acceptance remains to be run in the full project environment.

The bounded CLI collector accepts one verified SIREN and required publication-date lower bound, requests a single page capped at 100 notices, blocks redirects and retains only allowlisted metadata and provenance. It does not retain notice text, person fields or raw response bodies. The output identifies more API pages where applicable and treats zero results as inconclusive.

One branch-only live smoke query passed on 4 November 2026 for a verified SIREN, since `2020-01-01`, limit 1. One record returned and passed exact-SIREN validation; live `registre` was a JSON list. This validates one request path only. Source completeness, API-specific terms/rate limits and production suitability remain unverified. The command is not scheduled, wired into production monitoring or used by the UI.

Focused collector tests and the one live smoke query are documented in [BODACC_COLLECTOR_REVIEW.md](BODACC_COLLECTOR_REVIEW.md). The full project suite and hosted browser acceptance were not run on the latest collector head.
