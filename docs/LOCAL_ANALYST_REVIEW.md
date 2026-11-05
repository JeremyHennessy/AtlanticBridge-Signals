# Local evidence-context review

This is a local analyst worksheet for already-collected evidence context from the BODACC, federal Grants and Contributions, and Nova Scotia awarded-tenders collectors. It is not connected to the public app, lead feed, scoring model, or production collection schedule.

## Use

Install the package in a local Python environment, then build a packet from collector JSON envelopes:

```powershell
python -m pip install -e .
python scripts/build_analyst_review_packet.py `
  --input .\path\bodacc.json `
  --input .\path\federal-grants.json `
  --input .\path\nova-scotia-tenders.json `
  --output .\local-review-packet.json
```

Open `local_analyst_review/index.html` in a browser and select the packet. Or use “Load synthetic demonstration” to inspect the interface; its company and tender are invented and are not observations.

The packet builder reads local JSON and writes a local packet. It does not collect source data. Collectors must be run separately and manually under their existing bounds and source conditions. The browser UI does not automatically fetch, upload, or persist packet contents. Opening an official source or licence link performs normal browser navigation. Record a disposition, local follow-up owner/date, counter-evidence, and next-step note per finding. Exported notes remain keyed to stable finding IDs; the export is not a lead and does not update any app or database.

## Evidence handling

- Every finding is locked to context only. No score, eligibility, worklist, or lead-promotion path is present.
- “Live query” means the collector envelope reports an HTTP request. The envelope is not signed and that claim is not cryptographically authenticated. Independently open and validate the record, identity and dates.
- Fixture/replay and legacy-origin states remain visibly separate from a reported live query.
- Findings carry retrieval time where available, source dates, source attribution, licence, event stage, and interpretation limit. The collection summary carries a response SHA-256 when the envelope supplies a well-formed digest.
- Do not read a missing exact-name match as proof of absence. Check for truncation, identity variants, source cadence and coverage.
- A grant agreement is not necessarily a disbursement. An awarded tender is prior procurement activity. A French BODACC notice does not establish Canadian activity or expansion intent.
- Apply each source's licence and privacy terms. Open Government Licences exclude personal information; do not reuse personal information on the assumption that it is licensed.

This workflow is a local pilot aid only. It has not received independent browser acceptance or independent review of imported live findings. It does not change public output or activate any source in production.
