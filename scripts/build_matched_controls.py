from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.db import connect
from atlanticbridge.matched_controls import build_matched_controls, load_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--cohorts", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--per-case", type=int, default=3)
    args = parser.parse_args()

    conn = connect(args.db)
    payload = build_matched_controls(
        conn,
        cases_payload=load_json(args.cases),
        cohort_payload=load_json(args.cohorts),
        controls_per_case=args.per_case,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
