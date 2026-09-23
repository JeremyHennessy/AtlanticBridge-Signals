# Current qualification tranche 2 — 23 September 2026

Baseline: `11bfc986463ba714cd9a338fafa8a7aaf3c65491`, the accepted production release after qualification tranche 1.

This source-only tranche tests two existing HOLD decisions, Cellcentric and Roquette, against current operating, identity, supplier-path and rights-boundary evidence. It does not modify the live review register.

## Cellcentric
- The current contact page names **cellcentric Fuel Cell Canada Inc** at the Burnaby Riverbend address.
- The current corporate page describes cellcentric as the 50:50 Daimler Truck / Volvo Group joint venture and lists its Burnaby advanced-engineering site; its August 2026 intellectual-property count is context, not a page-publication date.
- The current supplier page explicitly solicits supplier inquiries and contains 2026/2027 goods-receipt dates. Those dates do not become a page publication date.
- ISED's Canadian Importers Database separately lists CELLCENTRIC FUEL CELL CANADA INC. in Burnaby. The Open Government Portal metadata for the reviewed CID dataset states Open Government Licence - Canada. Dataset/version scope must remain explicit.
- cellcentric's legal notice says the web pages themselves do not grant licence rights to cellcentric intellectual property. That is a rights boundary, not permission to republish corporate page content.

## Roquette
- The current locations page names Roquette Canada Ltd. and its Portage la Prairie office/production site.
- A September 4, 2026 official job posting describes an on-site Portage role operating the plant's utility systems. This is dated current plant evidence.
- Roquette's legal notice states that website information may not be republished without prior written consent and separately restricts third-party hyperlinks absent approval. This means commercial/public source reuse must remain unresolved/restricted unless a permitted source or written approval is established.

No company is automatically promoted. In particular, an open-government licence for a government dataset does not transfer rights to separate corporate webpages. Acceptance requires both captures, raw hashes, replay idempotence and full regressions.


## Initial live-proof failure and bounded repair

Initial exact-head run `35810395522` failed only `cellcentric-supplier-current`; the other eight reviewed paths were observed successfully and the existing company-source proof remained green. Diagnostic artifact `10729277461` has SHA-256 `fbbc5f99c21b6508d3677cda1d0314a96acd58c82866527be89597af4721070d`.

The retained Cellcentric supplier HTML contains the required supplier-inquiry text in its single page `<main>`, but also contains multiple earlier `<article>` elements used as PDF/document cards. The generic article parser therefore selected an unrelated PDF card and correctly failed its required anchor instead of treating the source as absent.

The repair is source-contract scoped: `cellcentric-supplier-current` explicitly requests the single reviewed `main` region. The parser accepts only that reviewed selector, requires exactly one match, and otherwise fails closed. Default parsing for every existing source is unchanged. Regression coverage requires the unscoped decorative-card fixture to fail, rejects unreviewed selectors, and rejects ambiguous duplicate `main` regions. No source anchor, robots/TLS rule or access control is weakened.
