# CORDIS static research lane

This release exposes an already reviewed, sanitized research snapshot as a separate page, reached from **EU–Canada research** in the main navigation. It does not activate a collector, refresh source evidence, or add research participants to CanadaBuys notices, company totals, qualified leads, the analyst queue, or prediction models.

## Fixed provenance

- Calculation as of: **2026-11-09**.
- Source acquired: **2026-11-09T18:36:59.372836+00:00**.
- Official source file Last-Modified: **Thu, 08 Oct 2026 15:52:57 GMT**.
- Catalogue modified: **2026-10-15**.
- Original hierarchical JSON ZIP: 143,482,269 bytes; SHA-256 `5f791fb527da6880322496278099d11661894a9e66d305431788e6ed88349533`.
- Published sanitized derivative: `ui/data/cordis-research-2026-11-09.json`, 977,669 bytes; SHA-256 `df7d55e6e3e2603e1b1bd38fc0068752388885357deb8442e95b498385b84825`.

The derivative bytes are unchanged from the reviewed 9 November research artifact. No original source archive was downloaded for this release. Deployment time is not source freshness, first discovery, first publication or an expansion date.

## What the snapshot contains

The complete source parse covered 23,954 projects and 148,155 organisation participation rows. There were 431 Canada-linked projects, 421 with an EU participant of any activity type, and 250 with an EU-27 PRC participant. Six conservative wording holds leave **244 displayed projects**. These contain **1,273 EU PRC participation rows / 1,094 distinct EU PICs** and **294 Canadian participation rows / 128 Canadian PICs**. PICs are source-local Commission identifiers, not verified companies or corporate groups. All records remain `RESEARCH_ONLY_NOT_QUALIFIED`, `model_eligible=false`, `expansion_inferred=false`.

Co-participation in a consortium is not proof of a direct partnership, Canadian expansion, current hiring, an open commercial requirement or present-day activity. Project status and period are retained as source claims, not reverified current status. PRC means private for-profit except Higher or Secondary Education Establishments. EU location does not establish European parent ownership. Contacts, detailed addresses, VAT, geolocation and objectives are absent. Civilian scope remains unverified even after screening.

## Sources and reuse

- [Official CORDIS Horizon Europe dataset](https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027)
- [Official hierarchical JSON distribution](https://cordis.europa.eu/data/cordis-HORIZONprojects-json.zip)
- [Commission Decision 2011/833/EU](https://eur-lex.europa.eu/eli/dec/2011/833/oj)
- [CORDIS legal notice](https://cordis.europa.eu/about/legal/en)

Source: CORDIS, Publications Office of the European Union. Selected, filtered and reformatted by Atlantic Signal under Commission Decision 2011/833/EU. No EU endorsement implied. This is not a claim that the dataset is CC0.

## Loading and failure behavior

The page loads only the dated same-origin JSON path, with credentials omitted, no referrer and redirects rejected. It enforces the exact size and reviewed derivative SHA-256 before validating schema, provenance, count consistency and research boundaries. Its CSP permits same-origin scripts/styles/data only and no remote images, objects, forms or base URL. An inert data favicon avoids a default favicon request. No original source is requested. The digest proves agreement with the reviewed derivative, not independent authenticity of the original source archive.

If fetch, type, size, checksum or schema validation fails, counts remain **unavailable**, not zero; old results are cleared. There is no automatic retry. Clear, local selection and repeated reloads use a generation guard so an older result cannot replace the latest user choice. Optional local files are never uploaded and are visibly labelled distinct from the published snapshot; they receive structural validation, not the published checksum assurance.

## Offline acceptance

Run `node --test tests/test_cordis_research.cjs tests/test_cordis_published.cjs` for 35 focused checks including the actual snapshot and inert DOM rendering. The new suites must be invoked explicitly or by `node --test tests/*.cjs`; existing workflow explicit Node lists do not automatically include them.

This patch changes only ten static/data/documentation/test paths. No workflows, collectors, schedules, source modules, retention code, prediction or main app data code change. The existing public UI acceptance entrypoint now calls dedicated CORDIS acceptance at its existing desktop, tablet, iPhone and narrow-phone sizes. It checks exact deployed assets, loaded counts and clocks, navigation, filters, pagination, clear/reload, source-link safety, request boundaries, overflow and intercepted unavailable/checksum failure responses. Browser appearance and deployed acceptance remain separate release checks; they were not performed by this offline implementation. No source was recollected.
