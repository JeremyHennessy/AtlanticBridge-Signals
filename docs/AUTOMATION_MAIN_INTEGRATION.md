# Local foundation integration on main

## Exact baseline and scope

This change is prepared against `1408cb351872c19db6ed5b8febe58fa039e0b4d0` in `JeremyHennessy/AtlanticBridge-Signals`. Every baseline file was verified against that commit's Git blob identity before preparing the candidate. Recheck the main head before applying it.

The independently reviewed r2 foundation is included unchanged, with its schema 2, conservative evidence model, private durable storage, source isolation and protected-source checks. The public UI, checked-in public data, existing collectors, archive scripts and workflows are unchanged. No source is enrolled, live collection scheduled, notification sent, credential configured or new service purchased.

## Offline dependency reconciliation

Main did not contain the local packet builder or bundled Halifax/NL pilots required by the foundation. This change adds only the necessary offline support:

- The existing analyst packet normalizer, with its four licence/attribution constants moved to a static `source_metadata.py` module. The literals are identical to the reviewed values.
- The hash-pinned Halifax parser/sample and NL invented-fixture parser, their packaged JSON pins and offline fixture builders/tests.
- Package-data declarations for the two existing pinned JSON resources.

The BODACC and federal-grants HTTP collector modules are **not** introduced. Normalizing a user-supplied local packet is not authority to fetch a source or a claim that its contents are independently verified. Known Halifax/NL provenance remains bound to the bundled content and rights limits at durable ingestion boundaries.

All original packet-builder tests are included except the standalone analyst UI's asset-specific test, because that separate UI is not shipped in this change. No existing main test is removed or relaxed. New tests verify the metadata-only import boundary and exact r2 protected contract/normalized-byte hashes.

## CI and publication effects

No workflow file changes are included. Under the exact baseline's existing rules:

- A branch named outside `feature/**` and the specialized `research/*` patterns has no matching ordinary push workflow for this change.
- Opening a PR to main triggers the existing general CI. In addition to unit tests and the publication gate, CI performs its existing live Investment Canada smoke. This is not an offline-only hosted check.
- Merging to main triggers CI and the Pages publisher. Pages refreshes CanadaBuys and deploys the public console.
- Completion of Pages triggers the existing delivery guard. If its current-state rules dispatch company monitoring, monitoring completion can trigger evidence retention.
- The added/modified paths do not directly match the company-monitor, evidence-retention, pilot-release, source-proof or browser/UI PR path filters.

A merge is therefore not merely a code save. Do not use it to retry a denied archive request indirectly. No workflow has been dispatched and no branch/PR/merge action was performed as part of this local preparation. Any external action must respect the latest authorization and unresolved access denial, with the exact current trigger chain reviewed first.

## Readiness limits

This is an application foundation, not a deployed automatic evidence service. There is still no authenticated write API, shared workspace integration, live-source scheduler transport or notification delivery. The public prediction gate remains closed. Schema 1 local databases are not silently migrated; preserve and reconcile any genuine operator data explicitly.
