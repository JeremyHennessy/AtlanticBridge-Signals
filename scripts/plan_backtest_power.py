from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.backtest_power import build_backtest_power_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build exact Fisher power-planning scenarios for Backtest 002."
    )
    parser.add_argument(
        "--output",
        default="reviews/backtests/2026-09-22-backtest-power-plan.json",
    )
    args = parser.parse_args()

    result = build_backtest_power_plan()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
