from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.backtest_metrics import build_backtest_001
from atlanticbridge.backtest_statistics import build_backtest_002


def load_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Backtest 002 statistical sufficiency diagnostics."
    )
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--semantics",
        default="reviews/backtests/2026-09-21-signal-source-semantics.json",
    )
    parser.add_argument(
        "--accepted-input",
        default="reviews/backtests/2026-09-21-backtest-001-input.json",
    )
    parser.add_argument(
        "--output",
        default="reviews/backtests/2026-09-21-backtest-002.json",
    )
    args = parser.parse_args()

    backtest_001 = build_backtest_001(
        entities_payload=load_json(args.entities),
        semantics_payload=load_json(args.semantics),
        accepted_input=load_json(args.accepted_input),
    )
    result = build_backtest_002(backtest_001=backtest_001)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "candidate_signal_count": result["candidate_signal_count"],
                "inferentially_resolved_rows": result[
                    "inferentially_resolved_rows"
                ],
                "expansion_score_1_0_weight_publication_allowed": result[
                    "expansion_score_1_0_weight_publication_allowed"
                ],
                "score_publication_gate_reason": result[
                    "score_publication_gate_reason"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
