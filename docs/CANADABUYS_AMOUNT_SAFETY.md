# CanadaBuys: amount interpretation and evidence roles

Local implementation update: 6 November 2026. Not a refreshed source dataset.

## Contract history is not the award-notice feed

Research supplied for this change identifies the March–April 2026 CanadaBuys contract-history restructuring: repeated values/dates were corrected, and certain administrative, placeholder-supplier and call-up records were removed. Official reference: https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/COsoutien-CHsupport-eng.html

This product ingests the separate awardNotice CSV. The contract-history notice does not establish that this feed was affected. The reference was supplied with the source research; this implementation did not fetch or independently revalidate the federal endpoint.

Do not total raw history rows, treat every amendment as new spending, or infer cancellation/reduced spending from a removed history row alone. Identify the dataset, snapshot hash/date, contract reference, revision, amount type and currency first. Reconcile revisions before comparing or aggregating. A published value is not automatically a payment, incremental value, supplier revenue, or market demand.

## Protective behavior

- Raw source records, individual amount/currency strings, raw JSON, hashes and source dates are unchanged.
- Per-supplier contract_amount_cad and live/scoped summary cad_contract_amount are null, with amount_aggregation_status = WITHHELD_UNRECONCILED_NOTICE_AMOUNTS and a plain-language amount_aggregation_reason.
- Null means withheld, not zero or unavailable source rows. This applies even to a single notice, zero-valued notices, only non-CAD notices, empty windows and unavailable feeds. Individual published zero values remain zero.
- Notice counts continue counting records. They do not count distinct contracts, incremental purchases or new operations.
- Scope filtering cannot restore an aggregate or remove the amount warning from retained audit rows.
- The browser supplies its own warnings for older payloads and labels amounts “Published notice value.” It does not calculate a replacement total.
- Older consumers expecting a numeric string must explicitly handle null. Do not coerce null to zero. The added status field explains why the total is withheld.

## Three separate roles

Announced expansion: a dated source explicitly describes a plan. It does not prove completion, first entry or current demand.

Commercial/research signal: source-backed activity or a relationship worth checking. Award notices belong here, not automatically under announced expansion or open procurement.

Relevant opportunity: an analyst-supported fit to a defined need and next action, after identity, civilian scope, Canadian relevance and current status checks. This guide adds no automatic qualification. Existing “Qualified for investigation” gates remain unchanged. No expansion probabilities, lead eligibility or source activation are introduced.

The separate local analyst workspace receives only this role glossary. It does not ingest CanadaBuys, and the contract-history warning is not incorrectly applied to its BODACC, federal grants or Nova Scotia tender inputs.

## Verification scope

Initial focused checks were followed by complete offline integration tests. The minimal release was reconstructed from exact main commit ab8515afbc41ef24e2a509c71b2ced9aa5f9cba5 and passed 488 Python and 103 Node tests, deterministic dashboard generation, the strict publication gate and workflow syntax checks. No test was skipped and the offline guards recorded no network/process attempts.

This verifies source logic and mocked UI behavior, not actual browser acceptance or current source freshness. Expected PR checks retain the existing ISED Investment Canada and CanadaBuys source proofs. The changes do not add a collector, qualify opportunities or accept an amount aggregate.

No live source requests or deployment occurred during local verification. Remote CI and deployment results must be checked for the exact proposed commit.
