"""Print actual validation readiness without fabricating pilot results."""
import json
from pathlib import Path
from atlanticbridge.commercial_validation import audit_outcomes, review_metrics

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT / "reviews/commercial_validation/design-2026-09-22.json").read_text())
outcomes = json.loads((ROOT / "reviews/commercial_validation/calibration-outcomes-2026-09-22.json").read_text())
result = {"design_status": plan["design_status"], "outcomes": audit_outcomes(outcomes),
          "pilot": review_metrics(plan["pilot_reviews"]), "targets_not_achieved_counts": plan["development_targets"]}
print(json.dumps(result, indent=2))
