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
| GLEIF API / Golden Copy | Global | Candidate legal-entity resolution and ownership links | Golden Copy updated multiple times daily | **IMPLEMENTED — candidate layer** |
| TED Search API v3 | EU | Commercial maturity, contract awards, winner identity evidence, CPV sectors | Continuous | **IMPLEMENTED** |
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


## GLEIF candidate-resolution contract

The GLEIF API search contract and ownership endpoints were probed live on 2026-09-18 before implementation.

AtlanticBridge uses the API's legal-name search against the GLEIF Golden Copy and stores:

- source system/entity ID, original name, country and VAT evidence
- GLEIF Golden Copy publish timestamp
- query URL and total result count
- returned LEI, legal name and legal jurisdiction
- entity status/category
- registration authority and registered-as identifier
- legal/headquarters city and country
- API rank
- conservative normalized-name similarity diagnostics
- GLEIF relationship links and complete returned candidate JSON

Candidate matching is deliberately **not** an identity decision.

Resolution states are:

- `NO_RESULTS`
- `UNRESOLVED`
- `REVIEW_READY` — exactly one returned candidate has an exact normalized legal-name + jurisdiction match
- `AMBIGUOUS` — more than one exact-name + jurisdiction candidate
- `CONFIRMED` — reserved for an explicit later decision workflow
- `REJECTED` — reserved for an explicit later decision workflow

A `REVIEW_READY` result is not automatically confirmed. Refreshes also do not overwrite a future explicit `CONFIRMED` or `REJECTED` decision.

The GLEIF API exposes direct-parent, ultimate-parent and child relationship links. AtlanticBridge preserves those links now; parent/child graph materialization will occur only after source identities have been confirmed, so ownership is not attached to the wrong candidate.


## TED contract-award contract

The anonymous TED Search API v3 request contract was probed live on 2026-09-18 before implementation.

The production search uses:

- `POST https://api.ted.europa.eu/v3/notices/search`
- expert-query award filters for contract-award notice types
- explicit search scope
- `checkQuerySyntax: false` for result retrieval
- bounded page-number pagination
- a hard fail when the result count exceeds TED's 15,000-result page-mode cap, requiring the date window to be split

A probe with `checkQuerySyntax: true` returned no notices even for a known historical award query. Changing only that flag to `false` returned **618 notices** for 2024-01-25, confirming that syntax-check mode must not be used for production retrieval.

AtlanticBridge preserves each TED notice losslessly, including:

- publication number/date and notice type
- multilingual notice/procedure titles
- CPV values
- raw winner-name multilingual map
- raw winner-country, winner-identifier and winner-decision-date arrays
- tender/total values and currencies
- source links
- complete notice JSON and hash

TED winner arrays are not assumed to be positionally aligned with multilingual winner-name values.

A normalized winner mention is marked `SINGLE_WINNER_ALIGNED` only when the notice has exactly one unique winner name and at most one country, identifier and decision date. Otherwise the names are stored as `NAME_ONLY_UNALIGNED` with the raw arrays retained at notice level.

A TED award is evidence of commercial maturity. It is not, by itself, evidence of Canadian expansion and does not receive an Expansion Likelihood weight until historical predictive analysis is performed.
