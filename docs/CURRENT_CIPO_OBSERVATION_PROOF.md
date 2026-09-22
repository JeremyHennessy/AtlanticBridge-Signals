# Current CIPO observation proof

This is an isolated proof for the next source family. It does not add CIPO rows to the live Signals inbox or change any historical source state.

Inputs are the 13 reviewed foreign legal entities in the expanded research cohort, not guessed names from Canadian investment vehicles. The existing official CIPO owner-search and detail parser are reused without changing their historical semantics.

Each query is bounded to ten detail requests. Full public response bytes are saved under SHA-256 names with URL, byte-count and hash manifests; authentication/cookie headers are not retained. Per-query truncation and failures remain explicit.

Only an exact current-owner/detail match becomes an observation. It is not assumed to be the owner at filing, a new filing alert, a newly public event, first Canadian entry or a model label. Filing dates, observation time and unverified public-availability dates remain separate. No search non-hit is promoted to proven absence.

Six local regression tests cover exact-owner matching, mismatches, zero-result unknowns, transport failures, bounded detail coverage and exclusion of unreviewed identities. The dedicated PR workflow must establish live source transport and current record parsing before this adapter is accepted. Broader live signal integration requires its own reviewed publication/recency semantics and UI acceptance.
