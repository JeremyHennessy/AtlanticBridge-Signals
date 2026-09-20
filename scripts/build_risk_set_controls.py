from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from atlanticbridge.risk_set_controls import build_risk_set_controls
from atlanticbridge.sources.investment_canada import (
    SOURCE_NAME,
    crawl_investment_canada_history,
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_live_payload(
    *,
    cohorts_path: Path,
    audit_path: Path,
    horizon_months: int,
    max_controls: int,
    workers: int,
) -> dict[str, object]:
    cohort_payload = json.loads(cohorts_path.read_text(encoding="utf-8"))
    audit_payload = json.loads(audit_path.read_text(encoding="utf-8"))
    crawl = crawl_investment_canada_history(workers=workers)

    payload = build_risk_set_controls(
        crawl.records,
        cohort_payload,
        audit_payload,
        horizon_months=horizon_months,
        max_controls=max_controls,
    )

    snapshot_material = [
        {
            "source_url": item.source_url,
            "source_bucket": item.source_bucket,
            "source_page": item.source_page,
            "sha256": item.sha256,
            "record_count": item.record_count,
        }
        for item in crawl.page_snapshots
    ]
    payload["source_proof"] = {
        "source_name": SOURCE_NAME,
        "bucket_count": crawl.bucket_count,
        "page_count": crawl.page_count,
        "record_appearances": crawl.appearances,
        "duplicate_appearances": crawl.duplicate_appearances,
        "unique_records": crawl.unique_records,
        "snapshot_manifest_sha256": hashlib.sha256(
            _canonical_json(snapshot_material).encode("utf-8")
        ).hexdigest(),
    }
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build censored future-entrant risk-set controls from the complete Investment Canada history."
    )
    parser.add_argument(
        "--cohorts",
        default="reviews/outcome_audit/2026-09-20-outcome-cohorts.json",
    )
    parser.add_argument(
        "--audit",
        default="reviews/outcome_audit/2026-09-20-cases.json",
    )
    parser.add_argument(
        "--output",
        default="reviews/control_cohorts/2026-09-20-risk-set-controls.json",
    )
    parser.add_argument("--horizon-months", type=int, default=24)
    parser.add_argument("--max-controls", type=int, default=5)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    payload = build_live_payload(
        cohorts_path=Path(args.cohorts),
        audit_path=Path(args.audit),
        horizon_months=args.horizon_months,
        max_controls=args.max_controls,
        workers=args.workers,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["source_proof"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
