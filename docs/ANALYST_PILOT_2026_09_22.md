# Analyst workflow pilot — 22 September 2026

## Starting point and product purpose

Reviewed baseline: `c522a167684308188ae4a0a64d6dc9035ef3ecda`, the verified PR95–98 release. The product is non-military European commercial expansion intelligence for Canada, with Canadian market fit and evidence confidence kept separate from expansion likelihood. Nova Scotia is one market, not the default destination.

The current feed establishes Canadian-buyer relationships; it is not yet a validated early-warning expansion model. This release makes that evidence usable in an individual analyst's repeatable investigation workflow. It does not claim a completed multi-user SaaS product.

## Observed gaps addressed

- Live supplier names had no company dossier; the watch star was an ID-only bookmark.
- There was no place to record a next action or return to unresolved work after a notice aged out.
- Client recency used cached `recency_days`; that number did not advance without another payload generation.
- Empty amount text became numeric zero and missing currency defaulted to CAD in presentation.
- The country metric incorrectly called supplier address country ultimate control.
- Failure of historical-case loading blocked the current signal workflow as well.

## Shipped contract (requires release acceptance)

Company names open a shareable dossier containing all available notices for the exact supplier-name/country identity. It shows Canadian delivery versus buyer-only evidence, raw amounts/currency, separate public/event/source-check dates and source hashes. It does not make fuzzy parent/group joins or sum repeated/amended notices into a fabricated contract/revenue total.

The worklist stores explicit analyst status, research notes, next action and follow-up date in a new versioned browser-local store. Existing watch IDs are imported without deleting or overwriting the old watch key; historical saved cases stay separate. Missing/removed feed identities retain their saved work and are not called negative expansion findings. Unknown amounts and location stay unknown.

CSV export covers the filtered worklist and neutralizes leading spreadsheet formula/control characters. JSON backup contains all saved work. Import is staged for review, strictly validated and add-only; existing notes are never replaced. Blocked/quota/corrupt storage and cross-tab revision conflicts are explicit and cannot be reported as successful saves. Notes are text, never executable HTML, and public company links contain no private work.

A 48-hour **operational freshness threshold**, not a claim about a source publication SLA, labels stale source checks. Recency uses UTC calendar dates at viewing time. The current FY inventory limitation is stated; a 180/365-day filter does not prove full historical source coverage.

The UI remains browser-local: no account, team synchronization, automatic reminders, outreach delivery, shared CRM, or sensitive-client-data storage is advertised. Follow-up dates are visible worklist fields, not scheduled notifications.

Historical and live feeds are loaded independently. An unavailable feed never becomes a fabricated zero; saved work remains accessible even if both evidence files fail to load.

## Preservation and tests

No source collector, accepted data payload, identity review, proof manifest, outcome label, backtest or score is changed. Existing navigation and card styling stay in place; new view styles are isolated in workspace.css. Existing audited-case behavior retains its original acceptance suite.

Local baseline: 243 Python tests. New pure-JavaScript contract: 28 tests. Container rendering is offline with simulated storage/network, not hosted or WebKit acceptance. Real persistence, migrations, source-failure handling, backups, imports, conflicts, and Chrome/WebKit interactions are checked by the PR and hosted Playwright contract. Every actual live supplier dossier is checked against its available source rows during hosted acceptance.

## Next viability gates

1. Resolve single-publisher Pages configuration with authorized settings access. The compatibility wait does not guarantee healthy-data preservation during every source failure.
2. Establish durable per-source snapshots and source-isolated refreshes, then expose provenance and independent outage status. Client-stale labelling does not fix server-side data continuity.
3. Integrate CIPO events only after event/publication/observation clocks and current-versus-historical ownership are reviewed. Existing-record observations are not new filing alerts. Corporations Canada change evidence also needs a preserved baseline and reviewed foreign identity links.
4. Expand identity-qualified entrant strata and provincial evidence, preserve matched controls, and freeze a confirmatory design before independent validation. Do not publish an Expansion Score from the exploratory cohort.
5. Run an individual-analyst pilot measuring time to a defensible company assessment, accuracy of surfaced records, retained next actions and repeat use. These are proposed pilot measures, not customer results already achieved.
6. Add authenticated durable storage, access control, backups and team workflow only as a separately accepted release before a multi-user commercial offering.

The immediate deliverable is an evidence-backed investigation workflow. Commercial viability still depends on finding timely, genuinely relevant opportunities, not on the number of interface features or passing tests.
