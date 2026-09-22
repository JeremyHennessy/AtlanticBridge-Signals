# Tranche-two source repair evidence

Accepted production baseline: 686d8b9fe11cb026edc9d0348a8adeb4aff627b9. Repairs remain on PR #107 until exact-head acceptance.

Initial diagnostic: run 35794133308, artifact 10723391513, ZIP SHA-256 3edea9f5529aefa4c8628307efa79950c7904b19104ca430e11ed49e069826f4.

Second diagnostic: run 35794985899, artifact 10723187655, ZIP SHA-256 f0a73ae39bf772621b1c33a1bbc360027bc48cb808513eb40b4677524cce20f7. Nine of eleven requested paths pass. Nature Energy and Roquette article-header publication dates survive their explicitly reviewed layouts. Alberta robots and the dated major-project page both return HTTP 200 with correct text/plain robots negotiation; the report supports only a completed-by bound, not an exact commissioning date.

The next two failures were inspected:

- The old investinontario.com alias fails TLS hostname verification. The official current Invest Ontario publisher at https://www.investontario.ca/press-release/major-investments-secure-automotive-manufacturing-futures-windsor-and-brampton is a distinct canonical host. The alias failure, artifact and original Ontario Newsroom shell remain recorded. TLS verification is never disabled.
- Enel's retained corporate page contains its document in the single `main free-text section[data-content]` component. A source-ID-locked layout reads only this escaped original HTML and the single `main article-header time`. Original raw SHA-256 0172d782bdaca4f47d04b85e3e8aee4795dadfbe038cbfcc5e96b21b7eb57985 is retained. Its body supports Riverview, Castle Rock Ridge II, and the existing Castle Rock Ridge I operating since 2012. No date, body or operating status is synthesized.

Third diagnostic: run 35795592598, artifact 10723828564, independently verified ZIP SHA-256 7e986144dd0fbc12e8f567be07219b4cc00e3d6178e9525e0f6a92a9bf31c392. Ten of eleven paths pass, including Enel. Invest Ontario's HTTP 200 raw body cb75c2178b385fe00971912039192a2e6a560a0cf16ab31969ca6726defb41f9 contains all required anchors and the publication date. The ordinary parser selected a decorative image `article` instead of the press release. A source-ID-locked `.press-release-text .field--name-body` region plus the single `.press-release-date` preserves the actual content and date. Missing dates, anchors, ambiguous regions and unreviewed selectors continue to fail. The exact retained body passes locally after this correction.

Nine targeted regression tests cover MIME negotiation, continued blocking of access errors, date/anchor loss, duplicate regions, embedded-body ambiguity, original-failure preservation, prior-presence semantics, and the decorative-image regression. All 382 Python tests and all 43 JavaScript tests pass locally. The local command requires PYTHONPATH=src in the uninstalled source export; an initial invocation without that environment failed module imports and was rerun correctly. These results do not replace complete fresh two-live-capture proof and independent artifact review.

The Nature Energy PDF-derived status remains unresolved in this research release. No current project-status, legal-parent, first-entry, public-alert, customer-value or predictive claim is enabled. All temporary preparation workflows are absent from the delivered source.
