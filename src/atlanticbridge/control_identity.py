from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Callable

from .foreign_identity import classify_candidates
from .sources.gleif import GLEIFCandidate, GLEIFSearchResult, search_legal_name


ALLOWED_INPUT_STATUS = "UNREVIEWED"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _is_canadian_entity(candidate: GLEIFCandidate) -> bool:
    values = {
        (candidate.jurisdiction or "").upper(),
        (candidate.legal_address_country or "").upper(),
        (candidate.headquarters_country or "").upper(),
    }
    return any(value == "CA" or value.startswith("CA-") for value in values if value)


def _candidate_summary(candidate: GLEIFCandidate) -> dict[str, object]:
    return {
        "rank": candidate.rank,
        "lei": candidate.lei,
        "legal_name": candidate.legal_name,
        "jurisdiction": candidate.jurisdiction,
        "entity_status": candidate.entity_status,
        "entity_category": candidate.entity_category,
        "registered_as": candidate.registered_as,
        "registration_authority_id": candidate.registration_authority_id,
        "legal_address_city": candidate.legal_address_city,
        "legal_address_country": candidate.legal_address_country,
        "headquarters_city": candidate.headquarters_city,
        "headquarters_country": candidate.headquarters_country,
        "exact_normalized_name": candidate.exact_normalized_name,
        "name_similarity": round(candidate.name_similarity, 6),
    }


def qualify_control_identity(
    row: dict[str, object],
    result: GLEIFSearchResult,
) -> dict[str, object]:
    if row.get("identity_qualification_status") != ALLOWED_INPUT_STATUS:
        raise ValueError("control identity triage requires UNREVIEWED input rows")
    if row.get("backtest_control_eligible"):
        raise ValueError("input control identity rows must not already be eligible")

    investor_name = str(row.get("investor_name") or "").strip()
    investor_locality = str(row.get("investor_locality") or "").strip()
    if not investor_name:
        raise ValueError("control identity row missing investor_name")

    raw_status, selected, exact_count, locality_match_count = classify_candidates(
        result.candidates,
        investor_locality,
    )

    triage_status = raw_status
    eligible = False
    exclusion_reason = ""

    if raw_status == "CONFIRMED_NAMED_ENTITY" and selected is not None:
        if _is_canadian_entity(selected):
            triage_status = "EXCLUDED_CANADIAN_LEGAL_ENTITY"
            exclusion_reason = (
                "Unique exact-name/locality GLEIF match resolves to a Canadian "
                "legal/headquarters jurisdiction."
            )
        else:
            triage_status = "GLEIF_CONFIRMED_FOREIGN_LEGAL_ENTITY"
            eligible = True
    elif raw_status == "REVIEW_READY_EXACT_NAME":
        triage_status = "REVIEW_REQUIRED_EXACT_NAME"
        exclusion_reason = (
            "Unique exact legal-name candidate lacks a source-locality match; "
            "primary review required before control use."
        )
    elif raw_status == "AMBIGUOUS_EXACT":
        exclusion_reason = "Multiple exact-name candidates or locality matches require review."
    elif raw_status == "NO_RESULTS":
        triage_status = "NO_GLEIF_RESULTS"
        exclusion_reason = "GLEIF returned no legal-entity candidate."
    elif raw_status == "UNRESOLVED":
        triage_status = "UNRESOLVED_GLEIF"
        exclusion_reason = "GLEIF candidates do not resolve the exact named investor."
    else:
        exclusion_reason = "GLEIF evidence is insufficient for automatic control qualification."

    exact_candidates = [
        _candidate_summary(candidate)
        for candidate in result.candidates
        if candidate.exact_normalized_name
    ]

    selected_summary = _candidate_summary(selected) if selected is not None else None
    evidence_url = (
        f"https://api.gleif.org/api/v1/lei-records/{selected.lei}"
        if selected is not None and selected.lei
        else ""
    )

    return {
        **row,
        "identity_qualification_status": triage_status,
        "backtest_control_eligible": eligible,
        "negative_label_eligible": False,
        "exclusion_reason": exclusion_reason,
        "gleif_query_url": result.query_url,
        "gleif_golden_copy_publish_date": result.golden_copy_publish_date,
        "gleif_total_results": result.total_results,
        "gleif_exact_name_candidate_count": exact_count,
        "gleif_locality_match_count": locality_match_count,
        "gleif_selected_candidate": selected_summary,
        "gleif_selected_evidence_url": evidence_url,
        "gleif_exact_candidates": exact_candidates,
    }


def build_control_identity_triage(
    review_queue: dict[str, object],
    *,
    search_fn: Callable[..., GLEIFSearchResult] = search_legal_name,
    page_size: int = 10,
) -> dict[str, object]:
    records = review_queue.get("records")
    if not isinstance(records, list):
        raise ValueError("control identity review queue requires records")
    if int(review_queue.get("record_count") or -1) != len(records):
        raise ValueError("control identity review queue record_count mismatch")

    triaged = []
    query_errors = []
    for source_row in records:
        if not isinstance(source_row, dict):
            raise ValueError("control identity review rows must be objects")
        row = dict(source_row)
        try:
            result = search_fn(
                str(row.get("investor_name") or ""),
                page_size=page_size,
            )
            triaged.append(qualify_control_identity(row, result))
        except Exception as exc:
            failed = {
                **row,
                "identity_qualification_status": "QUERY_ERROR",
                "backtest_control_eligible": False,
                "negative_label_eligible": False,
                "exclusion_reason": (
                    f"GLEIF query failed: {type(exc).__name__}: {str(exc)}"
                ),
                "gleif_query_url": "",
                "gleif_golden_copy_publish_date": "",
                "gleif_total_results": 0,
                "gleif_exact_name_candidate_count": 0,
                "gleif_locality_match_count": 0,
                "gleif_selected_candidate": None,
                "gleif_selected_evidence_url": "",
                "gleif_exact_candidates": [],
            }
            triaged.append(failed)
            query_errors.append(str(row.get("control_entity_key") or ""))

    triaged.sort(key=lambda row: str(row.get("control_entity_key") or ""))

    counts: dict[str, int] = {}
    golden_copies = set()
    for row in triaged:
        status = str(row["identity_qualification_status"])
        counts[status] = counts.get(status, 0) + 1
        golden = str(row.get("gleif_golden_copy_publish_date") or "")
        if golden:
            golden_copies.add(golden)

    payload = {
        "schema_version": 1,
        "source_queue_record_count": len(records),
        "triage_method": (
            "GLEIF exact normalized legal-name search plus unique source-locality "
            "match. Confirmed Canadian legal entities are excluded; all other "
            "unresolved/ambiguous rows fail closed."
        ),
        "backtest_control_eligibility_rule": (
            "Only GLEIF_CONFIRMED_FOREIGN_LEGAL_ENTITY rows are automatically "
            "eligible; no triage status creates a negative outcome label."
        ),
        "gleif_golden_copy_publish_dates": sorted(golden_copies),
        "query_error_entity_keys": sorted(query_errors),
        "status_counts": [
            {"identity_qualification_status": status, "records": count}
            for status, count in sorted(counts.items())
        ],
        "backtest_control_eligible_records": sum(
            bool(row.get("backtest_control_eligible")) for row in triaged
        ),
        "negative_labels_created": 0,
        "records": triaged,
    }
    validate_control_identity_triage(payload)
    return payload


def validate_control_identity_triage(payload: dict[str, object]) -> None:
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("control identity triage requires records")
    if int(payload.get("source_queue_record_count") or -1) != len(records):
        raise ValueError("control identity triage record count mismatch")

    seen = set()
    eligible = 0
    for row in records:
        if not isinstance(row, dict):
            raise ValueError("control identity triage rows must be objects")
        key = str(row.get("control_entity_key") or "")
        if not key or key in seen:
            raise ValueError("control identity triage entity keys must be unique")
        seen.add(key)
        if row.get("negative_label_eligible"):
            raise ValueError("control identity triage cannot create negative labels")

        status = str(row.get("identity_qualification_status") or "")
        is_eligible = bool(row.get("backtest_control_eligible"))
        if is_eligible:
            eligible += 1
            if status != "GLEIF_CONFIRMED_FOREIGN_LEGAL_ENTITY":
                raise ValueError(
                    "backtest eligibility requires confirmed foreign GLEIF identity"
                )
            selected = row.get("gleif_selected_candidate")
            if not isinstance(selected, dict) or not selected.get("lei"):
                raise ValueError("eligible control requires selected GLEIF evidence")
            values = {
                str(selected.get("jurisdiction") or "").upper(),
                str(selected.get("legal_address_country") or "").upper(),
                str(selected.get("headquarters_country") or "").upper(),
            }
            if any(v == "CA" or v.startswith("CA-") for v in values if v):
                raise ValueError("Canadian legal entities cannot be eligible controls")
        elif status == "GLEIF_CONFIRMED_FOREIGN_LEGAL_ENTITY":
            raise ValueError("confirmed foreign controls must be marked eligible")

    if eligible != int(payload.get("backtest_control_eligible_records") or 0):
        raise ValueError("backtest eligible count mismatch")
    if payload.get("negative_labels_created") != 0:
        raise ValueError("control identity triage must create zero negative labels")


def control_identity_manifest(payload: dict[str, object]) -> dict[str, object]:
    validate_control_identity_triage(payload)
    return {
        "schema_version": 1,
        "triage_canonical_sha256": hashlib.sha256(
            _canonical_json(payload).encode("utf-8")
        ).hexdigest(),
        "source_queue_record_count": payload["source_queue_record_count"],
        "status_counts": payload["status_counts"],
        "backtest_control_eligible_records": payload[
            "backtest_control_eligible_records"
        ],
        "negative_labels_created": payload["negative_labels_created"],
        "gleif_golden_copy_publish_dates": payload[
            "gleif_golden_copy_publish_dates"
        ],
        "query_error_entity_keys": payload["query_error_entity_keys"],
    }
