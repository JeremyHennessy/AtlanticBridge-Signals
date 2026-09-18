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
| CIPO live Canadian Trademarks Database | Canada | Current trademark ownership and filed-date evidence | Live database | **IMPLEMENTED — targeted owner search** |
| CanadaBuys award notices | Canada | Federal award, supplier, value, category and geography evidence | Current fiscal file updated daily | **IMPLEMENTED** |
| Statistics Canada tables 12-10-0175-01 / 12-10-0173-01 | Canada | Nova Scotia/Canada EU trade context by market and NAPCS section | Monthly major markets + annual full EU | **IMPLEMENTED** |
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

## Investment Canada historical-pagination contract

The first page of the public `/all` index contains only 50 current rows. It is not a historical corpus.

Production historical ingestion now crawls the source's complete alphanumeric bucket index (`0-9`, `a-z`) with page-level completeness checks. The accepted live crawl on 2026-09-18 covered 681 pages and produced 33,106 row appearances.

Because the public index can repeat a record across bucket/page views, page location and raw display text are not used as primary identity. Historical records are deduplicated by stable source structure:

- certification month;
- notification type;
- investor Drupal node ID;
- country of ultimate control; and
- Canadian-business node IDs.

The accepted crawl produced 32,369 unique records from 33,106 appearances. All unique rows had investor source node IDs. A structural duplicate with conflicting raw content causes a hard failure.

The authoritative historical replacement is transactional and stores a SHA-256 snapshot for every fetched page.

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


## CIPO trademark contract

AtlanticBridge tested three official CIPO delivery paths on 2026-09-18.

### Bulk IP Horizons web download

The quarterly research ZIPs and weekly ST.96 archives are published from `opic-cipo.ca`. Standard GitHub Linux runners could not establish a trusted TLS chain to that host:

`SSL certificate problem: unable to get local issuer certificate`

Both Python/OpenSSL and system `curl` failed certificate validation. AtlanticBridge does **not** disable TLS verification.

CIPO also documents an SFTP delivery path, but credentials are issued by CIPO. Historical bulk backfill therefore remains blocked until either the HTTPS certificate chain is corrected or SFTP credentials are available.

### Secure live database

The current Canadian Trademarks Database at `ised-isde.canada.ca` is securely reachable and exposes the same JSON endpoint used by CIPO's own public UI.

The source contract observed from CIPO's own `search.js` is:

- establish a public search session
- POST JSON to `/cipo/trademark-search/srch`
- current-owner field: `searchfield1 = "ownname"`
- response fields include `numFound`, `numReturned`, and `docs`
- result detail route: `/cipo/trademark-search/{id}?lang=eng`

The public UI supports a maximum returned-result setting of 5,000. Production owner searches therefore request 5,000 and **fail closed** if:

- `numFound > 5000`
- `numReturned != len(docs)`
- `numReturned != numFound`

The owner-search endpoint is not an exact-name identity lookup. A live search for `Siemens Aktiengesellschaft` returned 671 records; quoting the name still returned 668. Search hits are therefore candidates only.

Detail pages are the identity/evidence layer. They expose filed date, registration data, owner/applicant information, priority claims and action history. A detail record is marked `EXACT_DETAIL_OWNER` only when the normalized detail-page owner exactly matches the query owner.

Detail enrichment is explicitly bounded and reports whether coverage is partial or complete. Partial enrichment must never be interpreted as a complete trademark history.

CIPO trademark evidence remains an unweighted candidate pre-entry signal until historical predictive testing is complete.


## CanadaBuys award-notice contract

The current 2026–27 CanadaBuys award-notice CSV was probed live on 2026-09-18 before implementation.

The official public file endpoint returned HTTP 403 to a cold programmatic request from a standard GitHub runner. Establishing a normal public session through the CanadaBuys procurement-data page and then downloading the published file with the same session succeeded with HTTP 200. Production retrieval follows that public session-backed path and does not bypass authentication or TLS.

Observed live source:

- compressed/download bytes: **14,079,894**
- SHA-256 at probe time: `2912c321aed256b9a47122771b726dfecbd69f649ddfdc6c6f69e0c2e52986cd`
- columns: **80**
- records: **3,925**
- unique `(referenceNumber, amendmentNumber)` keys: **3,925**
- duplicate source keys: **0**

The collector validates the full observed 80-column schema and fails closed on a duplicate source key.

High-value extracted fields include:

- reference/amendment/solicitation/contract numbers
- publication, award, amendment, start and end dates
- contract amount, total value and currency
- award status and instrument/amendment type
- GSIN and UNSPSC
- procurement category, notice type and procurement method
- selection criteria and limited-tendering reason
- trade agreements and delivery regions
- supplier legal name/address/country
- contracting entity
- award description

All 80 source fields are also preserved as canonical row JSON.

Supplier-country values are normalized conservatively because the live file mixes ISO codes and names. The EU-27 flag is derived from that normalized country, while the raw source country remains stored unchanged.

A CanadaBuys federal award is direct evidence of Canadian commercial activity. It is not automatically treated as a pre-entry signal or scored until the historical model distinguishes awards that precede an Investment Canada entry from awards occurring after an established Canadian presence.


## Statistics Canada trade-context contract

AtlanticBridge uses two official Statistics Canada customs-basis merchandise-trade tables because no single table provides both monthly provincial timeliness and full EU-country breadth.

### Monthly major-market context — table 12-10-0175-01

PID: `12100175`

The live source was probed on 2026-09-18 and contained:

- **3,860,857** source rows
- latest reference month: **2026-07**
- 17 columns
- province/territory geography
- imports, domestic exports and re-exports
- 12 NAPCS merchandise sections plus total merchandise
- six EU countries among the principal trading partners:
  Belgium, France, Germany, Italy, Netherlands and Spain

For Nova Scotia in July 2026, the six EU markets produced 156 source rows across the current available trade/commodity combinations.

### Annual full-EU context — table 12-10-0173-01

PID: `12100173`

The live source was probed on 2026-09-18 and contained:

- **2,545,452** source rows
- latest reference year: **2025**
- 17 columns
- province/territory geography
- imports and exports
- NAPCS merchandise sections plus all-sections total
- all **27 EU countries**

Nova Scotia had 702 EU-country rows in the latest 2025 annual source.

### Storage and interpretation

Production downloads the official full-table ZIP through Statistics Canada's WDS, validates the exact observed schema, hashes the archive, then stores only rows needed by AtlanticBridge:

- geography: `Nova Scotia` and `Canada`
- partner: the six named EU principal markets for the monthly table
- partner: all EU-27 countries for the annual table

The two cadences remain separate. Annual exports are not silently equated to monthly domestic exports.

Values are stored exactly as published, including status/symbol/termination fields. The source uses a scalar factor of thousands for these dollar series; summaries expose both the published thousand-dollar value and a derived CAD value.

Statistics Canada trade data is **aggregate market context only**. It does not prove that any individual company plans to enter Canada and cannot independently create an Expansion Likelihood signal.

The broad NAPCS sections `Aircraft and other transportation equipment and parts [C21]` and `Special transactions trade [C23]` are preserved for source integrity but are excluded from any future AtlanticBridge scoring because they can contain mixed or non-commercially-comparable activity, including defence-related content.
