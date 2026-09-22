# CIPO Journal source extension acceptance

Acceptance date: 2026-09-22.

## Accepted proof

The source-only extension workflow run `35673341780` completed successfully on
exact head `8d9d7d83b393ba39d467b9d63a8deb81532ad827`.

It first re-proved the accepted historical prefix:

- 1,221 official Journal issues;
- 2000-01-05 through 2023-05-31;
- canonical inventory SHA-256
  `8a89eccf0c368e82de4fcd62bea62481930210b7ddf2c182b18e7f45e7521a2d`.

The bounded extension then proved:

- first extension issue: 2023-06-07;
- last extension issue: 2024-05-29;
- 52 / 52 official Journal issues complete;
- 51,269 Advertised Applications rows parsed;
- all 52 retrieved from official Journal HTML;
- all 52 parsed with the modern application/applicant parser;
- zero issue failures;
- zero structural errors;
- issue-audit canonical SHA-256
  `8f3d6871c47b8cec9b6eefd597f56eff0d8b8137942d72bae7f1eb55712e2101`.

Retained artifact:

- artifact ID `10671474936`;
- digest
  `sha256:e3ebd51e8af9c83eea8fef52e7e089b5c2b5a84950097cf3d2046e04ba54e458`.

The durable acceptance file is
`reviews/backtests/2026-09-22-cipo-journal-extension-manifest.json`.

## Boundary

This proof intentionally scans **no entity aliases**.

Therefore:

`identity_absence_inference_allowed = false`.

The result establishes that the official Journal archive and Advertised
Applications parser remain complete through the end of May 2024. It does not
establish that any particular company was absent from CIPO during the extension.

A company-specific non-hit can become proven absence only after that company's
explicitly reviewed legal aliases are scanned across every relevant issue with
zero unresolved alias occurrences.

## Research use

The extension removes a source-availability blocker for studying censored entry
anchors through September 2024 at the existing 3-month event-time cutoff. It
does not itself add entrants, controls, source states, or Expansion Score
weights.
