"""Create an invented NL review demonstration. No HTTP, real-data input or activation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from atlanticbridge.sources.nl_environmental_assessments import build_fixture_collection, RIGHTS_STATUS
from atlanticbridge.analyst_review import build_review_packet

FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/nl_environmental_assessments/synthetic-projects.html"

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, help="New local JSON file; existing files are never replaced")
    parser.add_argument("--registration", action="append", help="Invented registration-number string; may repeat")
    args = parser.parse_args(argv)
    selected = args.registration or ["009901", "9902", "9903", "9904", "9905", "9906", "9907", "9908"]
    collection = build_fixture_collection(FIXTURE.read_bytes(), selected)
    packet = build_review_packet([collection])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "fixture_only": True, "rights_status": RIGHTS_STATUS,
                      "finding_count": len(packet["findings"]), "lead_promotion_allowed": False}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
