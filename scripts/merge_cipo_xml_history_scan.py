from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


EXPECTED_ARCHIVE_COUNT = 145
SIGNAL_FAMILY = "CIPO_CANADIAN_TRADEMARK"


def load_worker_payloads(input_dir: Path) -> list[dict[str, object]]:
    paths = sorted(input_dir.rglob("worker-*.json"))
    if not paths:
        raise ValueError(f"no worker JSON files found under {input_dir}")
    payloads = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in paths
    ]
    return payloads


def merge(
    *,
    entities_payload: dict[str, object],
    workers: list[dict[str, object]],
) -> dict[str, object]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("backtest entities payload requires entities list")

    worker_ids = []
    worker_counts = set()
    chunk_by_sequence: dict[int, dict[str, object]] = {}
    matches: list[dict[str, object]] = []

    for worker in workers:
        worker_id = int(worker["worker_id"])
        worker_count = int(worker["worker_count"])
        worker_ids.append(worker_id)
        worker_counts.add(worker_count)

        chunks = worker.get("chunks")
        raw_matches = worker.get("matches")
        if not isinstance(chunks, list) or not isinstance(raw_matches, list):
            raise ValueError("worker payload lacks chunks/matches")

        for chunk in chunks:
            if not isinstance(chunk, dict):
                raise ValueError("chunk rows must be objects")
            sequence = int(chunk["sequence"])
            if sequence in chunk_by_sequence:
                raise ValueError(f"duplicate archive sequence {sequence}")
            chunk_by_sequence[sequence] = chunk

        for match in raw_matches:
            if not isinstance(match, dict):
                raise ValueError("match rows must be objects")
            matches.append(match)

    if len(worker_counts) != 1:
        raise ValueError(f"inconsistent worker_count values: {worker_counts}")
    worker_count = next(iter(worker_counts))
    if sorted(worker_ids) != list(range(worker_count)):
        raise ValueError(
            f"missing/duplicate workers: ids={sorted(worker_ids)} "
            f"worker_count={worker_count}"
        )

    expected_sequences = list(range(1, EXPECTED_ARCHIVE_COUNT + 1))
    if sorted(chunk_by_sequence) != expected_sequences:
        raise ValueError(
            "complete historical XML scan did not cover sequences "
            f"1..{EXPECTED_ARCHIVE_COUNT}"
        )

    entity_ids = {
        str(entity["entity_id"])
        for entity in entities
        if isinstance(entity, dict)
    }
    for match in matches:
        if str(match["entity_id"]) not in entity_ids:
            raise ValueError(
                f"scan match references unknown entity {match['entity_id']}"
            )

    deduped: dict[tuple[str, str], dict[str, object]] = {}
    for match in matches:
        key = (
            str(match["entity_id"]),
            str(match["application_number"]),
        )
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = match
            continue

        comparable_fields = (
            "matched_applicant_name",
            "normalized_applicant_name",
            "advertised_dates",
            "earliest_advertised_date",
            "xml_sha256",
        )
        for field in comparable_fields:
            if existing.get(field) != match.get(field):
                raise ValueError(
                    f"conflicting CIPO XML evidence for {key}: {field}"
                )

    matches = sorted(
        deduped.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["application_number"]),
        ),
    )

    evidence = []
    for match in matches:
        available = match.get("earliest_advertised_date")
        if not available:
            continue
        evidence_id = hashlib.sha256(
            "\x1f".join(
                [
                    str(match["entity_id"]),
                    str(match["application_number"]),
                    str(available),
                ]
            ).encode("utf-8")
        ).hexdigest()
        evidence.append(
            {
                "evidence_id": evidence_id,
                "entity_id": match["entity_id"],
                "signal_family": SIGNAL_FAMILY,
                "application_number": match["application_number"],
                "matched_applicant_name": match["matched_applicant_name"],
                "publicly_available_date": available,
                "publicly_available_date_precision": "DAY",
                "publicly_available_date_basis": (
                    "CIPO annual full historical ST.96 XML: exact Applicant "
                    "entity with Advertised publication/action history."
                ),
                "source_collection": "CA-TMK-GLOBAL_2025-06-14",
                "source_archive_sequence": match["archive_sequence"],
                "source_archive_filename": match["archive_filename"],
                "source_xml_sha256": match["xml_sha256"],
                "match_method": "EXACT_REVIEWED_ALIAS_APPLICANT_XML",
            }
        )

    evidence.sort(
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["application_number"]),
        )
    )

    coverage = []
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        coverage.append(
            {
                "entity_id": entity["entity_id"],
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_CIPO_FULL_HISTORICAL_XML_EXACT_APPLICANT_"
                    "HISTORY_1980_ONWARD"
                ),
                "absence_coverage_proven": True,
                "coverage_start_date": "1980-01-01",
                "coverage_end_exclusive": "2025-06-15",
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "collection": "CA-TMK-GLOBAL_2025-06-14",
                "archive_sequence_count": EXPECTED_ARCHIVE_COUNT,
            }
        )

    chunk_hash_material = "\n".join(
        f"{sequence:03d}\x1f{chunk_by_sequence[sequence]['archive_sha256']}\x1f"
        f"{chunk_by_sequence[sequence]['xml_entries_scanned']}"
        for sequence in expected_sequences
    )
    evidence_key_material = "\n".join(
        f"{row['entity_id']}\x1f{row['application_number']}\x1f"
        f"{row['publicly_available_date']}"
        for row in evidence
    )
    entity_match_counts = Counter(
        str(row["entity_id"]) for row in matches
    )
    entity_evidence_counts = Counter(
        str(row["entity_id"]) for row in evidence
    )

    return {
        "schema_version": 1,
        "source_family": SIGNAL_FAMILY,
        "design": "CIPO_FULL_HISTORICAL_XML_EXACT_APPLICANT_SCAN",
        "collection": {
            "name": "CA-TMK-GLOBAL_2025-06-14",
            "archive_sequence_count": EXPECTED_ARCHIVE_COUNT,
            "archive_manifest_sha256": hashlib.sha256(
                chunk_hash_material.encode("utf-8")
            ).hexdigest(),
            "coverage_start_date": "1980-01-01",
            "coverage_end_exclusive": "2025-06-15",
            "coverage_interpretation": (
                "CIPO annual refreshed historical collection covers trademarks "
                "through the completed historical period. The signal is limited "
                "to exact Applicant aliases and Advertised public dates. The "
                "1980 lower bound avoids CIPO's documented incomplete inactive "
                "pre-1979/refused-abandoned pre-1980 history."
            ),
        },
        "summary": {
            "entity_count": len(entities),
            "worker_count": worker_count,
            "archive_sequence_count": len(chunk_by_sequence),
            "xml_entries_scanned": sum(
                int(row["xml_entries_scanned"])
                for row in chunk_by_sequence.values()
            ),
            "candidate_raw_alias_hits": sum(
                int(row["candidate_raw_alias_hits"])
                for row in chunk_by_sequence.values()
            ),
            "confirmed_applicant_records": len(matches),
            "advertised_evidence_records": len(evidence),
            "entities_with_applicant_record": len(entity_match_counts),
            "entities_with_advertised_evidence": len(entity_evidence_counts),
            "evidence_key_sha256": hashlib.sha256(
                evidence_key_material.encode("utf-8")
            ).hexdigest(),
        },
        "entity_applicant_match_counts": {
            entity_id: entity_match_counts[entity_id]
            for entity_id in sorted(entity_ids)
        },
        "entity_advertised_evidence_counts": {
            entity_id: entity_evidence_counts[entity_id]
            for entity_id in sorted(entity_ids)
        },
        "coverage": coverage,
        "records": evidence,
        "applicant_matches": matches,
        "chunks": [
            chunk_by_sequence[sequence]
            for sequence in expected_sequences
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    payload = merge(
        entities_payload=entities,
        workers=load_worker_payloads(Path(args.input_dir)),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(
        json.dumps(
            payload["entity_advertised_evidence_counts"],
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
