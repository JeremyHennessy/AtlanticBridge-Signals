# UI proof dashboard

## Purpose

The first AtlanticBridge UI is a read-only evidence dashboard for the current Data Proof phase. It deliberately does not publish an Expansion Score or Nova Scotia Fit ranking while outcome timing, historical publication cutoffs and matched-control validation remain incomplete.

## Current views

- **Overview** — audit counts, research funnel, outcome classifications and publication-cutoff coverage.
- **Audited cases** — searchable/filterable case table with a drill-through drawer for business activity, audit notes, model-exclusion reason and evidence.
- **Evidence** — flat evidence ledger with source type and historical-publication status filters.
- **Sources** — implemented source families and their role in the evidence system.

The UI computes evidence publication status with the same interval semantics as `src/atlanticbridge/outcome_evidence.py`: explicit public-availability fields only; source dates, event dates and observation dates are not substitutes.

## Data source

The canonical source remains:

`reviews/outcome_audit/2026-09-20-cases.json`

The browser tries, in order:

1. `ui/data/outcome-audit.json` for a packaged deployment;
2. the repository-relative canonical audit file when the repository root is served locally;
3. the public raw `main` audit file as a fallback.

No browser action writes to the repository or SQLite store.

## Local preview

From the repository root:

```bash
python -m http.server 8000
```

Then open `/ui/` in a browser. Serving from the repository root allows the UI to read the canonical audit JSON directly without a copied data artifact.

## Verification

`tests/test_ui_contract.py` verifies that the audited case contract contains every field the UI depends on and that all evidence rows remain renderable through the canonical publication-status function.
