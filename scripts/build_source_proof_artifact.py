from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MAX_BACKTEST_CUTOFF_EXCLUSIVE = "2023-06-01"


def _copy_rows(rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list):
        raise ValueError("source proof rows must be lists")
    result: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("source proof rows must contain objects")
        result.append(dict(row))
    return result


def normalize_cipo(payload: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "source_family": payload["source_family"],
        "coverage_definition": payload["coverage_definition"],
        "known_coverage_gap": payload["known_coverage_gap"],
        "source_metadata": payload["source_metadata"],
        "summary": payload["summary"],
        "coverage": _copy_rows(payload["coverage"]),
        "records": _copy_rows(payload["records"]),
    }


def normalize_canadabuys(payload: dict[str, object]) -> dict[str, object]:
    semantic_window = payload.get("semantic_window")
    summary = payload.get("summary")
    if not isinstance(semantic_window, dict) or not isinstance(summary, dict):
        raise ValueError("CanadaBuys proof requires semantic_window and summary")

    coverage = _copy_rows(payload["coverage"])
    for row in coverage:
        row["coverage_end_exclusive"] = MAX_BACKTEST_CUTOFF_EXCLUSIVE

    records = [
        row
        for row in _copy_rows(payload["records"])
        if str(row.get("publicly_available_date") or "")
        < MAX_BACKTEST_CUTOFF_EXCLUSIVE
    ]

    return {
        "schema_version": 1,
        "source_family": payload["source_family"],
        "source_definition": payload["source_definition"],
        "coverage_definition": payload["coverage_definition"],
        "semantic_window": semantic_window,
        "summary": {
            "entity_count": summary["entity_count"],
            "source_file_count": summary["source_file_count"],
            "semantic_window_unique_reference_amendment_keys":
                semantic_window["unique_reference_amendment_keys"],
            "semantic_window_exact_reviewed_alias_matches":
                semantic_window["exact_reviewed_alias_matches"],
        },
        "coverage": coverage,
        "records": records,
    }


def normalize_ted(payload: dict[str, object]) -> dict[str, object]:
    coverage = _copy_rows(payload["coverage"])
    for row in coverage:
        row.pop("coverage_end_date", None)
        row["coverage_end_exclusive"] = MAX_BACKTEST_CUTOFF_EXCLUSIVE

    records = [
        row
        for row in _copy_rows(payload["records"])
        if str(row.get("publicly_available_date") or "")
        < MAX_BACKTEST_CUTOFF_EXCLUSIVE
    ]

    query_proof = payload.get("query_proof")
    if not isinstance(query_proof, list):
        raise ValueError("TED proof requires query_proof")

    return {
        "schema_version": 1,
        "source_family": payload["source_family"],
        "signal_definition": payload["signal_definition"],
        "coverage_definition": payload["coverage_definition"],
        "coverage_window": {
            "start_date": "2012-01-01",
            "end_exclusive": MAX_BACKTEST_CUTOFF_EXCLUSIVE,
        },
        "summary": payload["summary"],
        "coverage": coverage,
        "query_proof": query_proof,
        "records": records,
    }


def normalize_source(
    source: str,
    payload: dict[str, object],
) -> dict[str, object]:
    if source == "cipo":
        return normalize_cipo(payload)
    if source == "canadabuys":
        return normalize_canadabuys(payload)
    if source == "ted":
        return normalize_ted(payload)
    raise ValueError(f"unsupported source proof: {source}")


def canonical_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def validate_expected(
    generated: bytes,
    *,
    expected_path: Path | None,
    manifest_path: Path | None,
) -> None:
    generated_sha = sha256_bytes(generated)

    if expected_path is not None:
        expected = expected_path.read_bytes()
        if generated != expected:
            raise ValueError(
                "normalized source proof differs from the pinned evidence artifact: "
                f"generated_sha256={generated_sha} "
                f"expected_sha256={sha256_bytes(expected)}"
            )

    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        accepted = manifest.get("accepted_evidence_artifact")
        if not isinstance(accepted, dict):
            raise ValueError(
                f"manifest lacks accepted_evidence_artifact: {manifest_path}"
            )
        expected_sha = str(accepted.get("sha256") or "")
        if generated_sha != expected_sha:
            raise ValueError(
                "normalized source proof hash differs from manifest: "
                f"{generated_sha} != {expected_sha}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize live source collection into a stable backtest proof."
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=("cipo", "canadabuys", "ted"),
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--expected")
    parser.add_argument("--manifest")
    args = parser.parse_args()

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    normalized = normalize_source(args.source, payload)
    output_bytes = canonical_bytes(normalized)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(output_bytes)

    validate_expected(
        output_bytes,
        expected_path=Path(args.expected) if args.expected else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
    )

    print(
        json.dumps(
            {
                "source": args.source,
                "bytes": len(output_bytes),
                "sha256": sha256_bytes(output_bytes),
                "coverage_rows": len(normalized.get("coverage") or []),
                "evidence_records": len(normalized.get("records") or []),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
