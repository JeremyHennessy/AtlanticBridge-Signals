from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


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


def discover_shards(directory: Path) -> list[Path]:
    paths = sorted(directory.glob("shard-*.json"))
    if not paths:
        raise ValueError(f"no CIPO Journal shard files found in {directory}")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-dir", required=True)
    parser.add_argument(
        "--known-case-manifest",
        default="reviews/backtests/2026-09-21-cipo-journal-known-case-manifest.json",
    )
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    shard_paths = discover_shards(Path(args.shard_dir))
    known = load_json(args.known_case_manifest)
    entities_payload = load_json(args.entities)

    structural_errors: list[str] = []
    issue_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    unresolved: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    shard_summaries = []
    alias_contracts = []

    for path in shard_paths:
        payload = load_json(path)
        if payload.get("design") != "CIPO_JOURNAL_FULL_SCAN_SHARD":
            structural_errors.append(f"{path.name}: unexpected design")
            continue
        alias_contract = payload.get("alias_contract")
        if not isinstance(alias_contract, dict):
            structural_errors.append(f"{path.name}: missing alias_contract")
            continue
        alias_contracts.append(alias_contract)
        issue_rows.extend(payload.get("issue_proof") or [])
        failures.extend(payload.get("failures") or [])
        unresolved.extend(payload.get("unresolved_alias_occurrences") or [])
        records.extend(payload.get("records") or [])
        shard_summaries.append(
            {
                "file": path.name,
                "shard": payload.get("shard"),
                "summary": payload.get("summary"),
                "inventory": payload.get("inventory"),
            }
        )

    if alias_contracts:
        canonical_alias = canonical_json(alias_contracts[0])
        for index, contract in enumerate(alias_contracts[1:], start=2):
            if canonical_json(contract) != canonical_alias:
                structural_errors.append(
                    f"alias contract differs in shard index {index}"
                )
        alias_contract = alias_contracts[0]
    else:
        alias_contract = {
            "entity_count": 0,
            "alias_count": 0,
            "aliases": [],
        }

    issue_by_date: dict[str, dict[str, object]] = {}
    for row in issue_rows:
        if not isinstance(row, dict):
            structural_errors.append("issue proof row is not an object")
            continue
        published = str(row.get("publication_date") or "")
        if not published:
            structural_errors.append("issue proof row missing publication_date")
            continue
        if published in issue_by_date:
            structural_errors.append(f"duplicate issue date: {published}")
            continue
        issue_by_date[published] = row

    issues = sorted(
        issue_by_date.values(),
        key=lambda row: str(row["publication_date"]),
    )

    material = "\n".join(
        f"{row['publication_date']}|{row['pdf_url']}"
        for row in issues
    ) + ("\n" if issues else "")
    inventory_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()

    known_inventory = known.get("inventory")
    if not isinstance(known_inventory, dict):
        raise ValueError("known-case manifest lacks inventory")
    expected_issue_count = int(known_inventory["issue_count"])
    expected_inventory_hash = str(
        known_inventory["canonical_issue_sha256"]
    )

    if len(issues) != expected_issue_count:
        structural_errors.append(
            f"issue count mismatch: {len(issues)} != {expected_issue_count}"
        )
    if inventory_hash != expected_inventory_hash:
        structural_errors.append(
            "inventory hash mismatch: "
            f"{inventory_hash} != {expected_inventory_hash}"
        )

    incomplete_issue_rows = [
        row
        for row in issues
        if row.get("complete_for_exact_alias_absence") is not True
    ]
    if incomplete_issue_rows:
        structural_errors.append(
            f"{len(incomplete_issue_rows)} issue rows are incomplete"
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
        elif (
            row.get("alias_kind") == "HISTORICAL_LEGAL_NAME"
            and existing.get("alias_kind") != "HISTORICAL_LEGAL_NAME"
        ):
            dedup_records[key] = row

    records = sorted(
        dedup_records.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["application_number"]),
        ),
    )

    record_keys = {
        (
            str(row["application_number"]),
            str(row["publicly_available_date"]),
        )
        for row in records
    }
    required_cases = known.get("required_cases")
    if not isinstance(required_cases, list):
        raise ValueError("known-case manifest lacks required_cases")

    missing_required = []
    for case in required_cases:
        if not isinstance(case, dict):
            raise ValueError("required case must be object")
        key = (
            str(case["application_number"]),
            str(case["publication_date"]),
        )
        if key not in record_keys:
            missing_required.append(
                {
                    "case_id": case.get("case_id"),
                    "application_number": key[0],
                    "publication_date": key[1],
                }
            )

    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("backtest entities payload requires entities")

    aliases_by_entity: dict[str, list[str]] = {}
    for row in alias_contract.get("aliases") or []:
        if not isinstance(row, dict):
            continue
        aliases_by_entity.setdefault(
            str(row["entity_id"]),
            [],
        ).append(str(row["alias"]))

    gate_passed = (
        not structural_errors
        and not failures
        and not unresolved
        and not missing_required
        and len(issues) == expected_issue_count
        and inventory_hash == expected_inventory_hash
        and all(
            row.get("complete_for_exact_alias_absence") is True
            for row in issues
        )
    )

    coverage = []
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        entity_id = str(entity["entity_id"])
        coverage.append(
            {
                "entity_id": entity_id,
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_OFFICIAL_JOURNAL_EXACT_ALIAS_HISTORY_"
                    "2000_TO_2023_05_31"
                    if gate_passed
                    else "JOURNAL_FULL_SCAN_INCOMPLETE"
                ),
                "absence_coverage_proven": gate_passed,
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "coverage_start_date": COVERAGE_START_DATE,
                "coverage_end_exclusive": COVERAGE_END_EXCLUSIVE,
                "aliases_reviewed": sorted(
                    aliases_by_entity.get(entity_id, [])
                ),
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

    issue_audit_material = "\n".join(
        "\x1f".join(
            [
                str(row["publication_date"]),
                str(row["retrieval_method"]),
                str(row["parser_mode"]),
                str(row["application_count"]),
                str(row["advertised_section_sha256"]),
                str(row["applications_canonical_sha256"]),
                str(row["unresolved_alias_occurrence_count"]),
            ]
        )
        for row in issues
    ) + ("\n" if issues else "")

    payload = {
        "schema_version": 1,
        "design": "CIPO_JOURNAL_FULL_COMPLETENESS_PROOF",
        "source_family": SIGNAL_FAMILY,
        "signal_definition": (
            "At least one application in the official English CIPO Trademarks "
            "Journal Advertised Applications section from 2000-01-05 through "
            "2023-05-31 where the publication-time applicant begins with an "
            "exact reviewed current or source-backed historical legal alias."
        ),
        "coverage_definition": (
            "All 1,221 official Journal issues in the accepted inventory are "
            "fetched and their Advertised Applications sections parsed. "
            "A non-hit is absence only for the reviewed alias set and only "
            "when every issue is complete and no alias occurrence is ambiguous."
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
        "summary": {
            "shard_count": len(shard_paths),
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
            "entities_with_exact_match": len(
                {str(row["entity_id"]) for row in records}
            ),
            "retrieval_methods": dict(sorted(methods.items())),
            "parser_modes": dict(sorted(parser_modes.items())),
            "absence_inference_allowed": gate_passed,
        },
        "gate": {
            "passed": gate_passed,
            "structural_errors": structural_errors,
            "missing_required_cases": missing_required,
            "issue_failures": failures,
            "unresolved_alias_occurrences": unresolved,
        },
        "alias_contract": alias_contract,
        "coverage": coverage,
        "records": records,
        "issue_audit": issues,
        "issue_audit_canonical_sha256": hashlib.sha256(
            issue_audit_material.encode("utf-8")
        ).hexdigest(),
        "shards": shard_summaries,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["gate"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
