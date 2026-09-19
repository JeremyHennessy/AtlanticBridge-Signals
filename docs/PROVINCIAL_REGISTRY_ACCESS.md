# Provincial Registry Source Access Review

Review date: **2026-09-19**

## Purpose

Data Proof 010 confirmed only **27 of 382** recent EU new-business outcomes through the federal corporate registry. The remaining outcome/geography queue is:

| Province / status | Unresolved outcomes |
|---|---:|
| Ontario | 164 |
| Quebec | 120 |
| British Columbia | 50 |
| Alberta | 15 |
| Nova Scotia | 12 |
| Saskatchewan | 3 |
| Unknown | 3 |
| Manitoba | 2 |
| New Brunswick | 2 |
| Prince Edward Island | 1 |

This review determines which provincial sources can be automated and reused in a commercial AtlanticBridge product.

## Decision matrix

| Source | Coverage opportunity | Technical result | Reuse / automation result | Production decision |
|---|---:|---|---|---|
| Canada's Business Registries / MRAS | Multi-province | Public web app exposes a search service | Its own terms state **No Automated Tools** for data collection | **DO NOT AUTOMATE** |
| Quebec Registre des entreprises open files | 120 | Structured linked bulk files available | Dataset is published under **CC BY-NC-SA** | **DO NOT USE IN COMMERCIAL PRODUCT without separate permission/licence** |
| BC OrgBook API v4 | 50 | Public developer API works; legal-name autocomplete returns registry source IDs | OrgBook says its API is for integration into applications, but the data are labelled **Access Only**. BC licensing guidance states Access Only material may not be reproduced without written permission | **RESEARCH ONLY until written data permission is obtained** |
| BC Registry Search API | 50 | Official real-time API, including bulk search | Requires Premium/API account, signed API Terms of Use, API key, Account ID and applicable fees | **SUPPORTED COMMERCIAL PATH — CREDENTIALS REQUIRED** |
| Nova Scotia RJSC public search | 12 | Public search exposes names, status, addresses and registration dates | No full RJSC company dataset was located in Nova Scotia Open Data. The licensed open-data catalogue only exposed narrow registry-derived subsets such as co-operatives | **DO NOT SCRAPE; seek supported data/API route or use licensed subset only where applicable** |
| Ontario Business Registry public search | 164 | Free basic public lookup is available | No supported reusable bulk/API contract has been established for AtlanticBridge | **DO NOT SCRAPE; seek supported API/intermediary route** |
| Alberta Corporate Registry | 15 | Current/historical searches available through registry services | Searches are paid; authorized subscribers cannot retrieve/sell/distribute registry information on behalf of third parties outside permitted professional-service use | **AUTHORIZED PAID SOURCE ONLY** |

## Evidence

### MRAS

The official Canada's Business Registries web application identifies itself as the Multi-jurisdictional Registry Access Service and currently lists Alberta, British Columbia, Manitoba, Nova Scotia, Ontario, Quebec, Saskatchewan and Corporations Canada as participating registries.

The same application's terms modal states:

> No Automated Tools — We don't allow the use of automated tools to collect data.

AtlanticBridge will not call the discovered search API in an automated collector.

### British Columbia

OrgBook's official developer documentation says the v4 API is purpose-built for developers to integrate organization data into their applications. Live API probing confirmed the public v4 service is reachable and returns BC Registry source identifiers.

However, OrgBook states the published data are subject to **Access Only Data Terms and Conditions**. BC DataBC guidance states that Access Only material may not be reproduced without written permission.

The sanctioned commercial integration path is therefore the **BC Registry Search API**, which requires:
- a BC Registries account;
- API access request and signed API Terms of Use;
- production API key;
- Account ID;
- payment method / applicable service fees.

References:
- https://orgbook.gov.bc.ca/about/orgbook-api
- https://github.com/bcgov/orgbook-bc-api-docs
- https://developer.api.bcregistry.gov.bc.ca/en-CA/products/rs/overview/
- https://developer.api.bcregistry.gov.bc.ca/en-CA/products/get-started/account-setup/

### Quebec

The official Registre des entreprises dataset is technically suitable for entity matching, but its published licence is **Creative Commons Attribution-NonCommercial-ShareAlike**.

AtlanticBridge is intended to be commercial, so the bulk source is not incorporated into production under that licence.

### Nova Scotia

The public Registry of Joint Stock Companies search exposes business/non-profit information including official names, addresses and registration dates.

Nova Scotia Open Data is licensed for broad reuse under the Open Government Licence – Nova Scotia, but catalogue searches on 2026-09-19 did not identify a full company/business export of the RJSC registry. The only directly registry-derived business dataset found was the narrower **Nova Scotia Co-operatives** dataset.

AtlanticBridge will not infer that the public search UI is a reusable bulk API.

References:
- https://www.novascotia.ca/search-business-or-non-profit-information-filed-registry-joint-stock-companies
- https://data.novascotia.ca/d/k29k-n2db

### Alberta

Alberta's official guidance directs corporate searches through registry agents and applies government/service fees. Registries Online is also governed by an access agreement and restricts subscribers from retrieving, selling or distributing registry information on behalf of third parties outside the permitted use.

References:
- https://www.alberta.ca/find-corporation-details
- https://www.alberta.ca/registries-online-subscribers

## Product rule

A source being publicly searchable is **not** sufficient authorization for automated commercial ingestion.

Provincial records may enter AtlanticBridge production only when at least one of these is true:

1. the source is released under a licence compatible with commercial reuse;
2. the source explicitly permits API integration/reuse for the intended purpose; or
3. AtlanticBridge has an authorized account/agreement granting that access.

A blocked provincial source is represented as **UNRESOLVED / ACCESS_REQUIRED**, never as no corporation and never as a negative expansion signal.

## Immediate consequence

Provincial automation cannot yet expand the 27-record federal gold cohort without additional source permission or credentials.

The next unblocked workstream is therefore:

**resolve foreign operating/parent identities for the 27 detail-confirmed federal entry entities, while preserving the provincial access queue for later authorized recovery.**
