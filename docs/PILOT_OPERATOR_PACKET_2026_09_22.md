# AtlanticBridge operator packet — workflow pilot

This extends `ANALYST_PILOT_2026_09_22.md`; it does not replace its evidence, identity or score gates. No participant is enrolled by this file. The supplied records template is intentionally empty. Keep participant identities, consent, client information and payment records outside this public repository.

## Recruitment and enrollment

Recruit 3–5 independent economic-development, investment-attraction or commercial-development users. Record their role, explicit consent, date and an operator-held consent reference using a pseudonymous reviewer ID. A developer test, elapsed browser session or downloaded feedback file is not proof of independent enrollment. Do not claim invitations were sent or users agreed until those actions actually occurred.

Invitation draft: “We are testing AtlanticBridge Signals, a source-backed research workflow for European companies' Canadian activity. The pilot distinguishes procurement evidence, project histories and items that still need qualification; it does not provide validated expansion probabilities. We would like you to compare a few relevant cases with your normal research process, record what was new or useful, and identify anything misleading. Participation and feedback are voluntary. We will agree what data to retain before you begin.”

## Session protocol

Use a recorded set of source-backed cases appropriate to the participant's sector and Canadian market. Freeze the case IDs and source snapshots before the comparison. Include irrelevant or already-known cases so positive-only selection does not inflate usefulness. The 50-target roster is an operational review selection containing known outcomes, not fifty qualified companies or an independent predictive holdout.

Have each participant perform the same defined research task using their usual method and the app. Record task order and counterbalance baseline-first versus tool-first across sessions to expose learning effects. Record active research time manually, with the original timing record; the existing page-view timer includes idle time and must not be used as time saved. Compare against manual research, announcements-only and CIPO-only where the case has suitable coverage. Missing coverage is not a zero-signal baseline.

In the app, open Review queue, inspect a dossier and original sources, save a next action, and export the worklist and review feedback. Record identity correctness separately from source support, usefulness and whether the information was already known. Leave unassessed answers null. Record false identity joins, duplicate leads, stale or cancelled projects, misleading location claims and unsupported first-entry wording.

Ask willingness to pay only after the task. Keep a stated willingness distinct from a verified payment and retain any payment evidence privately. A small favorable pilot cannot establish a validated twelve-month forecast.

## Brief status model and evidence contract

Every reviewed company brief is a research record, not a qualified site-selection lead. Keep these stages distinct and preserve the source date and analyst decision behind every transition:

1. **Observed:** record the dated source fact, the source publication date when known, the retrieval/check date, the exact source URL, and what the source actually says.
2. **Canadian presence and identity:** verify the operating entity and ultimate ownership separately. State whether evidence indicates existing Canadian operations, a new operation, a partnership, procurement, or only general interest. Unknown identity stays unresolved.
3. **Mandate status:** default to **unconfirmed**. Call a site-selection mandate confirmed only when a primary source or the responsible organization directly supports that statement. An announced investment with no site, a hiring page, or a supplier opportunity is not an uncommitted mandate.
4. **Regional fit hypothesis:** show candidate regions and the reasons for each as hypotheses, with the relevant labor, infrastructure, supplier, logistics, market, and incentive sources. Keep missing information explicitly unknown.
5. **Disposition and next action:** the analyst records a status, a concrete next action, an owner role or private pseudonymous operator ID, and a follow-up date. Include reasons to disqualify, defer, or revisit; a positive-only lead list is not a pilot result.

For every candidate, capture counter-evidence and stale-data warnings beside supporting evidence. A source check is not the source's publication date, and an older announcement must be rechecked before being described as current. Ownership labels must distinguish headquarters, operating subsidiary, and ultimate parent. Never infer first Canadian entry from a new filing, hiring page, procurement relationship, or announcement without resolving earlier activity.

A pilot set should deliberately include already-present firms, ambiguous identities, non-mandate activity, and cases that should be ruled out or deferred, alongside promising observations. Report usefulness, factual support, identity correctness, novelty, and manually timed active research separately. Missing source coverage is unknown, not a zero or a negative finding. This workflow supports an analyst-reviewed brief; it does not validate the Expansion Score or create a predictive lead product.

## Source expansion gates

The source candidates below are leads for review, not approval to ingest. Confirm current endpoint behavior, licence terms, reuse rights, update cadence, suppression/coverage rules, and provenance before adding a collector or showing derived facts in a paid workflow.

| Candidate | Useful context | Gate before integration |
| --- | --- | --- |
| [Canada Business Registries FAQ](https://ised-isde.canada.ca/cbr-rec/faq) | Provincial and federal registry discovery | Its FAQ prohibits automated copying, searching, or scraping. Do not automate this federation or infer bulk provincial-registry rights. |
| [Federal Grants and Contributions dataset](https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013) | Public program awards and recipient context | Verify the bulk endpoint, applicable reuse terms, update frequency, recipient identity, and what award amounts mean before use. Awards are not evidence of a new expansion mandate. |
| [Impact Assessment Agency inventory](https://iaac-aeic.gc.ca/050/evaluations) | Major project and assessment context | Verify accessible fields, source dates, geographic coverage, reuse terms, and whether project proponent identities can be resolved. An assessment is not proof of a site-selection mandate. |
| [EU Funding & Tenders APIs](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) | Published EU projects, organizations, and partner-search context | Confirm endpoint terms, fields and refresh behavior. Treat projects and partnerships as context, not company expansion intent. |
| [Québec enterprise registry open data](https://www.donneesquebec.ca/recherche/dataset/registre-des-entreprises) | Québec entity and ownership research | Bulk data is described as CC BY-NC-SA. Do not assume compatibility with a commercial product; exclude it until rights are reviewed for the intended use. |
| [BC Registries API](https://developer.api.bcregistry.gov.bc.ca/en-CA/products/get-started/apis-summary/) | British Columbia entity research | Access requires an account, a scoped API key, and account context; some requests incur fees. It is not a plug-and-play public feed; do not access or budget for it without explicit authorization. |
| [Canadian Importers Database, 2024](https://ised-isde.canada.ca/site/ised/en/research-and-business-intelligence/canadian-importers-database) | HS6/product, city, and country-of-origin trade-footprint context | Based on 2024 CBSA data; the major-importer lists cover up to 80% of imports for a product or city and can include customs brokers, clients, and non-resident importers. Verify suppression rules, reuse terms, and publication vintage before integration. Trade footprint is not evidence of expansion intent or a current operating site. |

### Second-priority source leads (4 November 2026)

These are preliminary catalogue entries for due diligence, not integrated feeds. Live schema, current licence/terms, endpoint stability, coverage and change semantics still need to be checked.

| Candidate | Useful context | Interpretation and integration gate |
| --- | --- | --- |
| [EU Funding & Tenders Portal APIs](https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/support/apis) | Published calls, projects, organizations, results and partner-search context | Verify live endpoints, fields, identifiers, terms and update cadence. Projects and consortium links are research context, not a Canadian expansion mandate. |
| [DG Competition case open data](https://competition-policy.ec.europa.eu/about/news/dg-competitions-case-data-available-open-data-2025-03-18_en) | EU competition-policy case records; the Commission describes machine-readable JSON, daily updates and commercial reuse with source acknowledgement | Preserve case status and dates. A merger notification or open case is not a completed transaction or proof of Canadian operations. Verify dataset identifiers and schema before linking entities. |
| [France BODACC commercial notices](https://www.bodacc.fr/explore/dataset/annonces-commerciales/api/) | Official French commercial notices; the dataset page identifies Etalab Open Licence 2.0 | API access and a reuse licence are documented. Verify the live schema, auth/rate limits, notice types and publication clocks before a parser is accepted. A notice is an event to review, not a confirmed operating change or cross-border expansion. |
| [IAAC assessment inventory](https://open.canada.ca/data/en/dataset/f4c51eaa-a6ca-48b9-a1fc-b0651da20509) | Projects subject to federal impact assessment | Verify current schema, terms, status vocabulary, project identifiers and coverage. An assessment record does not establish site selection, construction, or completed operations. |
| [Nova Scotia awarded public tenders](https://data.novascotia.ca/Procurement-and-Contracts/Awarded-Public-Tenders/m6ps-8j6u) | Supplier and procurement-award context in one Canadian region | Verify schema, licence, publication cadence, buyer/supplier identifiers and contract status. A procurement award is not evidence of physical expansion or an investment mandate. |

### Verified registry and company-event candidates

Official pages reviewed on 4 November 2026 show a few comparatively practical sources for **origin-company identity and event context**. These do not themselves establish Canadian expansion. Integration is deferred until the current monitor and archive path are healthy and each source contract is tested.

| Candidate | Verified access and coverage | Product use and limit |
| --- | --- | --- |
| [Finnish PRH Open Data](https://avoindata.prh.fi/en) | Free APIs and daily data; basic company details, register notices from 7 November 2014, and digital financial statements. PRH says the digital statements cover about 5% of all filed statements. | Strong candidate for source-linked Finnish entity and register-event context. Keep unavailable fields and the financial-statement coverage limit explicit; validate API schema and reuse terms. |
| [France BODACC commercial notices](https://www.bodacc.fr/explore/dataset/annonces-commerciales/) | Official API-backed dataset, under Etalab 2.0 per the dataset page. | Strong candidate for French entity event context. Store notice type, publication date and company identifier; do not interpret one notice as verified current operations or a Canadian project. |
| [Brønnøysund Register Centre open data](https://www.brreg.no/en/use-of-data-from-the-bronnoysund-register-centre/open-data/) | Official API and datasets are free and under NLOD, according to the Register Centre. | Technically promising, but Norway is not an EU member. Keep it in a separately labelled EEA/other-Europe coverage cohort, not EU-origin totals. |
| [Belgian Crossroads Bank for Enterprises reuse options](https://economie.fgov.be/en/themes/enterprises/crossroads-bank-enterprises/services-everyone/public-data-available-reuse) | Public-search services are free for public CBE data; a limited active-entity file and updates are also free. The extensive complete file requires an agreement and commercial reuse costs €30,000 annually. | Do not assume bulk commercial reuse. The free limited/search options need separate scope and terms review before an integration decision. |
| Estonia e-Business Register | The official register exposes public and historical entity information, but the bulk/service access and terms need verification for the intended use. | Keep out of automated ingestion until the exact service-specific contract and permission are reviewed. |
| [Investment Canada Act decisions](https://ised-isde.canada.ca/site/investment-canada-act/en/investment-canada-act/decisions) | ISED says it publishes completed decisions and certified notifications filed under the Act. | High-value Canadian investment-event context, but publication cadence, available bulk records, lag, licence and entity fields need confirming. A filing is not proof of completion or a greenfield Canadian operation. |

Belgium's paid complete file, Québec's non-commercial licence, BC's account/API process, and restrictions on automated Canada Business Registries access remain separate access gates. A restricted source is not promoted into the pilot simply because it could improve identity matching.

### Expansion decision order

1. Restore reliable operation and durable archival for the accepted 13-source monitor before widening scheduled collection.
2. Validate BODACC and PRH as source-local identity/event enrichments in a bounded, non-production fixture, with source dates and stable identifiers. Keep their evidence separate from Canadian opportunity status.
3. Review Investment Canada notification records for terms, cadence, lag and usable company fields. Treat them as observed filing/completion events, not forward-looking leads.
4. Add project/award/permit sources only when they add a dated, company-resolved fact to a case. Keep grants, IAAC/provincial assessment stages, public tenders and Halifax permits labelled by their own status.
5. Keep EU funding portfolios, EIB/EIC/Kohesio and EU Financial Transparency records as funding/project context. Keep UKRI separate from EU-origin coverage; its Gateway to Research has a new API and existing users need to migrate and recheck its schema.

No source should be added to the production collector or the expansion score from this catalogue alone. Validate rights, endpoint schemas, update schedules, identifiers, failure behavior, and commercial-use terms first.

For every accepted source, record the official endpoint and licence/terms URL, retrieval and publication clocks, update cadence, geography and population coverage, stable identifiers, suppressed/missing-value rules, retained evidence/hash, and failure/staleness behavior. Keep company-specific evidence separate from regional context. A candidate that cannot be accessed or reused under the intended terms remains out of the product, regardless of relevance.

## Private record contract

Copy `reviews/pilot/participant-records-template.json` to private storage. A participant needs `reviewer`, `role`, `recorded_date` (YYYY-MM-DD), `consented`, `independent_user`, and a private `consent_record` reference. Append the existing browser feedback exports to `reviews`; the reviewer label must match the consented ID. Unknown or unconsented submissions are excluded from independent-user metrics, not silently enrolled.

For a paired task, supply `reviewer`, `task_id`, `timing_basis: MANUALLY_TIMED_ACTIVE_RESEARCH`, `order: BASELINE_FIRST` or `TOOL_FIRST`, `baseline_method: MANUAL_RESEARCH`, `ANNOUNCEMENTS_ONLY` or `CIPO_ONLY`, `timing_record`, `baseline_seconds` and `tool_seconds`. Negative time savings remain negative.

Purchase feedback uses `reviewer`, `willing_to_pay` (boolean or null), `payment_verified` (boolean), and an `operator_payment_record` reference only when an actual payment has been verified.

Run locally: `PYTHONPATH=src python scripts/analyse_pilot.py /private/pilot-records.json --output /private/pilot-results-01.json`.

The command refuses to overwrite inputs or existing results, sends nothing externally, and reports separate reviewer denominators, unique alerts, unverified reviewer submissions, paired active-time results and paying participants. Empty records yield zero recorded participants and unknown time savings—not invented accuracy or commercial validation.

## Acceptance and decisions

Before the first external session: require exact hosted release acceptance; verify the original worklist survives reload/export/restore; verify source dates, identity bounds and failure states; qualify the companies appropriate to that session. After sessions, retain actual exports and timing records and report both useful and unsuccessful cases. Expand the cohort only when new coverage generates useful or earlier evidence rather than more unreviewed records. No Expansion Score weights are enabled by pilot feedback.
