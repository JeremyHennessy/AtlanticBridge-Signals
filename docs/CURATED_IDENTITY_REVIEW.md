# Curated Primary-Evidence Identity Review

## Purpose

Data Proof 012 established that GLEIF alone cannot resolve the named-investor/parent layer reliably enough for modeling.

The curated review layer converts unresolved identity work into a persistent, auditable queue rather than another fuzzy resolver.

## Queue tasks

The current production foreign-identity states map to review tasks as follows:

| Source state | Review task |
|---|---|
| REVIEW_READY_EXACT_NAME | NAMED_INVESTOR_IDENTITY |
| AMBIGUOUS_EXACT | NAMED_INVESTOR_IDENTITY |
| UNRESOLVED | NAMED_INVESTOR_IDENTITY |
| NO_RESULTS | NAMED_INVESTOR_IDENTITY |
| QUERY_ERROR | NAMED_INVESTOR_IDENTITY |
| CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED | NAMED_INVESTOR_PARENT |
| CANADIAN_VEHICLE_PARENT_UNRESOLVED | CANADIAN_VEHICLE_PARENT |

Confirmed foreign named entities are not re-queued.

Queue IDs are based on `outcome_record_id + task_type`, so evidence and decisions remain stable when a foreign-identity run is refreshed.

## Evidence contract

Permitted evidence types:

- `OFFICIAL_COMPANY_SITE`
- `OFFICIAL_REGISTRY`
- `OFFICIAL_GOVERNMENT_FILING`
- `OFFICIAL_STOCK_EXCHANGE_FILING`
- `OTHER_REFERENCE`

The first four are treated as primary sources.

AtlanticBridge stores structured citations/identifiers and a concise review note. It does not copy full webpages into the database.

## Decision contract

Review states:

- `OPEN`
- `CONFIRMED`
- `BLOCKED`
- `INSUFFICIENT_EVIDENCE`
- `REJECTED`
- `RESOLVED_UPSTREAM`

A `CONFIRMED` decision is rejected unless the queue has at least one primary-source evidence record and the decision contains a legal name and jurisdiction.

Rebuilding the queue never overwrites explicit reviewed decisions. A task that disappears from a newer foreign-identity run is marked `RESOLVED_UPSTREAM` rather than deleted.

## Review JSON shape

```json
{
  "queue_id": "<stable queue id>",
  "evidence": [
    {
      "evidence_type": "OFFICIAL_REGISTRY",
      "source_url": "https://...",
      "source_title": "Official company record",
      "source_publisher": "Registry authority",
      "legal_name": "Example GmbH",
      "jurisdiction": "DE",
      "identifier_type": "REGISTER_NUMBER",
      "identifier_value": "HRB123",
      "relationship_type": "",
      "related_legal_name": "",
      "evidence_note": "Exact legal name and registered identifier."
    }
  ],
  "decision": {
    "state": "CONFIRMED",
    "resolved_legal_name": "Example GmbH",
    "resolved_jurisdiction": "DE",
    "resolved_identifier_type": "REGISTER_NUMBER",
    "resolved_identifier_value": "HRB123",
    "basis": "Exact official registry legal-name record."
  }
}
```

A file can contain either one object or a list of review objects.

## Modeling boundary

Curated identity confirmation is an identity/evidence gate only. It does not create an Expansion Likelihood score.

Matched-control and event-time modeling should use only identities that are either:

1. confirmed by the automated strict resolver; or
2. explicitly confirmed through this curated primary-evidence review layer.
