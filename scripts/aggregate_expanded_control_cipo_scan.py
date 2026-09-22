from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.expanded_control_cipo import (
    aggregate_expanded_control_cipo_shards,
    build_reviewed_entity_contract,
    load_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate the nine-control expanded research CIPO Journal scan "
            "against the accepted 2000-2023-05-31 inventory."
        )
    )
    parser.add_argument("--shard-dir", required=True)
    parser.add_argument(
        "--batch",
        action="append",
        required=True,
        help="Expanded control identity review batch JSON; repeatable.",
    )
    parser.add_argument(
        "--accepted-inventory",
        default=(
            "reviews/backtests/"
            "2026-09-21-cipo-journal-known-case-manifest.json"
        ),
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    shard_paths = sorted(Path(args.shard_dir).glob("shard-*.json"))
    if not shard_paths:
        raise ValueError("no expanded-control CIPO shard files found")

    batch_payloads = [load_json(path) for path in args.batch]
    reviewed_contract = build_reviewed_entity_contract(batch_payloads)

    accepted = load_json(args.accepted_inventory)
    inventory = accepted.get("inventory")
    if not isinstance(inventory, dict):
        raise ValueError("accepted CIPO manifest lacks inventory")

    result = aggregate_expanded_control_cipo_shards(
        shard_payloads=[load_json(path) for path in shard_paths],
        accepted_inventory=inventory,
        reviewed_contract=reviewed_contract,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    print(json.dumps(result["gate"], indent=2, sort_keys=True))
    return 0 if result["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
