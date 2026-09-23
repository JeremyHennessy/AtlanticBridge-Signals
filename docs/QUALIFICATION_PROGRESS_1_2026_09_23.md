# Qualification progress tranche 1 — 23 September 2026

Baseline: `c1fe9ed88bea9ec351ca047d715f441323c0c097`, after accepted source proof PR #110.

This increment integrates accepted artifact **10729310481** (ZIP SHA-256 `478167783afbd109deccc8a4576252fef895a67c9585ce8c61c45ae937336365`) into the existing 20-decision review register. The proof contains two clean captures of five official sources, five stable observations per capture, zero source failures or change/replay events, and 20 retained raw-response hashes.

## Decision changes

No company is promoted to `QUALIFIED_FOR_INVESTIGATION`.

- **Adyen Canada Ltd.** — legal identity, Adyen group relationship, civilian payment-services scope, Canadian relevance and current status are supported by Adyen's dated July 1, 2026 legal page. Source-reuse/legal-use review remains unresolved, so the decision remains HOLD.
- **Ubisoft Sherbrooke** — current studio activity/hiring, civilian game-development scope and Canadian relevance are supported by the current official location/careers page. The page is undated, so its retrieval clock is not used as a public status date. Legal entity/group and source reuse remain unresolved.
- **Accenture St. Catharines** — a current official job page supports onsite St. Catharines activity, hiring and civilian scope. The page is undated. Exact Canadian legal operator/group and source reuse remain unresolved.
- **Giesecke+Devrient Montréal** — the June 16, 2026 issuer release supports the hub launch, started projects and Canadian relevance. It is outside the 90-day current-status window by the September 23 review date, and the release explicitly covers security-critical domains, so civilian-only scope is not inferred.
- **Sanofi Canada** — the current Canada page supports active Canadian biopharma operations, civilian scope and the Toronto influenza-facility context. The page is undated and does not establish an exact production-start date. Exact legal entity/group and source reuse remain unresolved.

## Product boundaries

The Review queue keeps these records in HOLD. A supported check is source-bound to a retained URL/hash/observation. Undated current pages can reduce uncertainty but cannot satisfy the queue's dated <=90-day promotion rule. Historical/current evidence remains separate from predictive scoring, first-entry labels and public alerts.

The accepted qualification artifact is added to the deterministic pilot-release build and to evidence-retention pins so the exact bytes remain reproducible after Actions expiry. No CSS, layout, procurement collector, persistent-monitor state, worklist semantics or Expansion Score gate is changed.
