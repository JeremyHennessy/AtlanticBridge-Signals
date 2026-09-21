from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.backtest_metrics import build_backtest_001


def load_json(path: str) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run fail-closed Backtest 001 event-time diagnostics."
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
        default="reviews/backtests/2026-09-21-backtest-001.json",
    )
    args = parser.parse_args()

    result = build_backtest_001(
        entities_payload=load_json(args.entities),
        semantics_payload=load_json(args.semantics),
        accepted_input=load_json(args.accepted_input),
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
