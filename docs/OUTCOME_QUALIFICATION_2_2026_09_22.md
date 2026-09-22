# Documentary qualification tranche 2 — 22 September 2026

Baseline: `686d8b9fe11cb026edc9d0348a8adeb4aff627b9`, the accepted reviewed-dossier and persistent-monitor release. This tranche does not modify the UI, monitoring-state branch, current procurement feed, historical denominators, or scoring gates. The shared capture change is limited to requesting the correct MIME type for robots.txt; all access and robots checks remain enforced.

Nine additional EU-labelled Invest in Canada discoveries are reviewed against ten dated primary issuer/government pages: cellcentric Burnaby, Stellantis Brampton, Nature Energy Farnham, Ubisoft Sherbrooke, Roquette Manitoba R&D, Siemens Energy Greenview, Nova Bus Saint-François-du-Lac, Enel Green Power Pincher Creek, and Accenture St. Catharines.

Key boundaries:
- cellcentric, Stellantis, Ubisoft, Nova Bus and Accenture sources explicitly describe existing Canadian operations; their projects are expansion/relocation/modernization, not first Canadian entry.
- Nature Energy's March 2022 Farnham announcement is preserved separately from the March 2023 Investment Canada acquisition record naming Nature Energy Farnham Inc. and reporting United Kingdom ultimate control after Shell's acquisition. The original Denmark card label remains a source label, not current control.
- Roquette's primary partner source supports a Winnipeg-datelined collaborative R&D project, not independently a distinct Winnipeg R&D-centre facility. The agency card characterization remains qualified.
- Alberta's January 1, 2023 monthly update establishes only that the Siemens pilot was listed as completed for December 2022. It is a completed-by bound, not an exact commissioning/first-operation date.
- Enel's May 2020 release says the two Alberta projects were connected and delivering energy. Its three-wind-farm North America headline also includes a Texas expansion; it is not three Canadian wind farms. The same document identifies an existing Canadian wind farm operating since 2012, so the additional capacity is not first Canadian entry.

No case becomes a verified legal identity, first-entry label, independent holdout, public alert, or score input. Historical documents do not establish 2026 project status. The Nature Energy 2025 withdrawal noted in earlier research remains unverified in this release: its reported Énergir PDF has not passed the retained evidence pipeline. No PDF-derived current-status claim is inserted.

## Captured failures and bounded repairs

Initial exact-head run `35794133308` failed on five paths. Diagnostic artifact `10723391513` has independently verified ZIP SHA-256 `3edea9f5529aefa4c8628307efa79950c7904b19104ca430e11ed49e069826f4`; its raw bodies establish the failures rather than inferred source absence.

1. The Ontario Newsroom page is a JavaScript shell; the separately named Invest Ontario primary-publisher article has its own source ID. The original failed URL remains in `known_unavailable_paths`.
2. The original Enel landing page supplies a PDF rather than the asserted HTML body. Enel's separately published corporate HTML release is a distinct source; the original failed URL is retained.
3. Nature Energy and Roquette dates occur in the article's own header. Two explicitly reviewed layouts preserve those headers without including site navigation or fabricating a date. Missing dates, missing anchors and ambiguous article regions still fail.
4. Alberta's retained HTTP 406 body reports unacceptable MIME negotiation. Only robots.txt requests now accept text/plain. Authentication failures, disallows, 406, throttling and server errors remain blocking; no user-agent change or access bypass was added. A fresh live proof is required to establish whether negotiation resolves this path.

Six added regressions and all existing tests passed locally (379 Python tests); remote exact-head source acceptance is still required. The temporary branch-only preparation workflow removes itself and is not part of the delivered tree.

Acceptance requires every selected source path to pass the existing robots/network checks, exact date and literal-anchor verification, two live captures on one ledger, raw-response hash retention, replay idempotence, preserved first observation clocks, full tests, and exact-head artifact inspection. A failing source remains unverified; it must not be converted to absence or silently replaced.
