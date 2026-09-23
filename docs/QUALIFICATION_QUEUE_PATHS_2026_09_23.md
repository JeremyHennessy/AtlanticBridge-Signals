# Complete qualification-to-worklist paths

Baseline: `2f72ccbdc499aa18f47a45a1a711c8b33603446c`, tree `bb6c860dc712d334eb4b8b607415c37a278a6866`.

Two synthetic regressions reproduce on the original source: a company-only fully qualified review produces zero qualified rows, and an old project's recently qualified status remains omitted because original-publication recency controls admission. Neither explains the real zero count: all production decisions remain HOLD.

This client-mapping change introduces stable company-only rows/dossiers using the pre-existing decision ID, without name matching or parent inference. The qualified view evaluates the unchanged six-check and 90-day status/review gates independently of the original announcement age. Historical publication dates and sources are never overwritten. The qualifying status source appears separately. Unqualified, undated and expired records do not become qualified; duplicate project bindings fail instead of silently overwriting a decision.

Company-only dossiers use the existing workspace schema and save/reload/backup mechanisms. Evidence and retrieval/publication clocks are displayed separately. Source outages retain saved notes without assigning supplier semantics. No production data, source collector, CSS, historical dossier, source-use permission or predictive gate is changed.

Tests: eight additional unit regressions cover both defects, stable identities, expiry, no name merge, undated evidence, source bindings, duplicate projects and immutability. Browser acceptance exercises actual Adyen review navigation and source references, save/reload/worklist roundtrip, exact storage preservation on source outage, and isolated qualified/expired fixture contexts on desktop/tablet/iPhone/narrow-phone. Synthetic qualification never enters production payloads.

The local source was reconstructed from the accepted production archive and its full Git tree hash matches the baseline. Local Python 441 tests and JavaScript 68 tests pass. Local Chromium endpoint navigation is blocked by this session's administrator policy; no policy bypass was attempted. Remote exact-head browser and hosted acceptance are required before release claims.
