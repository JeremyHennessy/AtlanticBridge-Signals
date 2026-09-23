# Retained company changes to source-bound review

Baseline: PR115 c718949f90ba752bf8f2f53a2cd2614309c4f7a3.

This is a read-only client projection of the existing public metadata checkpoint. No new collector, source record, monitoring branch write, source rights, alert permission, predictive flag or workspace schema is introduced. The original public-news queue retains its publication-date semantics; a collapsed Needs review section loads observed changes separately.

Before rendering, verify the checkpoint's canonical SHA-256 and schema, unique source/record/event identities, safe URLs, observation/publication clocks, no source-body fields and false alert/backtest flags. Bind each source ID to exactly one existing review's evidence references. Missing or ambiguous bindings remain a disclosed count, not a guessed company join. Military/scope-held and geographically unconfirmed records are withheld from actionable rows, but not deleted from the underlying state. The view covers 30 observed days, at most 200 routed events; limits and other records remain visible as counts. Stale/failed collection is explicit.

Each routed item exposes the change clock, original first observation, source-publication value and clock meaning, raw hash, unresolved source-use state, and the exact company dossier/worklist path. A changed record is not necessarily a new publication, open vacancy, expansion event or commercial requirement. Metadata availability is not permission to republish a source body.

Tests: fifteen deterministic metadata tests, browser fixture roundtrip and corruption/storage isolation, and independent Python/JavaScript validation of one exact real production checkpoint on the PR runner. Hosted acceptance additionally renders actual retained changes. Existing source facts, CSS, historical dossiers and saved work remain unchanged.
