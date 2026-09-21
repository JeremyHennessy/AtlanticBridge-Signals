from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.event_time_signals import build_event_time_snapshots, load_json


def combine_evidence(paths: list[str]) -> dict[str, object]:
    coverage: list[dict[str, object]] = []
    records: list[dict[str, object]] = []
    source_summaries: list[dict[str, object]] = []
    for path in paths:
        payload = load_json(path)
        source_summaries.append(
            {
                "path": path,
                "source_family": payload.get("source_family"),
                "summary": payload.get("summary"),
                "source_metadata": payload.get("source_metadata"),
            }
        )
        raw_coverage = payload.get("coverage") or []
        raw_records = payload.get("records") or []
        if not isinstance(raw_coverage, list) or not isinstance(raw_records, list):
            raise ValueError(f"invalid evidence payload: {path}")
        coverage.extend(raw_coverage)
        records.extend(raw_records)
    return {
        "schema_version": 1,
        "source_summaries": source_summaries,
        "coverage": coverage,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--semantics",
        default="reviews/backtests/2026-09-21-signal-source-semantics.json",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="One or more source evidence JSON payloads.",
    )
    parser.add_argument("--combined-evidence-output")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    combined = combine_evidence(args.evidence)
    snapshots = build_event_time_snapshots(
        entities_payload=load_json(args.entities),
        semantics_payload=load_json(args.semantics),
        evidence_payload=combined,
    )
    snapshots["source_summaries"] = combined["source_summaries"]

    if args.combined_evidence_output:
        combined_path = Path(args.combined_evidence_output)
        combined_path.parent.mkdir(parents=True, exist_ok=True)
        combined_path.write_text(
            json.dumps(combined, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(snapshots, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(snapshots["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
