"""Commercial-validation diagnostics, separate from existing exploratory backtests.

Calibration examples are never an independent holdout. Current retrieval of an
old document does not establish historical public availability.
"""
from __future__ import annotations

from collections import Counter
from datetime import date
import math
import re

from .company_sources import instant, url

EVENT_TYPES = {"ANNOUNCED_FIRST_ESTABLISHMENT", "ANNOUNCED_EXPANSION_EXISTING_PRESENCE",
               "VERIFIED_OPERATIONAL_OPENING", "REGULATORY_OR_MEMBERSHIP_MILESTONE",
               "DISTRIBUTOR_OR_CUSTOMER_RELATIONSHIP", "DELAYED_OR_CANCELLED"}


def audit_outcomes(rows: list[dict]) -> dict:
    seen = set()
    for row in rows:
        if not row.get("id") or row["id"] in seen:
            raise ValueError("Missing or duplicate outcome id")
        seen.add(row["id"])
        if row.get("event_type") not in EVENT_TYPES:
            raise ValueError("Unreviewed outcome type")
        for field in ("first_entry_confirmed", "independent_holdout", "legal_identity_confirmed"):
            if field in row and type(row[field]) is not bool:
                raise ValueError("Outcome confirmation flags must be explicit booleans")
        url(row["source_url"])
        date.fromisoformat(row["source_publication_date"])
        if row.get("announcement_date"):
            date.fromisoformat(row["announcement_date"])
        opening = row.get("operational_opening_date")
        if row["event_type"] == "VERIFIED_OPERATIONAL_OPENING":
            if not opening or not row.get("opening_evidence"):
                raise ValueError("Verified opening requires both an opening date and retained evidence")
            date.fromisoformat(opening)
        elif opening:
            raise ValueError("Announcement/membership cannot stand in for operational opening")
        if row.get("first_entry_confirmed") and not row.get("prior_presence_review"):
            raise ValueError("First-entry confirmation requires independent prior-presence review")
        if row.get("independent_holdout") and (row.get("split") != "holdout" or not row.get("independent_reviewer")):
            raise ValueError("Calibration/developer-curated rows are not independent validation")
    return {"documented_examples": len(rows), "event_type_counts": dict(Counter(r["event_type"] for r in rows)),
            "verified_operational_openings": sum(r["event_type"] == "VERIFIED_OPERATIONAL_OPENING" for r in rows),
            "independent_holdout_rows": sum(r.get("independent_holdout") is True for r in rows),
            "legal_identity_qualified_rows": sum(r.get("legal_identity_confirmed") is True for r in rows),
            "expansion_score_publication_allowed": False}


def validate_split(rows: list[dict], frozen_at: str) -> dict:
    """Validate supplied cohort assignments; do not invent eligible companies."""
    frozen = instant(frozen_at)
    groups = {}
    keys = set()
    for row in rows:
        key = row.get("company_id")
        group = row.get("corporate_group_id")
        split = row.get("split")
        if not key or key in keys or not group or split not in {"development", "holdout", "prospective"}:
            raise ValueError("Unique companies and explicit corporate groups/splits are required")
        keys.add(key)
        if row.get("legal_identity_confirmed") is not True:
            raise ValueError("Unconfirmed legal identity cannot enter validation denominator")
        if groups.setdefault(group, split) != split:
            raise ValueError("Corporate-group leakage across data splits")
        if split == "holdout" and instant(row["first_evaluated_at"]) <= frozen:
            raise ValueError("Holdout was evaluated before design freeze")
        if row.get("outcome_label") == "NO_ENTRY" and not row.get("complete_followup_evidence"):
            raise ValueError("Missing evidence cannot be labelled no entry")
    return {"companies": len(rows), "corporate_groups": len(groups),
            "splits": dict(Counter(r["split"] for r in rows))}


def historical_signal_eligible(row: dict, cutoff: str) -> bool:
    """Require retained contemporaneous evidence, not just an old page date."""
    try:
        return (row.get("legal_identity_confirmed") is True
                and row.get("availability_basis") == "CONTEMPORANEOUS_RETAINED_SNAPSHOT"
                and bool(re.fullmatch(r"[a-f0-9]{64}", row.get("snapshot_sha256", "")))
                and instant(row["snapshot_observed_at"]) <= instant(cutoff)
                and instant(row["publicly_available_at"]) <= instant(cutoff))
    except (ValueError, KeyError, TypeError):
        return False


def review_metrics(rows: list[dict]) -> dict:
    """Explicit denominators; no submitted reviews means unknown, never 0% accuracy."""
    keys = set()
    for row in rows:
        if not row.get("alert_id") or row["alert_id"] in keys:
            raise ValueError("Duplicate/missing alert reviews would inflate denominator")
        keys.add(row["alert_id"])
        if not row.get("reviewer"):
            raise ValueError("Reviewer attribution required")
        for field in ("identity_correct", "source_supported", "useful", "already_known"):
            if row.get(field) is not None and type(row[field]) is not bool:
                raise ValueError("Review judgments must be booleans or unreviewed null")
        seconds = row.get("review_seconds")
        if seconds is not None and (type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0):
            raise ValueError("Review time must be finite and non-negative")
    def fraction(field):
        reviewed = [r[field] for r in rows if r.get(field) is not None]
        return {"reviewed": len(reviewed), "positive": sum(reviewed),
                "rate": sum(reviewed) / len(reviewed) if reviewed else None}
    verified_useful = [r for r in rows if all(r.get(f) is True for f in ("identity_correct", "source_supported", "useful"))]
    incremental = [r for r in verified_useful if r.get("already_known") is False]
    times = [r["review_seconds"] for r in rows if r.get("review_seconds") is not None]
    return {"submitted_reviews": len(rows), "identity_accuracy": fraction("identity_correct"),
            "source_support": fraction("source_supported"), "reviewer_usefulness": fraction("useful"),
            "verified_useful_alerts": len(verified_useful), "new_to_reviewer_verified_useful_alerts": len(incremental),
            "mean_review_seconds": sum(times) / len(times) if times else None,
            "commercial_viability_proven": False, "expansion_score_publication_allowed": False}
