# Source Registry

Status values:

- **IMPLEMENTED** — collector/parser exists.
- **NEXT** — planned for the current data-proof sequence.
- **LATER** — useful after the predictive proof is established.
- **VERIFY** — source is useful but access/reuse/automation details still need verification before implementation.

| Source | Jurisdiction | Primary value | Cadence | Status |
|---|---|---|---|---|
| Investment Canada Act Decisions & Notification Index | Canada | Historical entry/acquisition outcomes | Monthly/public index | **IMPLEMENTED** |
| Corporations Canada open data/API | Canada | New subsidiaries, offices, directors, status changes | Real-time API / open data | **NEXT** |
| CORDIS Horizon Europe open data | EU | Company/research relationships with Canadian organizations | Open datasets | **NEXT** |
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

## Current source contract: Investment Canada

The initial collector preserves:

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
