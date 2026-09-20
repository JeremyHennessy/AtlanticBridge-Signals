from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from atlanticbridge.curated_identity import (
    apply_curated_identity_review,
    curated_identity_summary,
    ensure_curated_identity_schema,
    seed_curated_identity_queue,
)
from atlanticbridge.foreign_identity import ensure_foreign_identity_schema


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_foreign_identity_schema(conn)
    ensure_curated_identity_schema(conn)
    return conn


def _insert_foreign_run(conn, run_id="foreign-run"):
    conn.execute(
        """
        INSERT INTO foreign_identity_runs (
            run_id,
            entry_identity_run_id,
            target_records,
            queried_investors,
            page_size,
            observed_at
        ) VALUES (?, 'entry-run', 3, 2, 20, '2026-09-19T00:00:00+00:00')
        """,
        (run_id,),
    )


def _insert_resolution(
    conn,
    outcome,
    status,
    investor,
    *,
    confirmed_name="",
    confirmed_jurisdiction="",
):
    conn.execute(
        """
        INSERT INTO foreign_identity_resolutions (
            run_id,
            outcome_record_id,
            certification_month,
            ultimate_control_country,
            ultimate_control_country_iso2,
            investor_name,
            investor_locality,
            investor_role_status,
            canadian_entry_corporation_number,
            resolution_status,
            query_url,
            golden_copy_publish_date,
            total_gleif_results,
            returned_candidate_count,
            exact_name_candidate_count,
            locality_match_candidate_count,
            confirmed_lei,
            confirmed_legal_name,
            confirmed_jurisdiction,
            confirmed_registered_as,
            confirmed_registration_authority_id,
            confirmed_legal_city,
            confirmed_headquarters_city,
            control_country_matches_jurisdiction,
            candidate_snapshot_json,
            direct_parent_status,
            direct_parent_lei,
            direct_parent_legal_name,
            direct_parent_relationship_type,
            direct_parent_exception_reason,
            direct_parent_evidence_url,
            direct_parent_raw_json,
            ultimate_parent_status,
            ultimate_parent_lei,
            ultimate_parent_legal_name,
            ultimate_parent_relationship_type,
            ultimate_parent_exception_reason,
            ultimate_parent_evidence_url,
            ultimate_parent_raw_json,
            observed_at
        ) VALUES (
            'foreign-run', ?, '2025-01', 'Germany', 'DE',
            ?, 'Berlin', 'DISTINCT_INVESTOR_REQUIRES_FOREIGN_RESOLUTION',
            '1234567', ?, 'https://example.test/query', '', 0, 0, 0, 0,
            '', ?, ?, '', '', '', '', 0, '[]',
            'NOT_QUERIED', '', '', '', '', '', '{}',
            'NOT_QUERIED', '', '', '', '', '', '{}',
            '2026-09-19T00:00:00+00:00'
        )
        """,
        (
            outcome,
            investor,
            status,
            confirmed_name,
            confirmed_jurisdiction,
        ),
    )


class CuratedIdentityTests(unittest.TestCase):
    def test_seed_maps_unresolved_states_to_stable_tasks(self):
        conn = _conn()
        _insert_foreign_run(conn)
        _insert_resolution(conn, "a", "NO_RESULTS", "No Match GmbH")
        _insert_resolution(
            conn,
            "b",
            "CANADIAN_VEHICLE_PARENT_UNRESOLVED",
            "Canada Vehicle Inc.",
        )
        _insert_resolution(
            conn,
            "c",
            "CONFIRMED_FOREIGN_NAMED_ENTITY",
            "Resolved B.V.",
            confirmed_name="Resolved B.V.",
            confirmed_jurisdiction="NL",
        )
        conn.commit()

        result = seed_curated_identity_queue(
            conn,
            observed_at="2026-09-19T01:00:00+00:00",
        )
        self.assertEqual(result["active_queue_records"], 2)
        task_counts = {
            row["task_type"]: row["records"]
            for row in result["task_counts"]
        }
        self.assertEqual(task_counts["NAMED_INVESTOR_IDENTITY"], 1)
        self.assertEqual(task_counts["CANADIAN_VEHICLE_PARENT"], 1)

        before = {
            row["queue_id"]
            for row in conn.execute(
                "SELECT queue_id FROM curated_identity_queue"
            )
        }
        seed_curated_identity_queue(
            conn,
            observed_at="2026-09-19T02:00:00+00:00",
        )
        after = {
            row["queue_id"]
            for row in conn.execute(
                "SELECT queue_id FROM curated_identity_queue"
            )
        }
        self.assertEqual(before, after)

    def test_confirm_requires_primary_source_evidence(self):
        conn = _conn()
        _insert_foreign_run(conn)
        _insert_resolution(conn, "a", "NO_RESULTS", "No Match GmbH")
        conn.commit()
        seed_curated_identity_queue(conn)
        queue_id = conn.execute(
            "SELECT queue_id FROM curated_identity_queue"
        ).fetchone()[0]

        payload = {
            "queue_id": queue_id,
            "evidence": [
                {
                    "evidence_type": "OTHER_REFERENCE",
                    "source_url": "https://example.test/reference",
                    "subject_type": "LEGAL_ENTITY",
                    "subject_name": "No Match GmbH",
                    "jurisdiction": "DE",
                }
            ],
            "decision": {
                "state": "CONFIRMED",
                "resolved_subject_type": "LEGAL_ENTITY",
                "resolved_subject_name": "No Match GmbH",
                "resolved_jurisdiction": "DE",
                "basis": "Reference only",
            },
        }
        with self.assertRaisesRegex(ValueError, "primary-source evidence"):
            apply_curated_identity_review(conn, payload)

    def test_primary_evidence_allows_audited_confirmation(self):
        conn = _conn()
        _insert_foreign_run(conn)
        _insert_resolution(conn, "a", "NO_RESULTS", "No Match GmbH")
        conn.commit()
        seed_curated_identity_queue(conn)
        queue_id = conn.execute(
            "SELECT queue_id FROM curated_identity_queue"
        ).fetchone()[0]

        result = apply_curated_identity_review(
            conn,
            {
                "queue_id": queue_id,
                "evidence": [
                    {
                        "evidence_type": "OFFICIAL_REGISTRY",
                        "source_url": "https://registry.example.test/entity/123",
                        "source_title": "Official company record",
                        "source_publisher": "Official Registry",
                        "subject_type": "LEGAL_ENTITY",
                    "subject_name": "No Match GmbH",
                        "jurisdiction": "DE",
                        "identifier_type": "REGISTER_NUMBER",
                        "identifier_value": "HRB123",
                        "evidence_note": "Exact legal-name record.",
                    }
                ],
                "decision": {
                    "state": "CONFIRMED",
                    "resolved_subject_type": "LEGAL_ENTITY",
                "resolved_subject_name": "No Match GmbH",
                    "resolved_jurisdiction": "DE",
                    "resolved_identifier_type": "REGISTER_NUMBER",
                    "resolved_identifier_value": "HRB123",
                    "basis": "Exact official registry legal-name record.",
                },
            },
            observed_at="2026-09-19T03:00:00+00:00",
        )
        self.assertEqual(result["decisions_processed"], 1)
        summary = curated_identity_summary(conn)
        self.assertEqual(summary["confirmed_reviews"], 1)
        self.assertEqual(summary["confirmed_legal_entities"], 1)
        self.assertEqual(summary["confirmed_natural_persons"], 0)
        self.assertEqual(summary["identity_evidence_supported_curated_records"], 1)
        self.assertEqual(summary["modeling_ready_curated_records"], 0)
        self.assertEqual(summary["modeling_readiness_status"], "NOT_EVALUATED")
        row = summary["queue"][0]
        self.assertEqual(row["review_status"], "CONFIRMED")
        self.assertEqual(row["primary_evidence_count"], 1)

    def test_reseed_preserves_review_decision(self):
        conn = _conn()
        _insert_foreign_run(conn)
        _insert_resolution(conn, "a", "NO_RESULTS", "No Match GmbH")
        conn.commit()
        seed_curated_identity_queue(conn)
        queue_id = conn.execute(
            "SELECT queue_id FROM curated_identity_queue"
        ).fetchone()[0]

        apply_curated_identity_review(
            conn,
            {
                "queue_id": queue_id,
                "evidence": [
                    {
                        "evidence_type": "OFFICIAL_COMPANY_SITE",
                        "source_url": "https://company.example.test/legal",
                        "source_title": "Legal notice",
                        "source_publisher": "No Match GmbH",
                        "subject_type": "LEGAL_ENTITY",
                    "subject_name": "No Match GmbH",
                        "jurisdiction": "DE",
                    }
                ],
                "decision": {
                    "state": "CONFIRMED",
                    "resolved_subject_type": "LEGAL_ENTITY",
                "resolved_subject_name": "No Match GmbH",
                    "resolved_jurisdiction": "DE",
                    "basis": "Official legal notice.",
                },
            },
        )

        seed_curated_identity_queue(
            conn,
            observed_at="2026-09-19T04:00:00+00:00",
        )
        status = conn.execute(
            """
            SELECT review_status
            FROM curated_identity_queue
            WHERE queue_id = ?
            """,
            (queue_id,),
        ).fetchone()[0]
        self.assertEqual(status, "CONFIRMED")


    def test_primary_evidence_can_confirm_natural_person_without_modeling_promotion(self):
        conn = _conn()
        _insert_foreign_run(conn)
        _insert_resolution(conn, "person", "NO_RESULTS", "Anastasios Lianos")
        conn.commit()
        seed_curated_identity_queue(conn)
        queue_id = conn.execute(
            "SELECT queue_id FROM curated_identity_queue"
        ).fetchone()[0]

        result = apply_curated_identity_review(
            conn,
            {
                "queue_id": queue_id,
                "evidence": [
                    {
                        "evidence_type": "OFFICIAL_GOVERNMENT_FILING",
                        "source_url": "https://government.example.test/filing/123",
                        "source_title": "Official filing",
                        "source_publisher": "Government authority",
                        "subject_type": "NATURAL_PERSON",
                        "subject_name": "Anastasios Lianos",
                        "evidence_note": "Named individual in official filing.",
                    }
                ],
                "decision": {
                    "state": "CONFIRMED",
                    "resolved_subject_type": "NATURAL_PERSON",
                    "resolved_subject_name": "Anastasios Lianos",
                    "basis": "Official filing identifies the named investor as an individual.",
                },
            },
            observed_at="2026-09-19T05:00:00+00:00",
        )
        self.assertEqual(result["decisions_processed"], 1)
        summary = curated_identity_summary(conn)
        self.assertEqual(summary["confirmed_reviews"], 1)
        self.assertEqual(summary["confirmed_natural_persons"], 1)
        self.assertEqual(summary["confirmed_legal_entities"], 0)
        self.assertEqual(summary["modeling_ready_curated_records"], 0)
        row = summary["queue"][0]
        self.assertEqual(row["resolved_subject_type"], "NATURAL_PERSON")
        self.assertEqual(row["resolved_subject_name"], "Anastasios Lianos")


if __name__ == "__main__":
    unittest.main()
