# CORDIS research co-participation preview

This is a separate, unqualified research discovery lane. It does not add CanadaBuys awards, verified corporate groups, expansion claims, predictive evidence, monitor events, alerts or database rows. There is no network collection, schedule, deployment or source promotion in this patch.

## What it provides

`python -m atlanticbridge.cordis_research` consumes a previously acquired official Horizon Europe JSON ZIP and its acquisition receipt, then writes an allowlisted JSON derivative. `ui/cordis-research.html` is a standalone local file-picker review page; it does not fetch the source or mutate the app. Load the derivative with its file picker. The existing live console and its counts are unchanged.

A record requires an organisation located in Canada and at least one EU-27 organisation classified PRC on the same project. CORDIS uses EL for Greece; the derivative normalizes exactly EL to ISO GR and preserves country_raw. No other country alias is inferred. PRC means private for-profit entities excluding Higher or Secondary Education Establishments. PICs are Commission participant identifiers, not verified legal entities or ultimate parent groups. A shared consortium does not establish a direct bilateral relationship. Participant roles are preserved. Some participants do not receive funding or sign the grant.

All records explicitly have `qualification_status=RESEARCH_ONLY_NOT_QUALIFIED`, `model_eligible=false`, and `expansion_inferred=false`. Conservative military/dual-use text markers hold projects out of the preview; passing that screen is not authoritative civilian-use clearance. None is promoted to a qualified commercial lead.

## Verified snapshot, not new activity

The JSON ZIP was acquired on 9 November 2026 at 18:36:59.372836 UTC:

- Official source: https://cordis.europa.eu/data/cordis-HORIZONprojects-json.zip
- SHA-256: `5f791fb527da6880322496278099d11661894a9e66d305431788e6ed88349533`
- 143,482,269 bytes; HTTP 200; Last-Modified 8 October 2026 at 15:52:57 GMT.
- Catalogue modified date: 15 October 2026. The catalogue's advertised file size is stale relative to the actual download. Preserve the clocks separately.
- 23,954 project JSON objects and 148,155 organisation participation rows.
- 431 projects with a Canadian participant; 250 also have an EU-27 PRC participant.
- Six candidates held by conservative scope wording; preview contains 244 projects, 1,273 EU PRC participation rows and 294 Canadian participation rows.
- 1,094 distinct EU PRC PICs and 128 Canadian PICs. These are not verified corporate groups or incremental market leads. No cross-source entity deduplication is claimed.
- Source project status: 242 SIGNED, one CLOSED, one TERMINATED. These source labels are not a current activity assessment.

Project start/end, content update, file modification, catalogue modification and acquisition are different clocks. The JSON also contains content creation/source update/last update dates; this integration does not treat those as proven original publication. Historical model use remains blocked.

`attributes.terminated` is mapped to the source's end-of-participation flag. It is a boolean string, not a date. `active` relates to Framework Partnership Agreements; missing values stay empty and it is never used as a universal current-participant flag. The derived unended-participant indicator means only that a non-terminated Canadian and EU PRC participant are both listed in this snapshot.

## Rights and privacy

The authoritative distribution metadata explicitly identifies Commission Decision 2011/833/EU. It permits reuse subject to attribution, non-distortion, privacy and third-party-rights limits:

- Metadata: https://data.europa.eu/api/hub/repo/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027.ttl
- Catalogue: https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027
- Licence: https://eur-lex.europa.eu/eli/dec/2011/833/oj
- Legal notice: https://cordis.europa.eu/about/legal/en

Attribution: Source: CORDIS, Publications Office of the European Union, “CORDIS – EU research projects under Horizon Europe (2021–2027)”, reused under Commission Decision 2011/833/EU. Selected, filtered and reformatted by Atlantic Signal. Retrieved 9 November 2026. No EU endorsement implied.

This dataset is not labelled CC0: CC0 applies to catalogue metadata. The editorial-content CC BY statement is not substituted for the distribution's licence. No beneficiary documents are reused.

The output allowlist excludes VAT, addresses, geolocation, contact mechanisms, arbitrary source fields and full objectives. Public organisation names and project titles remain. Their mere publication is not permission for unrelated profiling or outreach. Raw ZIPs stay outside the deliverable. Source-record hashes identify the locally parsed evidence without exporting excluded fields.

## Source integrity

The current official CSV has 198 malformed-width project rows (23,756 normal-width rows out of 23,954). Three affect Canada-linked projects, and one affects the Canada/EU PRC candidate scope. CSV strict mode also catches malformed quotation boundaries. The old collector silently accepted replacement decoding and shifted columns. It now fails closed on invalid UTF-8, quotation boundaries and row widths. A failed transactional replacement retains the prior database snapshot.

The new derivative uses the separately licensed official hierarchical JSON, not a reconstruction or permissive reinterpretation of damaged CSV. Project 101182948, affected in CSV, is parsed directly from valid JSON. Separately, the source uses EL rather than GR on all 6,341 Greek participation rows. Thirty-six Canada/Greek-PRC projects contain 54 Greek PRC rows; one project was otherwise absent from the inherited GR-only scope. No CSV fields are heuristically joined.

The new reader checks the exact source/final URL, receipt status, actual byte size and SHA-256. The receipt records acquisition; it is not a cryptographic publisher attestation. ZIP size, expanded size, member size, member identities, duplicate names, duplicate JSON keys, non-finite constants, duplicate project IDs, duplicate participant rows and schema mismatches are checked. Unknown association types, missing or conflicting activity classifications, unknown roles and missing/invalid termination flags fail closed instead of silently narrowing coverage. Repeated PICs across distinct source participation rows are preserved; they can legitimately have different roles or termination flags. Input parsing failure does not replace the output. The reader never extracts ZIP members to paths.

## Reproduce offline

From the repository root, with the package available:

    PYTHONPATH=src python -m atlanticbridge.cordis_research \
      --archive /path/to/cordis-HORIZONprojects-json.zip \
      --receipt /path/to/build-json-receipt.json \
      --output /path/to/cordis-research.json \
      --as-of-date 2026-11-09

The receipt requires `source_url`, `final_url`, `http_status`, `sha256`, `bytes`, and timezone-aware `retrieved_at`; optional file/catalogue modification clocks are carried separately. An as-of date before acquisition is rejected. No new download is performed by this command.

## Release boundary

Prepared against main `1408cb351872c19db6ed5b8febe58fa039e0b4d0`, verified unchanged on 9 November. No workflow or schedule is changed. This preview has not been pushed, deployed, merged, added to the live app or activated as a monitor. Any future publication requires a fresh exact-path trigger review and the existing operational release gates. A main push invokes Pages and may invoke downstream monitoring/retention; this patch is not permission to execute that chain.
