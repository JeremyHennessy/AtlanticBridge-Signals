from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.control_identity import (
    build_backtest_control_set,
    load_json,
    validate_control_identity_review,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build identity-qualified time-indexed risk-set controls."
    )
    parser.add_argument(
        "--queue",
        default="reviews/control_cohorts/2026-09-20-risk-set-control-identity-review.json",
    )
    parser.add_argument(
        "--review",
        default="reviews/control_cohorts/2026-09-20-control-identity-decisions.json",
    )
    parser.add_argument(
        "--cohorts",
        default="reviews/outcome_audit/2026-09-20-outcome-cohorts.json",
    )
    parser.add_argument(
        "--manifest",
        default="reviews/control_cohorts/2026-09-20-risk-set-controls.manifest.json",
    )
    parser.add_argument(
        "--output",
        default="reviews/control_cohorts/2026-09-20-backtest-controls.json",
    )
    args = parser.parse_args()

    queue = load_json(args.queue)
    review = load_json(args.review)
    cohorts = load_json(args.cohorts)
    manifest = load_json(args.manifest)

    validate_control_identity_review(queue, review)
    payload = build_backtest_control_set(
        queue=queue,
        review=review,
        cohorts=cohorts,
        risk_manifest=manifest,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
