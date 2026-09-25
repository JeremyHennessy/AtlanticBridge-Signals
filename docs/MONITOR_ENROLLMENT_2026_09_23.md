# First additive production monitor enrollment — 23 September 2026

Baseline application: `ba3b1d57fa31e54c4b73cb7c2ded94a391e81b90`.

This increment expands the existing persistent monitor using the same accepted ledger and capture engine. It does not create a parallel source pipeline, a prediction, a first-entry label, or a public alert.

## Proposed additions

Five companies already reviewed with the exact generic source parser are added:

- Ubisoft — current Sherbrooke studio/careers page.
- Accenture — current St. Catharines onsite hiring page.
- Sanofi — current Canada manufacturing page.
- Cellcentric — current supplier-inquiry page.
- Roquette — current Canada locations page.

Together with Mistral AI, Giesecke+Devrient, Adyen Canada Ltd., DeepL and Pleo, this makes **10 company identities represented in the company-specific monitor** after a successful production enrollment. The Montréal International discovery index remains a separate agency source. Source paths and companies must continue to be reported separately.

These five contracts are not newly guessed. Ubisoft/Accenture/Sanofi are tied to accepted proof artifact 10729310481; Cellcentric/Roquette are tied to 10729682735. The restricted evidence archive already pins both artifacts. Fresh PR proof must still recapture all five sources twice.

## Migration policy

Source enrollment is addition-only. Removing a source fails. Every new source needs an exact reviewed contract hash, accepted proof artifact/hash and the policy `ADDITIVE_BASELINE_NO_EVENTS`.

Before any new source state is written, all additions are fetched and parsed successfully. If one fails, no new source is baselined. On success, the first observation for each new source is a baseline and **must emit zero review events**. Existing source identities and first-seen clocks are preserved. The normal second process must see the sources as already enrolled.

The reliability metric is changed to the **current source set only**. Days accumulated by the old eight-source cohort cannot count toward the new thirteen-source cohort. The first successful expanded production run therefore starts the expanded cohort at one successful UTC day; it does not inherit the previous 2/14.

## Source-use boundary

Enrollment is evidence monitoring, not permission to redistribute source content. Durable public state continues to retain metadata/fingerprints only. Raw responses remain access-controlled. Any review with `source_reuse=CONTRADICTED` must not gain a new public corporate-source hyperlink from monitored-change routing.

## Acceptance

Merge only after: all unit tests; exact current monitoring-state restore; fresh two-capture proof of all five additions; zero baseline/replay events; no removal of existing source contracts; two independent monitor processes on a disposable copy; and exact browser regression for the source-use link boundary. After merge, verify the real monitoring-state commit has 13 source paths, all five additions marked as baseline with zero change events on their first run, all prior first-seen clocks preserved, and current-cohort reliability reset rather than inflated.

This is a bounded enrollment step, not completion of the 50-target roster or the 14-day operational trial.
