# Tranche-two source repair evidence

Accepted production baseline: 686d8b9fe11cb026edc9d0348a8adeb4aff627b9. Repairs remain on PR #107 until exact-head acceptance.

Initial diagnostic: run 35794133308, artifact 10723391513, ZIP SHA-256 3edea9f5529aefa4c8628307efa79950c7904b19104ca430e11ed49e069826f4.

Second diagnostic: run 35794985899, artifact 10723187655, ZIP SHA-256 f0a73ae39bf772621b1c33a1bbc360027bc48cb808513eb40b4677524cce20f7. Nine of eleven requested paths now pass. Nature Energy and Roquette article-header publication dates survive their two explicitly reviewed layouts. Alberta robots and the dated major-project page both return HTTP 200 with correct text/plain robots negotiation; the captured report supports only a completed-by bound, not an exact commissioning date.

The remaining two failures were inspected:

- The old investinontario.com alias fails TLS hostname verification. The official current Invest Ontario publisher at https://www.investontario.ca/press-release/major-investments-secure-automotive-manufacturing-futures-windsor-and-brampton is separately verified in public source review. The alias failure, artifact and original Ontario Newsroom shell remain recorded. TLS verification is never disabled.
- Enel's retained corporate page contains the full document in the single `main free-text section[data-content]` component. The ordinary text extractor omits attribute content. A source-ID-locked layout reads only this escaped original HTML and the single `main article-header time`. The original raw SHA-256 0172d782bdaca4f47d04b85e3e8aee4795dadfbe038cbfcc5e96b21b7eb57985 is retained. Its body supports Riverview, Castle Rock Ridge II, and the existing Castle Rock Ridge I operating since 2012. No date, body or operating status is synthesized.

Eight targeted regression tests now cover MIME negotiation, continued blocking of access errors, date/anchor loss, duplicate regions, embedded-body ambiguity, original-failure preservation and prior-presence semantics. All 381 Python tests pass locally, and the exact captured Enel document passes the repaired parser. These local results do not replace the required complete two-live-capture proof and artifact review.

The Nature Energy PDF-derived status remains unresolved in this research release. No current project-status, legal-parent, first-entry, public-alert, customer-value or predictive claim is enabled. Both temporary preparation workflows are absent from the final delivered source.
