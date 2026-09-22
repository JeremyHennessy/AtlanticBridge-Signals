# Company-source proof execution record — 22 September 2026

## First test and evidence-driven corrections

PR #101 starts from main c522a167684308188ae4a0a64d6dc9035ef3ecda and adds isolated source/validation infrastructure. Parallel PR #100 merged to ded11a79b28fc05fb6f9fc83a8e6833b617a62e1; no files owned by that UI change are modified here.

Initial source-proof run 35779234080 on head d652d03351f10e1e5bd8dd67a7589e3099699e70 passed all 48 new regression tests but failed its live gate. Five of six source paths returned 110 normalized observations; the careers path stopped during the Ashby API host's robots.txt request, before a job-data request. Raw artifact 10717631034 retained nine responses whose SHA-256 hashes were independently verified after download.

The retained official Mistral careers HTML links to https://jobs.ashbyhq.com/mistral.ai. The failure therefore was not a guessed board identity. RFC 9309 section 2.3.1.3 permits requests when robots.txt is unavailable (4xx). The repair allows that case narrowly for the documented public Ashby postings path; an actual content 401/403, returned disallow rule, 429, server error or unknown protected path still blocks collection. Error response bytes and failed URLs are now retained. References: https://www.rfc-editor.org/rfc/rfc9309.html and https://developers.ashbyhq.com/docs/public-job-posting-api .

Raw inspection also identified Montreal International's /en/news/subject/ category links being counted as articles. The parser now excludes those taxonomy links. Its contract version advances to 2; an old experimental ledger is not silently migrated. Regression tests preserve that failure case.

Input review identified an incomplete verified-opening label that could otherwise count without an opening date/evidence, string-valued confirmation flags, and non-finite review durations. These now fail closed with focused regression tests. They do not change any accepted historical case.

## Six-path proof accepted as a source-feasibility result

Head: e1879b2ffadcbbbf56fcf2bb216eb5f43a999752.
Tested merge commit: c8c199a7d3313fd50ffd45f1c5dd358f542d3fa5.
Source workflow: https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35779895762 .
CI workflow: https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35779895772 .
Workflow syntax: https://github.com/JeremyHennessy/AtlanticBridge-Signals/actions/runs/35779895973 .
All three completed successfully.

Artifact 10717388795 contains the exact tested source tree, ledger, raw responses and report. ZIP SHA-256: 32ecd7b68253ad29b5b24ada1db613062e6d6972fbd3dc279d22b8225a5373bf. Both the archive hash and all 11 retained raw-response hashes were independently verified after native artifact download. The exact exported source passed the complete local Python suite: 303 tests in 0.904 seconds.

Observed source counts (source records, NOT distinct verified leads):

| Path | Retained records |
|---|---:|
| Mistral official careers, Ashby binding | 198 |
| Mistral official news index | 90 |
| Montreal International news index | 12 |
| Mistral Montreal announcement detail | 1 |
| G+D Montreal announcement detail | 1 |
| Adyen Payments Canada membership detail | 1 |
| Total | 303 |

All six source paths succeeded. First-baseline change events: 0. Exact replay events: 0. This is the intended baseline behavior, not an empty source result.

There are seven Canada-location Mistral job records, including Montreal locations and a multi-location record mentioning Toronto. All seven are conservatively held for scope review because their descriptions contain defense wording in the company-introduction text; one also contains a cloud-defense responsibility. The summary's `canada_candidates` count is the number after scope holds, not all geographic matches. Zero unheld career records must not be interpreted as no Canadian hiring. The full records and hold flags are retained. No hold is overridden merely to produce leads, and no job is called a first office or newly published entry signal.

## Bounded source expansion

The manifest is extended from six to eight requested paths with DeepL and Pleo official careers pages. Each publicly links its own Ashby board; the collector must rediscover and retain that binding during the live run. Those are additional source-local company candidates, not new accepted legal identities or control companies. The extended proof still requires every requested source to succeed. Its result must be recorded separately; the six-path acceptance above does not imply an eight-path pass.

## What is not proven

Greenhouse and RSS/Atom are implemented and fixture-tested, not live-proven by the six-path run. The three documentary calibration cases are not independent validation, confirmed first-operation dates or a completed 100-outcome cohort. No pilot-user judgments, willingness-to-pay results, historical predictive lift or expansion probability are manufactured. Public alert publication and historical score gates remain closed. The source work does not yet publish new company-source records to the production Signals inbox or establish scheduled durable monitoring.
