# BODACC manual lookup

Status: manual official-site lookup plus a bounded CLI collector candidate that passed one live API smoke query. Browser acceptance and production suitability are not verified. Reviewed 4 November 2026.

## User flow and provenance

An analyst first verifies the French legal entity and its nine-digit SIREN in independently reviewed evidence. The opportunity review panel then constructs a fixed BODACC search URL. The analyst opens it deliberately, checks the returned legal entity, captures the notice URL and publication/event dates, and records relevant facts and counter-evidence in the case notes. The browser opens the official search in a separate tab without a referrer.

The browser lookup does not send the SIREN to an AtlanticBridge server, make API requests, persist the identifier, copy notice text, or treat a result as a signal. A no-result search is not evidence of absence. The separately invoked CLI collector candidate is not scheduled or deployed, and its live API behavior remains unverified.

## Source and interpretation

- Official BODACC commercial notices: https://www.bodacc.fr/pages/annonces-commerciales-recherche/
- Official open-data/API overview: https://www.bodacc.fr/pages/donnees-ouvertes-et-api/
- Dataset page: https://www.bodacc.fr/explore/dataset/annonces-commerciales/
- The official page describes the commercial-notice data under Etalab Open Licence 2.0. Recheck the current source terms before adding any automated or retained use.
- The public Huwise Explore API documentation says public datasets can be queried without an API key, but endpoint schema, query semantics, quotas and operational behavior have not been validated here. Do not infer permission or suitability for automated ingestion from API availability alone.

French legal notices can establish dated French corporate events or legal facts within the notice's scope. They do not establish Canadian operations, a Canada-directed expansion, an uncommitted site-selection mandate, investment intent, or market fit. Check event and publication dates separately, verify entity identity and parent-control relationships, and record contradictory or later evidence. Keep French corporate context separate from Canadian-specific evidence and analyst assessments.

## Validation and next step

Run `node --test tests/test_bodacc_search.cjs`. Browser acceptance remains to be run in the full project environment. Before proposing API ingestion, verify the live schema and fields, source-specific terms, update cadence, rate limits, identity matching, and how source records will be retained with timestamps and lineage.


## Bounded collector candidate

A CLI collector is available in this branch as a testable candidate. It accepts one verified SIREN, a required publication-date lower bound, and a single page limited to 100 notices. It returns only the record ID, SIREN, publication date/type, notice family, official notice URL, publication-age label, retrieval time, query URL, and response hash; it does not retain free-text notice bodies, person fields, or the raw response. A query with no returned matching notice is explicitly not evidence of absence.

The official API is documented as free and open under Etalab Open Licence 2.0, subject to the API's terms. The source catalogue warns that API availability and rate limits are not documented and that records can contain personal data. For this reason, the command is not scheduled, wired into production monitoring, or used by the UI. One branch-only live smoke query passed on 4 November 2026: one record returned for the verified SIREN, one exact match, and the live `registre` field was a JSON list. This validates one request path only; source completeness, API-specific terms/rate limits, and production suitability remain unverified.

Run the contract tests with `python -m unittest discover -s tests -p test_bodacc_collector.py -v` in a Python-enabled checkout. To attempt an on-demand smoke test after network access is restored: `python -m atlanticbridge collect-bodacc-context --siren <verified-nine-digit-SIREN> --since YYYY-MM-DD --limit 20 --output bodacc-context.json`. The collector writes a single JSON envelope and never updates production state.
