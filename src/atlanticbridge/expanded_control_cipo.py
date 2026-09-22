from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path

from .sources.cipo_journal import normalize_name


SIGNAL_FAMILY = "CIPO_CANADIAN_TRADEMARK"
COVERAGE_START_DATE = "2000-01-05"
COVERAGE_END_EXCLUSIVE = "2023-06-01"


def load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def build_reviewed_entity_contract(
    batch_payloads: list[dict[str, object]],
) -> dict[str, object]:
    rows: dict[str, dict[str, object]] = {}

    for batch in batch_payloads:
        records = batch.get("records")
        if not isinstance(records, list):
            raise ValueError("expanded control review batch requires records")

        for row in records:
            if not isinstance(row, dict):
                raise ValueError("expanded control review row must be object")
            if row.get("review_decision") != (
                "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY"
            ):
                continue
            if row.get("identity_confidence") != "HIGH":
                continue
            if row.get("accepted_backtest_control_eligible") is not False:
                raise ValueError(
                    "expanded control CIPO research must not consume accepted "
                    "backtest-control eligibility"
                )

            entity_id = str(row["control_entity_key"])
            if entity_id in rows:
                raise ValueError(f"duplicate reviewed control entity: {entity_id}")

            alias_candidates = [
                str(row.get("investor_name") or "").strip(),
                str(row.get("foreign_legal_name") or "").strip(),
            ]
            alias_by_normalized: dict[str, str] = {}
            for alias in alias_candidates:
                normalized = normalize_name(alias)
                if not normalized:
                    continue
                alias_by_normalized.setdefault(normalized, alias)
            if not alias_by_normalized:
                raise ValueError(f"reviewed entity lacks usable aliases: {entity_id}")

            rows[entity_id] = {
                "entity_id": entity_id,
                "display_name": str(row.get("investor_name") or ""),
                "foreign_legal_name": str(
                    row.get("foreign_legal_name") or ""
                ),
                "exact_aliases": [
                    alias_by_normalized[key]
                    for key in sorted(alias_by_normalized)
                ],
                "identity_confidence": "HIGH",
                "foreign_signal_identity_eligible": True,
                "source_review_decision":
                    "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY",
            }

    entities = sorted(
        rows.values(),
        key=lambda row: str(row["entity_id"]),
    )
    aliases = []
    for entity in entities:
        for alias in entity["exact_aliases"]:
            aliases.append(
                {
                    "entity_id": entity["entity_id"],
                    "alias": alias,
                    "normalized_alias": normalize_name(str(alias)),
                }
            )

    return {
        "schema_version": 1,
        "design": "EXPANDED_CONTROL_CIPO_REVIEWED_ALIAS_CONTRACT",
        "entity_count": len(entities),
        "alias_count": len(aliases),
        "entities": entities,
        "aliases": aliases,
    }


def scanner_entities_payload(
    contract: dict[str, object],
) -> dict[str, object]:
    entities = contract.get("entities")
    if not isinstance(entities, list):
        raise ValueError("reviewed alias contract requires entities")
    return {
        "schema_version": 1,
        "entities": [
            {
                "entity_id": row["entity_id"],
                "exact_aliases": row["exact_aliases"],
                "foreign_signal_identity_eligible": True,
            }
            for row in entities
        ],
    }


def aggregate_expanded_control_cipo_shards(
    *,
    shard_payloads: list[dict[str, object]],
    accepted_inventory: dict[str, object],
    reviewed_contract: dict[str, object],
) -> dict[str, object]:
    if not shard_payloads:
        raise ValueError("expanded control CIPO scan requires shards")

    expected_issue_count = int(accepted_inventory["issue_count"])
    expected_inventory_hash = str(
        accepted_inventory["canonical_issue_sha256"]
    )

    structural_errors: list[str] = []
    issue_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    shard_summaries: list[dict[str, object]] = []
    alias_contracts: list[dict[str, object]] = []

    for payload in shard_payloads:
        if payload.get("design") != "CIPO_JOURNAL_FULL_SCAN_SHARD":
            structural_errors.append("unexpected shard design")
            continue

        alias_contract = payload.get("alias_contract")
        if not isinstance(alias_contract, dict):
            structural_errors.append("shard missing alias_contract")
            continue

        alias_contracts.append(alias_contract)
        issue_rows.extend(payload.get("issue_proof") or [])
        failures.extend(payload.get("failures") or [])
        unresolved.extend(
            payload.get("unresolved_alias_occurrences") or []
        )
        records.extend(payload.get("records") or [])
        shard_summaries.append(
            {
                "shard": payload.get("shard"),
                "summary": payload.get("summary"),
                "inventory": payload.get("inventory"),
            }
        )

    if not alias_contracts:
        structural_errors.append("no valid shard alias contracts")
        actual_alias_contract = {
            "entity_count": 0,
            "alias_count": 0,
            "aliases": [],
        }
    else:
        actual_alias_contract = alias_contracts[0]
        canonical = canonical_json(actual_alias_contract)
        for index, contract in enumerate(alias_contracts[1:], start=2):
            if canonical_json(contract) != canonical:
                structural_errors.append(
                    f"alias contract differs in shard index {index}"
                )

    expected_aliases = {
        (
            str(row["entity_id"]),
            str(row["normalized_alias"]),
        )
        for row in reviewed_contract.get("aliases") or []
        if isinstance(row, dict)
    }
    actual_aliases = {
        (
            str(row["entity_id"]),
            normalize_name(str(row["alias"])),
        )
        for row in actual_alias_contract.get("aliases") or []
        if isinstance(row, dict)
    }
    if actual_aliases != expected_aliases:
        structural_errors.append(
            "scanner alias contract differs from reviewed aliases"
        )

    if int(actual_alias_contract.get("entity_count") or 0) != int(
        reviewed_contract.get("entity_count") or 0
    ):
        structural_errors.append("scanner entity count differs from review")
    if int(actual_alias_contract.get("alias_count") or 0) != int(
        reviewed_contract.get("alias_count") or 0
    ):
        structural_errors.append("scanner alias count differs from review")

    issue_by_date: dict[str, dict[str, object]] = {}
    for row in issue_rows:
        if not isinstance(row, dict):
            structural_errors.append("issue proof row is not an object")
            continue
        published = str(row.get("publication_date") or "")
        if not published:
            structural_errors.append("issue proof row missing publication date")
            continue
        if published in issue_by_date:
            structural_errors.append(
                f"duplicate issue publication date: {published}"
            )
            continue
        issue_by_date[published] = row

    issues = sorted(
        issue_by_date.values(),
        key=lambda row: str(row["publication_date"]),
    )
    inventory_material = "\n".join(
        f"{row['publication_date']}|{row['pdf_url']}"
        for row in issues
    ) + ("\n" if issues else "")
    inventory_hash = hashlib.sha256(
        inventory_material.encode("utf-8")
    ).hexdigest()

    if len(issues) != expected_issue_count:
        structural_errors.append(
            f"issue count mismatch: {len(issues)} != {expected_issue_count}"
        )
    if inventory_hash != expected_inventory_hash:
        structural_errors.append(
            "inventory hash mismatch: "
            f"{inventory_hash} != {expected_inventory_hash}"
        )

    incomplete = [
        row
        for row in issues
        if row.get("complete_for_exact_alias_absence") is not True
    ]
    if incomplete:
        structural_errors.append(
            f"{len(incomplete)} issue rows are incomplete"
        )

    dedup_records: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in records:
        if not isinstance(row, dict):
            structural_errors.append("evidence record is not an object")
            continue
        key = (
            str(row.get("entity_id") or ""),
            str(row.get("application_number") or ""),
            str(row.get("publicly_available_date") or ""),
        )
        if not all(key):
            structural_errors.append(
                f"incomplete evidence record key: {key}"
            )
            continue
        existing = dedup_records.get(key)
        if existing is None:
            dedup_records[key] = row

    records = sorted(
        dedup_records.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["application_number"]),
        ),
    )

    gate_passed = (
        not structural_errors
        and not failures
        and not unresolved
        and len(issues) == expected_issue_count
        and inventory_hash == expected_inventory_hash
        and all(
            row.get("complete_for_exact_alias_absence") is True
            for row in issues
        )
    )

    records_by_entity: dict[str, list[dict[str, object]]] = {}
    for row in records:
        records_by_entity.setdefault(
            str(row["entity_id"]),
            [],
        ).append(row)

    coverage = []
    entities = reviewed_contract.get("entities")
    if not isinstance(entities, list):
        raise ValueError("reviewed alias contract requires entities")
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("reviewed entity must be object")
        entity_id = str(entity["entity_id"])
        matched = records_by_entity.get(entity_id, [])
        coverage.append(
            {
                "entity_id": entity_id,
                "display_name": entity["display_name"],
                "foreign_legal_name": entity["foreign_legal_name"],
                "identity_confidence": "HIGH",
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_OFFICIAL_JOURNAL_EXACT_REVIEWED_ALIAS_"
                    "2000_TO_2023_05_31"
                    if gate_passed
                    else "JOURNAL_SCAN_INCOMPLETE"
                ),
                "absence_coverage_proven": gate_passed,
                "coverage_start_date": COVERAGE_START_DATE,
                "coverage_end_exclusive": COVERAGE_END_EXCLUSIVE,
                "exact_aliases_reviewed": entity["exact_aliases"],
                "exact_match_record_count": len(matched),
                "signal_present_in_coverage": bool(matched),
            }
        )

    methods = Counter(
        str(row.get("retrieval_method") or "")
        for row in issues
    )
    parser_modes = Counter(
        str(row.get("parser_mode") or "")
        for row in issues
    )

    return {
        "schema_version": 1,
        "design":
            "EXPANDED_CONTROL_CIPO_EXACT_REVIEWED_ALIAS_COMPLETENESS_PROOF",
        "source_family": SIGNAL_FAMILY,
        "research_boundary": (
            "This proof applies only to the nine HIGH-confidence expanded "
            "research controls in the reviewed alias contract. It does not "
            "modify Backtest 001 entities, the accepted five-control set, "
            "or Expansion Score weights."
        ),
        "signal_definition": (
            "At least one application in the official English CIPO "
            "Trademarks Journal Advertised Applications section from "
            "2000-01-05 through 2023-05-31 where the publication-time "
            "applicant begins with an exact reviewed legal alias."
        ),
        "inventory": {
            "start_date": COVERAGE_START_DATE,
            "end_date": "2023-05-31",
            "end_exclusive": COVERAGE_END_EXCLUSIVE,
            "issue_count": len(issues),
            "canonical_issue_sha256": inventory_hash,
            "expected_issue_count": expected_issue_count,
            "expected_canonical_issue_sha256": expected_inventory_hash,
        },
        "reviewed_alias_contract": reviewed_contract,
        "summary": {
            "shard_count": len(shard_payloads),
            "reviewed_entity_count": int(
                reviewed_contract.get("entity_count") or 0
            ),
            "reviewed_alias_count": int(
                reviewed_contract.get("alias_count") or 0
            ),
            "issue_count": len(issues),
            "complete_issue_count": sum(
                row.get("complete_for_exact_alias_absence") is True
                for row in issues
            ),
            "issue_failure_count": len(failures),
            "unresolved_alias_occurrence_count": len(unresolved),
            "application_rows_scanned": sum(
                int(row.get("application_count") or 0)
                for row in issues
            ),
            "exact_match_record_count": len(records),
            "entities_with_exact_match": len(records_by_entity),
            "entities_with_proven_absence": sum(
                gate_passed and not records_by_entity.get(
                    str(entity["entity_id"])
                )
                for entity in entities
                if isinstance(entity, dict)
            ),
            "retrieval_methods": dict(sorted(methods.items())),
            "parser_modes": dict(sorted(parser_modes.items())),
            "absence_inference_allowed_for_reviewed_aliases": gate_passed,
        },
        "gate": {
            "passed": gate_passed,
            "structural_errors": structural_errors,
            "issue_failures": failures,
            "unresolved_alias_occurrences": unresolved,
        },
        "coverage": coverage,
        "records": records,
        "shards": shard_summaries,
    }
