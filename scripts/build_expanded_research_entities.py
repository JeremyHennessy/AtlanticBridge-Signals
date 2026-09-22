from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BATCH_PATHS = [
    ROOT / "reviews" / "control_cohorts" / "2026-09-22-expanded-control-identity-batch-01.json",
    ROOT / "reviews" / "control_cohorts" / "2026-09-22-expanded-control-identity-batch-02.json",
]
BASE_ENTITIES_PATH = ROOT / "reviews" / "backtests" / "2026-09-21-backtest-entities.json"


def normalized_alias(value: str) -> str:
    return "".join(ch.casefold() for ch in value if ch.isalnum())


def build_payload() -> dict:
    base = json.loads(BASE_ENTITIES_PATH.read_text(encoding="utf-8"))
    entrants = {
        row["candidate_outcome_id"]: row
        for row in base["entities"]
        if row.get("role") == "ENTRANT"
    }

    records = []
    for path in BATCH_PATHS:
        doc = json.loads(path.read_text(encoding="utf-8"))
        for row in doc["records"]:
            if row.get("review_decision") != "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY":
                continue
            assigned = row.get("assigned_candidate_outcome_ids") or []
            if len(assigned) != 1:
                raise ValueError(f"Expanded control must map to exactly one candidate: {row['control_entity_key']}")
            candidate_id = assigned[0]
            entrant = entrants.get(candidate_id)
            if entrant is None:
                raise ValueError(f"Missing entrant anchor for {candidate_id}")

            aliases = []
            seen = set()
            for value in (row.get("investor_name"), row.get("foreign_legal_name")):
                value = str(value or "").strip()
                key = normalized_alias(value)
                if value and key not in seen:
                    aliases.append(value)
                    seen.add(key)
            if not aliases:
                raise ValueError(f"No reviewed aliases for {row['control_entity_key']}")

            records.append(
                {
                    "entity_id": f"control:{row['control_entity_key']}",
                    "role": "CONTROL",
                    "candidate_outcome_id": candidate_id,
                    "anchor_month": entrant["anchor_month"],
                    "display_name": row.get("foreign_legal_name") or row["investor_name"],
                    "ultimate_control_country": row.get("ultimate_control_country"),
                    "foreign_legal_name": row.get("foreign_legal_name"),
                    "identity_status": "QUALIFIED_FOREIGN_OPERATING_LEGAL_ENTITY",
                    "identity_confidence": row.get("identity_confidence"),
                    "exact_aliases": aliases,
                    "foreign_signal_identity_eligible": True,
                    "later_new_business_month": row.get("later_new_business_month"),
                    "research_status": row.get("integration_status"),
                }
            )

    records.sort(key=lambda row: row["entity_id"])
    if len(records) != 9 or len({row["entity_id"] for row in records}) != 9:
        raise ValueError("Expected exactly nine unique expanded research controls")

    return {
        "schema_version": 1,
        "review_date": "2026-09-22",
        "purpose": "Exact reviewed aliases for the nine newly identity-qualified future-entrant controls. These rows are research controls, not permanent negatives and not current prospects.",
        "anchor_rule": base["anchor_rule"],
        "cutoff_rule": base["cutoff_rule"],
        "identity_rule": base["identity_rule"],
        "entities": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        default="reviews/backtests/2026-09-22-expanded-research-entities.json",
    )
    args = parser.parse_args()
    payload = build_payload()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"entity_count": len(payload["entities"]), "output": str(output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
