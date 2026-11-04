"""Build a local-only analyst review packet from staged collector envelopes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atlanticbridge.analyst_review import build_review_packet


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, help="Collector JSON envelope; may be repeated")
    parser.add_argument("--output", required=True, help="Local packet path to create or replace")
    args = parser.parse_args(argv)

    collections = []
    for source_path in args.input:
        data = json.loads(Path(source_path).read_text(encoding="utf-8"))
        collections.append(data)
    packet = build_review_packet(collections)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    print(json.dumps({
        "output": str(target),
        "collection_count": len(packet["collections"]),
        "finding_count": len(packet["findings"]),
        "workflow_mode": packet["workflow_mode"],
        "lead_promotion_allowed": packet["lead_promotion_allowed"],
        "independent_verification": packet["independent_verification"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
