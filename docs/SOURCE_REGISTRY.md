# Source Registry

Status values:

- **IMPLEMENTED** — collector/parser exists.
- **NEXT** — planned for the current data-proof sequence.
- **LATER** — useful after the predictive proof is established.
- **VERIFY** — source is useful but access/reuse/automation details still need verification before implementation.

| Source | Jurisdiction | Primary value | Cadence | Status |
|---|---|---|---|---|
| Investment Canada Act Decisions & Notification Index | Canada | Historical entry/acquisition outcomes | Monthly/public index | **IMPLEMENTED** |
| Corporations Canada active CBCA open data | Canada | New federal corporations and registered-office/status changes | Typically daily | **IMPLEMENTED** |
| CORDIS Horizon Europe open data | EU | EU-Canada project/organization relationships and funding context | Monthly bulk archive | **IMPLEMENTED** |
| GLEIF LEI + relationship data | Global | Entity resolution, parent/child identity | Frequent | **NEXT** |
| TED procurement data/API | EU | Commercial maturity, awards, geography, CPV sectors | Continuous | **NEXT** |
| CIPO IP Horizons — trademarks | Canada | Pre-entry brand/market intent | Weekly XML / quarterly research data | **NEXT** |
| CanadaBuys open procurement data | Canada | Canadian tenders, awards, suppliers | Frequent/open data | **NEXT** |
| Statistics Canada trade data | Canada | Sector/country/province context | Monthly | **NEXT** |
| Canadian Importers Database | Canada | Potential distributor/importer mapping by product/origin | Periodic | **LATER** |
| Nova Scotia procurement | Nova Scotia | Local buyer/award signals | Ongoing | **LATER** |
| Nova Scotia Registry of Joint Stock Companies | Nova Scotia | Local incorporation verification | Public search | **VERIFY** |
| Invest Nova Scotia disclosures | Nova Scotia | Historical expansion/incentive validation | Event driven | **LATER** |
| Company careers/newsrooms | Company | Hiring/market-entry intent | Variable | **LATER** |

## Investment Canada contract

The collector preserves:

- certification month
- notification type
- investor text exactly as published
- country of ultimate control
- Canadian-business cell exactly as published
- source URL/bucket
- raw record hash
- observation timestamp
- full-page snapshot hash

The Canadian-business cell is intentionally not over-normalized in Data Proof 001. Historical variation must be inspected before reliable business-name, city and activity extraction is locked.

## Corporations Canada contract

The active-CBCA source schema was probed live on 2026-09-18 before implementation. The current English CSV contains 18 fields:

- corporation number and business number
- two corporate-name forms
- governing legislation
- status and status detail
- anniversary date
- year of last annual filing
- date of last annual meeting
- registered-office street, city, province/territory, country and postal code
- minimum/maximum director counts

The source is approximately 100 MB and is streamed to disk. The first run is a **baseline**. Later runs use **diff** mode and emit only:

- `CORPORATION_APPEARED`
- `CORPORATION_CHANGED`

The collector deliberately does **not** infer a disappearance from absence in the active file. A disappearance signal will only be added after a source-completeness gate and inactive-corporation reconciliation exist.


## CORDIS Horizon contract

The live Horizon archive was probed before implementation on 2026-09-18. The collector requires the observed exact schemas for:

- \`project.csv\` — 22 fields
- \`organization.csv\` — 25 fields

The archive is handled as a full monthly snapshot. Projects and participations are rebuilt inside one transaction, so a parser, foreign-key, or completeness failure rolls back to the previous complete snapshot.

CORDIS \`organisationID\` is treated as a **source-local identifier only**. It is not promoted to a global company/legal-entity identity. VAT numbers, names, addresses, organization URLs and future GLEIF evidence will be used for entity resolution.

Activity-type codes such as \`PRC\`, \`HES\`, \`REC\`, \`PUB\` and \`OTH\` are preserved as raw source codes in this phase. Business semantics are not inferred from the code without an authoritative mapping.

The relationship summary derives only direct evidence:

- Canadian participation rows/projects/organizations
- EU-27 participation rows on projects that contain a Canadian participant
- distinct EU-27 source-local organization IDs on those projects
- raw activity-type and country distributions

A shared Horizon project is a relationship signal, not proof of commercial expansion.
