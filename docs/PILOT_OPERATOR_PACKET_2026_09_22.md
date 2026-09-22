# AtlanticBridge operator packet — workflow pilot

This extends `ANALYST_PILOT_2026_09_22.md`; it does not replace its evidence, identity or score gates. No participant is enrolled by this file. The supplied records template is intentionally empty. Keep participant identities, consent, client information and payment records outside this public repository.

## Recruitment and enrollment

Recruit 3–5 independent economic-development, investment-attraction or commercial-development users. Record their role, explicit consent, date and an operator-held consent reference using a pseudonymous reviewer ID. A developer test, elapsed browser session or downloaded feedback file is not proof of independent enrollment. Do not claim invitations were sent or users agreed until those actions actually occurred.

Invitation draft: “We are testing AtlanticBridge Signals, a source-backed research workflow for European companies' Canadian activity. The pilot distinguishes procurement evidence, project histories and items that still need qualification; it does not provide validated expansion probabilities. We would like you to compare a few relevant cases with your normal research process, record what was new or useful, and identify anything misleading. Participation and feedback are voluntary. We will agree what data to retain before you begin.”

## Session protocol

Use a recorded set of source-backed cases appropriate to the participant's sector and Canadian market. Freeze the case IDs and source snapshots before the comparison. Include irrelevant or already-known cases so positive-only selection does not inflate usefulness. The 50-target roster is an operational review selection containing known outcomes, not fifty qualified companies or an independent predictive holdout.

Have each participant perform the same defined research task using their usual method and the app. Record task order and counterbalance baseline-first versus tool-first across sessions to expose learning effects. Record active research time manually, with the original timing record; the existing page-view timer includes idle time and must not be used as time saved. Compare against manual research, announcements-only and CIPO-only where the case has suitable coverage. Missing coverage is not a zero-signal baseline.

In the app, open Review queue, inspect a dossier and original sources, save a next action, and export the worklist and review feedback. Record identity correctness separately from source support, usefulness and whether the information was already known. Leave unassessed answers null. Record false identity joins, duplicate leads, stale or cancelled projects, misleading location claims and unsupported first-entry wording.

Ask willingness to pay only after the task. Keep a stated willingness distinct from a verified payment and retain any payment evidence privately. A small favorable pilot cannot establish a validated twelve-month forecast.

## Private record contract

Copy `reviews/pilot/participant-records-template.json` to private storage. A participant needs `reviewer`, `role`, `recorded_date` (YYYY-MM-DD), `consented`, `independent_user`, and a private `consent_record` reference. Append the existing browser feedback exports to `reviews`; the reviewer label must match the consented ID. Unknown or unconsented submissions are excluded from independent-user metrics, not silently enrolled.

For a paired task, supply `reviewer`, `task_id`, `timing_basis: MANUALLY_TIMED_ACTIVE_RESEARCH`, `order: BASELINE_FIRST` or `TOOL_FIRST`, `baseline_method: MANUAL_RESEARCH`, `ANNOUNCEMENTS_ONLY` or `CIPO_ONLY`, `timing_record`, `baseline_seconds` and `tool_seconds`. Negative time savings remain negative.

Purchase feedback uses `reviewer`, `willing_to_pay` (boolean or null), `payment_verified` (boolean), and an `operator_payment_record` reference only when an actual payment has been verified.

Run locally: `PYTHONPATH=src python scripts/analyse_pilot.py /private/pilot-records.json --output /private/pilot-results-01.json`.

The command refuses to overwrite inputs or existing results, sends nothing externally, and reports separate reviewer denominators, unique alerts, unverified reviewer submissions, paired active-time results and paying participants. Empty records yield zero recorded participants and unknown time savings—not invented accuracy or commercial validation.

## Acceptance and decisions

Before the first external session: require exact hosted release acceptance; verify the original worklist survives reload/export/restore; verify source dates, identity bounds and failure states; qualify the companies appropriate to that session. After sessions, retain actual exports and timing records and report both useful and unsuccessful cases. Expand the cohort only when new coverage generates useful or earlier evidence rather than more unreviewed records. No Expansion Score weights are enabled by pilot feedback.
