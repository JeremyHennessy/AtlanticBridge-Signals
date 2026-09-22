# Current-feed scope review — 22 September 2026

## Boundary

The original product request excluded military-related opportunities. Canada-wide geography does not make every purchase by a Canadian federal buyer an expansion event in Canada.

This change applies a product-scope review after collection and before the live JSON export. It does not delete or rewrite source records, historical outcomes, identities, proof manifests, or backtests.

## Evidence-supported defects

The accepted raw CanadaBuys artifact for source SHA-256 `3c9a726d1d935a94ad974b1f3f094138ef3d27fd4f0f74ac837b6224dd3e48e1` contains 35 EU-supplier rows. Examples include embassy cleaning in Madrid, brokerage of residential property in Brussels, explicit DND requirements and armament/machine-gun procurement. Those should not appear as non-military Canadian expansion opportunities.

## Decisions

- Explicit military terms in the notice or published end-user field: excluded from the product feed, retained in `scope_audit.excluded_signals`.
- Entirely foreign stated delivery: excluded from the product feed, retained with the exact source record and reason.
- Foreign delivery plus an unresolved location, or CBRN use without civilian/military resolution: held in `scope_audit.review_required_signals`.
- Explicit Canadian delivery, including mixed domestic/foreign delivery: retained, without inferring an office, first entry or market fit.
- Missing/unrecognized delivery location: retained only as a Canadian-buyer relationship with location unverified, not operations in Canada.
- Supplier address country is not a verified ultimate-control country. Each surfaced explanation now states that distinction.

A civilian Coast Guard purchase is not excluded merely because its fuel is named Naval Distillate. Military scope is assessed from actual notice/end-user text, not supplier name, a guessed procurement code or that fuel label alone.

## Reproduction and acceptance

`python -m unittest tests.test_live_signal_scope -v`

The local full suite passed 235 tests. The isolated review of the earlier exported artifact yielded 24 retained events, 9 explicit exclusions and 2 held for review. These are a regression fixture result, not a claim about a newly refreshed source; the live-source workflow must inspect the current database's end-user fields and establish final counts before release.

`scope_audit` reconciles every input event. Product exclusions are not negative training labels. No scored predictions or regional recommendations are introduced. The established UI layout is unchanged.
