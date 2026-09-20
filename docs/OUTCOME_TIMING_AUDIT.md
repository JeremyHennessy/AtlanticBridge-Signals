# Notification timing and curated identity audit

Audit date: 2026-09-20.

The 27 confirmed federal entities remain valid registry matches. They are **not 27 verified first Canadian operating entries**. The 94-day median is the interval from incorporation to the start of the notification month. No score weights are justified by this statistic.

## Baseline and scope

- Preserved baseline: `72a7884160914287c939eb52fd2b1e0495a115e3` and [successful batch-04 acceptance](https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35485089110).
- Baseline corpus: 32,369 historical records; 382 EU-controlled new-business outcomes in 2019–2025; 27 federal matches. These are baseline counts, not a newly measured complete-corpus recall estimate.
- The attempted [full rebuild](https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35515294530) failed when Investment Canada returned HTTP 503 after bounded retries. No full rebuild is claimed.
- Recovery: reconstructed the 26 queued cases plus the separately confirmed Backbase case, retrieved all 27 matching notification records, and refreshed all 27 official corporation-detail records. The newly downloaded active-register CSV matched the baseline SHA-256 `ccb35c240c48dadea7b00b0bd37dd364cd4199ac9f239216422ab06a7e546331` exactly.
- All 20 outcome IDs printed in the baseline sample were matched to the refreshed records. The remaining seven were recovered from the queue, official notification pages and corporation records. No sample truncation is used.

Machine-readable evidence and decisions:

- [Baseline acceptance summary and queue](../reviews/outcome_audit/2026-09-20-baseline.json)
- [All 27 reviewed cases](../reviews/outcome_audit/2026-09-20-cases.json), including notification node IDs, source URLs, source hashes, corporation-name/activity projections and individual follow-up notes
- [All 12 historical identity approval dispositions](../reviews/outcome_audit/2026-09-20-identity-dispositions.json)

Registry projections intentionally contain corporate names, status and activities. Their accompanying raw-response hashes identify the complete fetched response; projections are not represented as the complete hashed payload. The acceptance workflow retains complete source responses separately for 90 days.

## Outcome findings

| Finding | Cases | Treatment |
|---|---:|---|
| Prior Canadian presence supported by primary material | 2 | Bolton and TOPdesk: exclude their notification months as assumed first-entry dates |
| Prior commercial presence supported only by secondary material | 0 | TOPdesk is upgraded by the City of Toronto's primary annual report evidence |
| Subsidiary founding corroborated by company news | 1 | LINET: legal founding confirmed; first operations still unresolved |
| Registry establishment only; operating outcome unresolved | 24 | Require dated operational and notification-purpose evidence |
| Exact first Canadian operating dates established | 0 | No positive first-entry labels promoted |
| Cases eligible for first-entry model training from this audit | 0 | Unresolved is not a negative outcome |

All 27 selected federal events are incorporations. Twenty-five occurred before the notification month and two occurred within it. Among the 25 earlier events the median remains **94 days**. Same-month negative numbers in the table are arithmetic relative to day one of the month, not evidence of an event occurring after notification.

**Bolton:** an [Italian Cultural Institute Toronto event page](https://iictoronto.esteri.it/en/gli_eventi/calendario/bocconi-alumni-toronto-andrea-pugliese-2/) for March 2020 describes establishment of a Toronto subsidiary in 2017 and Canadian retail distribution. The [2020 company report](https://www.bolton.com/sites/default/files/2024-07/Bolton-Group-Sustainability-Report-2020-1.pdf), PDF page 6, also lists Bolton BG Canada. This supports prior presence. It does not establish an exact first-operations day or explain the October 2025 notification. The 2017 reference has year precision only.

**TOPdesk:** the 2015-09-23 registry incorporation predates the July 2022 notification by 2,473 days. Invest Toronto's [2015 Annual Report](https://www.toronto.ca/legdocs/mmis/2016/ex/bgrd/backgroundfile-93038.pdf), received by City Council in 2016, states that Invest Toronto assisted with establishment of TOPdesk's first Canadian location in Toronto in 2015. This upgrades prior presence from secondary reporting to primary municipal evidence. The milestone has year precision only, so `first_canadian_operations_date` remains unset and the 2022 notification purpose remains unresolved.

**LINET:** [official group news dated 2019-10-21](https://www.wi-bo.com/de/Linet/news/news-and-press-releases/2019/New-Subsidiary-in-Canada-will-Share-Clinical-Experience) corroborates founding on 2019-02-21 and describes forthcoming Canadian support and partner coordination. The publication falls in the notification month. It does not prove that this evidence was publicly available before operations began.

The case review is complete as a disposition of the available evidence, not an exhaustive reconstruction of every operating history. The 24 unresolved cases have explicit next research questions in the JSON. Acquisition, reorganization, delayed notification, never-started operations and first operating entry are not assigned without supporting evidence.

## Every case

`Unresolved` means the legal event is verified but first operations and the notification's economic meaning are not established. All rows remain ineligible for a first-entry backtest at this stage.

| Investor / Canadian business | Corporation | Notification | Incorporation | Days to month start | Audit disposition |
|---|---|---|---|---:|---|
| Backbase B.V. / Backbase Canada Inc. | [11075896](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11075896.json?lang=eng) | 2019-01 | 2018-11-01 | 61 | Unresolved |
| TVM Life Science Ventures VIII SCSp / Ocellaris Pharma Inc. | [11223836](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11223836.json?lang=eng) | 2019-03 | 2019-01-29 | 31 | Unresolved |
| TVM Life Science Ventures VIII SCSp / Acanthas Pharma Inc. | [11228170](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11228170.json?lang=eng) | 2019-04 | 2019-01-31 | 60 | Unresolved |
| Futy Ntango Ngongo Filipe Mingas / MIM Technology Group Inc. | [11400916](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11400916.json?lang=eng) | 2019-05 | 2019-05-09 | -8 | Unresolved |
| Relieve Consulting Services Canada Inc. | [11351362](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11351362.json?lang=eng) | 2019-07 | 2019-04-10 | 82 | Unresolved |
| Antea Canada Inc. | [11309552](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11309552.json?lang=eng) | 2019-08 | 2019-03-20 | 134 | Unresolved |
| LINET spol. s.r.o. / Linet Canada Inc. | [11263161](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11263161.json?lang=eng) | 2019-10 | 2019-02-21 | 222 | Founding corroborated; operations unresolved |
| FRAMEWORK COMPUTER CONSULTANTS LTD / DIGITARY CANADA INC. | [12015056](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12015056.json?lang=eng) | 2020-06 | 2020-04-21 | 41 | Unresolved |
| Dynamic Breeders United Inc. | [11577662](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11577662.json?lang=eng) | 2020-07 | 2019-08-19 | 317 | Unresolved |
| Max Neusser / HANECS Canada Inc. | [12689481](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12689481.json?lang=eng) | 2021-02 | 2021-01-28 | 4 | Unresolved |
| conTeyor International NV / conTeyor Canada Ltd. | [12527430](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12527430.json?lang=eng) | 2021-03 | 2020-11-27 | 94 | Unresolved |
| Trillium Supply Chain Inc. | [11681460](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/11681460.json?lang=eng) | 2021-04 | 2019-10-15 | 534 | Unresolved |
| Power by Britishvolt Limited / Britishvolt Canada Inc. | [12720914](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12720914.json?lang=eng) | 2021-06 | 2021-02-08 | 113 | Unresolved |
| Pegasi Oy / Pegasi IAM Canada Inc. | [13072681](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/13072681.json?lang=eng) | 2021-07 | 2021-06-03 | 28 | Unresolved |
| Aiut sp. z.o.o. / Aiut Inc. | [12934345](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12934345.json?lang=eng) | 2021-08 | 2021-04-18 | 105 | Unresolved |
| Bayer CropScience Inc. / 2022 Environmental Science CA Inc. | [13679624](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/13679624.json?lang=eng) | 2022-04 | 2022-01-13 | 78 | Unresolved |
| SD2 Engineering Services S.T.P. A R.L / SD2 Consulting Services Inc. | [12773449](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/12773449.json?lang=eng) | 2022-04 | 2021-02-25 | 400 | Unresolved |
| TOPdesk Canada Inc. | [9450122](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/9450122.json?lang=eng) | 2022-07 | 2015-09-23 | 2473 | Prior presence supported by City primary evidence |
| Roberto Sancristobal Llobell / Sanllo Canada Inc | [14292910](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/14292910.json?lang=eng) | 2022-10 | 2022-08-16 | 46 | Unresolved |
| Anastasios Lianos / Knitly Inc. | [14719808](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/14719808.json?lang=eng) | 2023-02 | 2023-01-30 | 2 | Unresolved |
| Sioo Wood Protection Industry AB / Sioo Wood Protection Industry Canada Inc. | [14274431](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/14274431.json?lang=eng) | 2023-07 | 2022-08-09 | 326 | Unresolved |
| Quista Technology Pte. Ltd. / Reebelo Canada, Inc. | [15053404](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/15053404.json?lang=eng) | 2023-08 | 2023-05-24 | 69 | Unresolved |
| Leadership Pipeline Institute Canada Inc. | [15266092](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/15266092.json?lang=eng) | 2023-09 | 2023-08-09 | 23 | Unresolved |
| Tiandingfeng Canada Nonwovens Co., Ltd. | [14895142](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/14895142.json?lang=eng) | 2023-10 | 2023-03-30 | 185 | Unresolved |
| K-Rouge Holding Inc. | [15924669](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/15924669.json?lang=eng) | 2024-04 | 2024-04-05 | -4 | Unresolved |
| Vaxxinova International B.V. / Vaxxinova Canada, Inc. | [16220801](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/16220801.json?lang=eng) | 2025-05 | 2024-07-18 | 287 | Unresolved |
| Bolton BG Canada Inc. | [9996672](https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations/9996672.json?lang=eng) | 2025-10 | 2016-11-24 | 3233 | Prior presence supported |

## Identity evidence gate

The previous gate accepted any primary evidence on a queue item, including evidence about another subject. Confirmation now requires explicitly cited evidence matching the resolved subject type, full normalized legal name, jurisdiction and any declared identifier. Normalization removes punctuation and spacing, not words or legal suffixes. A changed name requires an explicit primary-source `SAME_LEGAL_ENTITY_AS` assertion. Parent tasks require an explicit allowed parent relationship to the exact queued legal entity. Contradictory cited identity attributes fail confirmation.

New decisions store a pointer to the active decision, so replaying an earlier decision uses its own citations. Existing databases migrate additively. Summary reads reassess existing confirmations without rewriting their decision history. Existing evidence must be cited explicitly by its evidence ID; incidental evidence elsewhere on the queue cannot satisfy a new decision.

Of the 12 committed historical approvals, **11 now satisfy this structured gate and 1 requires evidence review**:

| Historical approval | Missing support | Action |
|---|---|---|
| SD2 Engineering Services società tra professionisti a R.L. | Resolved: the Turin government filing uses both the full legal form and `SD2 engineering services s.t.p. a r.l.` for the same firm, address and VAT | `SAME_LEGAL_ENTITY_AS` recorded; identity support only, not event-time eligibility |
| Bolton Group S.r.l. | Exact legal parent-to-`Bolton BG Canada Inc.` relation; existing report assertions use shortened group/vehicle names | Obtain an explicit legal-entity relationship or supported alias chain |

All 12 original approvals and four review files are preserved. The remaining Bolton flag does not assert that the original identity is false. Fourteen baseline queue tasks remain open; Backbase is a separate automated identity confirmation and is not counted among these 12.

`identity_evidence_supported_curated_records` reports supported legal identities. `confirmations_requiring_evidence_review` exposes the legacy gaps. The compatibility field `modeling_ready_curated_records` is now zero, with `modeling_readiness_status = NOT_EVALUATED`; identity support alone does not confer training eligibility. Publisher authenticity and the truth of submitted structured assertions still require review; this code does not authenticate a website merely because an evidence type says "official".

Batch 03 now carries explicit SD2 alias evidence and passes the current identity gate. Batch 04 still fails the parent-link gate for Bolton; do not replay that confirmation as a new supported decision until explicit parent evidence is added. Use the pinned disposition audit to assess historical decisions.

## Reproduction and validation

```sh
python -m unittest discover -s tests -v
python scripts/refresh_outcome_cases.py --output data/outcome-audit-refresh
```

The pinned refresh checks each outcome ID, notification classification/month, named investor, Canadian business name and federal event. Source movement or changed evidence fails visibly. This refresh verifies records and dates; it does not automatically reclassify manual operating-history judgments. The **Outcome audit acceptance** workflow runs it for relevant pull requests and retains raw pages, corporation responses and a complete JSON summary. Its optional manual `full_history` input additionally rebuilds the complete historical corpus and calls `scripts/export_outcome_audit.py`; the exporter includes every confirmed row and rejects missing rows or corrupted registry hashes.

Local validation: **77 tests passed**. Regression coverage includes wrong-subject evidence, conflicting identifiers/jurisdictions, alias and parent direction, explicit citations, cross-queue rejection, transaction rollback, earlier-decision replay, preserved legacy decisions, corrected legacy timing labels, all-27 export completeness, source-hash mismatch and changed/missing pinned-source evidence. Live acceptance results are linked from the pull request.

## Next work

1. Resolve the remaining Bolton legal parent-link gap, preserving all prior decisions.
2. Establish operational milestones for the remaining unresolved cases, starting with the Bayer environmental-science vehicle, the two TVM portfolio companies and inactive entities. TOPdesk is now confirmed as pre-existing Canadian presence at year precision; its exact first-operating date and 2022 notification purpose remain unresolved. Record first operations, evidence publication/availability and notification purpose separately, at the precision the sources support.
3. For cases with defensible outcome dates and historical identity chains, construct matched controls and enforce publication cutoffs. Missing evidence remains unresolved; it does not become a negative label.
4. Validate incremental predictive lift before assigning Expansion Likelihood weights. Keep Nova Scotia Fit and Evidence Confidence separate.
