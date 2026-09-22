from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from atlanticbridge.canadabuys_store import ensure_canadabuys_schema
from atlanticbridge.db import connect
from atlanticbridge.live_signals import write_live_signals
from atlanticbridge.live_signal_scope import apply_commercial_scope


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", default="ui/data/live-signals.json")
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--as-of-date")
    args = parser.parse_args()

    conn = connect(args.db)
    ensure_canadabuys_schema(conn)
    as_of = date.fromisoformat(args.as_of_date) if args.as_of_date else None
    payload = write_live_signals(
        conn,
        args.output,
        as_of_date=as_of,
        lookback_days=args.lookback_days,
    )
    payload = apply_commercial_scope(payload, conn)
    Path(args.output).write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    conn.close()
    print(
        json.dumps(
            {
                "status": payload["status"],
                "generated_at": payload["generated_at"],
                "summary": payload["summary"],
                "output": args.output,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
