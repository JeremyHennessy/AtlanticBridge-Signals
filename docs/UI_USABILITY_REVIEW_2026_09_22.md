# Purpose-led UI review — 22 September 2026

## Baseline and purpose

Baseline: `96861bb5633671b553ebee313947c4abbc9c960e` (PR #87). Review covered the available project conversation history, README, data-proof principles, outcome/publication rules, Backtest 002 constraints, existing UI code, accepted case payload, and deployment/tests.

The product is commercial, non-military intelligence about European expansion toward Canada. Nova Scotia suitability is a separate question. Expansion likelihood, Nova Scotia fit and evidence confidence must never be collapsed into one unvalidated score.

The old landing screen centered audit terminology, model ineligibility and a six-column evidence queue. The task flow should instead answer: What is this for? Which company case am I looking at? What does its evidence support? What remains unknown? What should I investigate next?

## Changes

- Overview explains original purpose and today's historical-research limitation. It does not present audited outcomes as live prospects.
- Companies provides search, control-country/finding/evidence filters, explicit non-predictive sort choices, quick views, reset, shareable URL state, and local-only saved cases.
- Case details lead with a plain-language summary, unchanged audit note, unresolved boundaries and a rule-based research suggestion. Complete timelines, claims, source URLs and publication status remain accessible.
- Evidence coverage separates registry timing, publication timing, identity review, exact first-operation eligibility and the absence of validated prediction/NS-fit assessment.
- How to use explains common terms and a three-step research workflow.
- Mobile uses stacked company cards and collapsible advanced filters. Modal focus trapping, inert background, Escape close, visible focus, safe external links and explicit error/empty states are included.
- Root redirect preserves hash/query links for branch-based Pages hosting.

## Unchanged research boundaries

No source collector, review, identity, proof manifest, model, backtest, score, outcome classification or accepted payload value is changed. Source observation/audit date remains distinct from interface release date. Save state is browser-local and does not mutate research or imply team sync. Evidence count is not confidence. The next-research-step copy is UI guidance, not newly discovered company evidence.

## Acceptance

Local baseline and updated Python suites: 219 tests passed. Offline Chromium render/interaction checks passed at 1440, 393 and 320 pixel widths. These local checks are not claimed as hosted or WebKit verification.

`tests/ui_visual_acceptance.mjs` is the shared integration contract for PR preview and hosted release: four routes, all cases, all attached claims and source URLs, filters, URL reload, local-save reload, keyboard/dialog behavior, overflow, failed payload and browser errors. Engines are desktop Chromium, iPhone WebKit and 320-pixel Chromium. Reports and screenshots are retained by CI.

The existing payload generator reorders some JSON keys. Repeated generation must be byte-stable, and parsed data must equal the accepted payload. UI HTML/JS/CSS must match the checked-out release exactly; evidence data comparisons must preserve every audited value regardless of JSON key ordering.

Do not describe a branch, PR or passing local render as a production deployment. Publish merge/deployment/hosted-acceptance provenance separately once verified.
