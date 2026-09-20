"""Export every confirmed outcome and its registry evidence for a timing audit.

Run after the existing history and entry-identity CLI commands. This never
promotes incorporation dates into first-operation dates or model eligibility.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from atlanticbridge.entry_identity import _lead_timing


def export_audit(db_path, output):
    conn = sqlite3.connect(f"file:{Path(db_path).resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        run = conn.execute("SELECT * FROM entry_identity_runs ORDER BY observed_at DESC LIMIT 1").fetchone()
        if run is None:
            raise ValueError("No entry identity run available")
        cases = []
        for row in conn.execute("""
            SELECT e.*, n.source_url AS outcome_source_url, n.investor_node_id,
                   n.notification_type
            FROM entry_identity_matches e
            JOIN investment_canada_notifications n ON n.record_id = e.outcome_record_id
            WHERE e.run_id = ? AND e.detail_status = 'FEDERAL_ENTITY_CONFIRMED'
            ORDER BY e.certification_month, e.investor_name, e.outcome_record_id
        """, (run["run_id"],)):
            raw = row["detail_raw_json"]
            if hashlib.sha256(raw.encode()).hexdigest() != row["detail_raw_hash"]:
                raise ValueError("Registry detail hash mismatch")
            timing, days = _lead_timing(row["certification_month"], row["federal_event_date"])
            cases.append({
                "outcome_record_id": row["outcome_record_id"],
                "investor_name": row["investor_name"],
                "investor_node_id": row["investor_node_id"],
                "ultimate_control_country": row["ultimate_control_country"],
                "canadian_business_name": row["matched_business_name"],
                "corporation_number": row["selected_corporation_number"],
                "notification_type": row["notification_type"],
                "notification_month": row["certification_month"],
                "outcome_source_url": row["outcome_source_url"],
                "registry_source_url": row["detail_source_url"],
                "registry_observed_at": row["observed_at"],
                "registry_raw_sha256": row["detail_raw_hash"],
                "registry_evidence": json.loads(raw),
                "federal_event_type": row["federal_event_type"],
                "federal_event_date": row["federal_event_date"],
                "notification_timing": timing,
                "days_before_notification_month": days,
                "outcome_classification": "UNRESOLVED",
                "first_canadian_operations_date": None,
                "model_eligible": False,
                "audit_note": "Registry event verified; first Canadian operations and notification meaning not established.",
                "additional_evidence": [],
            })
        expected = conn.execute("SELECT COUNT(*) FROM entry_identity_matches WHERE run_id = ? AND detail_status = 'FEDERAL_ENTITY_CONFIRMED'", (run["run_id"],)).fetchone()[0]
        if not cases or len(cases) != expected:
            raise ValueError("Audit export lost confirmed outcomes")
        payload = {"schema_version": 1, "entry_identity_run": dict(run), "case_count": len(cases), "cases": cases}
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return payload
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    export_audit(args.db, args.output)
