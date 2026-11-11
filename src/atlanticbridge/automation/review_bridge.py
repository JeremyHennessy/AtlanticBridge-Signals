"""Validate an existing local collection, then retain its context in the durable store.

No original response is claimed: the retained bytes are a normalized local packet.
Pinned Halifax/NL validation remains owned by the existing packet builder.
"""
from __future__ import annotations
from .models import SourceContract, canonical, decode_batch
from ..analyst_review import build_review_packet


def _prepare_review_parts(collection, *, generated_at):
    packet = build_review_packet([collection], generated_at=generated_at)
    if len(packet["collections"]) != 1:
        raise ValueError("Exactly one validated local collection is required")
    envelope = packet["collections"][0]
    source = envelope["source"]
    evidence_class = envelope["evidence_class"]
    origin = "INVENTED_FIXTURE" if envelope.get("fixture_only") is True or "FIXTURE" in evidence_class else "LOCAL_REVIEW_PACKET"
    rows = []
    fields = set()
    for finding in packet["findings"]:
        facts = dict(finding["source_facts"])
        # Keep semantic/provenance boundaries in each durable version.
        facts.update({
            "_evidence_class": finding["evidence_class"],
            "_independent_verification": finding["independent_verification"],
            "_headline": finding["headline"],
            "_entity_label": finding["entity_label"],
            "_event_stage": finding["event_stage"],
            "_date_kind": finding["source_record_date_kind"],
            "_interpretation_limit": finding["interpretation_limit"],
            "_identity_limit": finding["identity_resolution_limit"],
            "_lead_promotion_allowed": False,
        })
        fields.update(facts)
        rows.append({"record_id": finding["source_record_id"], "facts": facts,
                     "source_url": finding["source_url"], "event_date": finding["event_date"],
                     "published_date": finding["published_date"], "source_observed_at": finding["retrieved_at"]})
    if not rows:
        raise ValueError("Deriving a first contract needs a nonempty reviewed sample")
    contract = SourceContract(source_id=source, title=source.replace("_", " "),
                              parser_version="analyst-review-v1/automation-bridge-v1",
                              allowed_fields=tuple(sorted(fields)), origin=origin,
                              license_name=envelope["source_license"], license_url=envelope["source_license_url"],
                              attribution=envelope["attribution"], coverage=envelope["coverage"])
    body = canonical({"format_version": 1, "source_id": source, "origin": origin,
                      "coverage": contract.coverage, "records": rows}).encode()
    return contract, body


def prepare_review_collection(collection, *, generated_at):
    contract, body = _prepare_review_parts(collection, generated_at=generated_at)
    return contract, decode_batch(body, contract)
