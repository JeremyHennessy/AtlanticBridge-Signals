#!/usr/bin/env python3
"""Build a local-only, bundled Halifax pilot packet; never overwrite output."""
import argparse
import json
from pathlib import Path
from atlanticbridge.sources.halifax_building_permits import build_pinned_collection
from atlanticbridge.analyst_review import build_review_packet

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("ui_observed", "invented"), default="ui_observed")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--generated-at")
    args = parser.parse_args(argv)
    packet = build_review_packet([build_pinned_collection(args.kind)], generated_at=args.generated_at)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(packet, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
