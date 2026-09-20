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

A `CONFIRMED` decision requires explicitly cited primary evidence matching the resolved subject type, normalized full name and legal jurisdiction. A declared identifier requires a matching evidence identifier. Conflicting cited jurisdictions or values of the declared identifier type reject the decision. A non-empty decision basis is required.

The cited evidence consists of the current item's `evidence` rows plus explicitly supplied `evidence_ids` already belonging to that queue item. Evidence elsewhere in the queue does not silently support a new decision. Each decision retains the actual cited IDs.

For a named-investor identity, the resolved name must match the queued investor after punctuation/spacing normalization, or matching primary evidence must explicitly assert `SAME_LEGAL_ENTITY_AS` to the queued spelling. Legal suffixes, acronyms and company words are not discarded. For a parent task, matching primary evidence must explicitly link the resolved parent to the queued investor through `DIRECT_PARENT_OF`, `ULTIMATE_PARENT_OF`, `GROUP_HOLDING_PARENT_OF`, `DIRECT_ACCOUNTING_PARENT_OF` or `ULTIMATE_ACCOUNTING_PARENT_OF`. Brand membership or an unspecified group relationship is insufficient.

These checks validate the consistency of reviewed assertions; a reviewer must still authenticate the publisher and read the source. A supplied source-type label is not automatic proof that a URL is authoritative.

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
      "subject_type": "LEGAL_ENTITY",
      "subject_name": "Example GmbH",
      "jurisdiction": "DE",
      "identifier_type": "REGISTER_NUMBER",
      "identifier_value": "HRB123",
      "relationship_type": "",
      "related_subject_type": "UNKNOWN",
      "related_subject_name": "",
      "evidence_note": "Exact legal name and registered identifier."
    }
  ],
  "decision": {
    "state": "CONFIRMED",
    "resolved_subject_type": "LEGAL_ENTITY",
    "resolved_subject_name": "Example GmbH",
    "resolved_jurisdiction": "DE",
    "resolved_identifier_type": "REGISTER_NUMBER",
    "resolved_identifier_value": "HRB123",
    "basis": "Exact official registry legal-name record."
  }
}
```

A file can contain either one object or a list of review objects.

## Modeling boundary

Curated identity confirmation is an identity/evidence gate only. It does not create an Expansion Likelihood score. Confirmed natural persons remain valid reviewed identities but do not count as modeling-ready company identities.

Summary fields now distinguish:

- `confirmed_reviews` / `confirmed_legal_entities`: historical reviewed decisions, preserved;
- `identity_evidence_supported_curated_records`: legal-entity confirmations passing the current evidence gate;
- `confirmations_requiring_evidence_review`: earlier decisions that require more explicit evidence;
- per-row `confirmation_gate_status` and `confirmation_gate_reason`;
- `modeling_readiness_status = NOT_EVALUATED` and deprecated compatibility field `modeling_ready_curated_records = 0` until separate outcome, event-time and scope eligibility are established.

The previous summary equated a confirmed legal identity with model readiness. That interpretation is withdrawn. Historical validation documents retain their original counts as records of the old gate, not current model eligibility. Existing decisions are not rewritten by this reassessment.

Matched-control and event-time modeling should use only identities that are either:

1. confirmed by the automated strict resolver; or
2. explicitly confirmed through this curated primary-evidence review layer.
