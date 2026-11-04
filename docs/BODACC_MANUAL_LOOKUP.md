# BODACC manual lookup

Status: manual official-site link only; no automated data ingestion. Reviewed 4 November 2026.

## User flow and provenance

An analyst first verifies the French legal entity and its nine-digit SIREN in independently reviewed evidence. The opportunity review panel then constructs a fixed BODACC search URL. The analyst opens it deliberately, checks the returned legal entity, captures the notice URL and publication/event dates, and records relevant facts and counter-evidence in the case notes. The browser opens the official search in a separate tab without a referrer.

The app does not send the SIREN to an AtlanticBridge server, make API requests, persist the identifier, copy notice text, or treat a result as a signal. A no-result search is not evidence of absence.

## Source and interpretation

- Official BODACC commercial notices: https://www.bodacc.fr/pages/annonces-commerciales-recherche/
- Official open-data/API overview: https://www.bodacc.fr/pages/donnees-ouvertes-et-api/
- Dataset page: https://www.bodacc.fr/explore/dataset/annonces-commerciales/
- The official page describes the commercial-notice data under Etalab Open Licence 2.0. Recheck the current source terms before adding any automated or retained use.
- The public Huwise Explore API documentation says public datasets can be queried without an API key, but endpoint schema, query semantics, quotas and operational behavior have not been validated here. Do not infer permission or suitability for automated ingestion from API availability alone.

French legal notices can establish dated French corporate events or legal facts within the notice's scope. They do not establish Canadian operations, a Canada-directed expansion, an uncommitted site-selection mandate, investment intent, or market fit. Check event and publication dates separately, verify entity identity and parent-control relationships, and record contradictory or later evidence. Keep French corporate context separate from Canadian-specific evidence and analyst assessments.

## Validation and next step

Run `node --test tests/test_bodacc_search.cjs`. Browser acceptance remains to be run in the full project environment. Before proposing API ingestion, verify the live schema and fields, source-specific terms, update cadence, rate limits, identity matching, and how source records will be retained with timestamps and lineage.
