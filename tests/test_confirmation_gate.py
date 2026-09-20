from copy import deepcopy
import json
from pathlib import Path
import unittest

from test_curated_identity import _conn, _insert_foreign_run, _insert_resolution
from atlanticbridge.curated_identity import (
    apply_curated_identity_review, seed_curated_identity_queue,
    curated_identity_summary,
    confirmation_evidence_issue,
)


class ConfirmationGateTests(unittest.TestCase):
    def setUp(self):
        self.conn = _conn()
        _insert_foreign_run(self.conn)
        _insert_resolution(self.conn, "one", "NO_RESULTS", "Example GmbH")
        _insert_resolution(self.conn, "parent", "CANADIAN_VEHICLE_PARENT_UNRESOLVED", "Example Canada Inc.")
        self.conn.commit()
        rows = seed_curated_identity_queue(self.conn)["queue"]
        self.ids = {r["task_type"]: r["queue_id"] for r in rows}
        self.payload = {
            "queue_id": self.ids["NAMED_INVESTOR_IDENTITY"],
            "evidence": [{
                "evidence_type": "OFFICIAL_REGISTRY",
                "source_url": "https://registry.example.test/123",
                "subject_type": "LEGAL_ENTITY", "subject_name": "Example GmbH",
                "jurisdiction": "DE", "identifier_type": "REGISTER_NUMBER",
                "identifier_value": "123",
            }],
            "decision": {
                "state": "CONFIRMED", "resolved_subject_type": "LEGAL_ENTITY",
                "resolved_subject_name": "Example GmbH", "resolved_jurisdiction": "DE",
                "resolved_identifier_type": "REGISTER_NUMBER", "resolved_identifier_value": "123",
                "basis": "Reviewed official register entry.",
            },
        }

    def tearDown(self):
        self.conn.close()

    def test_contradictory_identity_fails_and_rolls_back(self):
        for key, wrong in [("subject_name", "Other GmbH"), ("subject_type", "NATURAL_PERSON"),
                           ("jurisdiction", "FR"), ("identifier_value", "999")]:
            with self.subTest(key=key):
                payload = deepcopy(self.payload)
                payload["evidence"][0][key] = wrong
                with self.assertRaises(ValueError):
                    apply_curated_identity_review(self.conn, payload)
                self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM curated_identity_evidence").fetchone()[0], 0)
                self.assertEqual(curated_identity_summary(self.conn)["confirmed_reviews"], 0)

    def test_matching_evidence_for_wrong_queue_subject_is_rejected(self):
        self.payload["decision"]["resolved_subject_name"] = "Other GmbH"
        self.payload["evidence"][0]["subject_name"] = "Other GmbH"
        with self.assertRaisesRegex(ValueError, "queued investor"):
            apply_curated_identity_review(self.conn, self.payload)

    def test_one_matching_source_does_not_hide_conflicting_cited_evidence(self):
        for key, value in [("jurisdiction", "FR"), ("identifier_value", "999")]:
            with self.subTest(key=key):
                payload = deepcopy(self.payload)
                conflicting = deepcopy(payload["evidence"][0])
                conflicting[key] = value
                conflicting["source_url"] += "/conflict"
                payload["evidence"].append(conflicting)
                with self.assertRaisesRegex(ValueError, "contradicts"):
                    apply_curated_identity_review(self.conn, payload)

    def test_committed_reviews_have_explicit_gate_dispositions(self):
        root = Path(__file__).resolve().parents[1]
        baseline = json.loads((root / "reviews/outcome_audit/2026-09-20-baseline-queue.json").read_text())
        queue = {r["queue_id"]: r for r in baseline["queue"]}
        supported, flagged = [], []
        for filename in ("2026-09-19-primary-batch-01.json", "2026-09-19-primary-batch-02.json",
                         "2026-09-20-primary-batch-03.json", "2026-09-20-primary-batch-04.json"):
            path = root / "reviews/curated_identity" / filename
            for item in json.loads(path.read_text()):
                evidence = [{
                    "relationship_type": "", "related_subject_type": "UNKNOWN",
                    "related_subject_name": "", "identifier_type": "", "identifier_value": "", **e,
                } for e in item["evidence"]]
                issue = confirmation_evidence_issue(queue[item["queue_id"]], item["decision"], evidence)
                (flagged if issue else supported).append(item["decision"]["resolved_subject_name"])
        self.assertEqual(len(supported), 10)
        self.assertEqual(set(flagged), {"Bolton Group S.r.l.", "SD2 Engineering Services società tra professionisti a R.L."})

    def test_explicit_primary_alias_and_punctuation_are_supported(self):
        self.payload["decision"]["resolved_subject_name"] = "Example Holding GmbH"
        self.payload["evidence"][0].update(
            subject_name="Example Holding GmbH", relationship_type="SAME_LEGAL_ENTITY_AS",
            related_subject_type="LEGAL_ENTITY", related_subject_name="EXAMPLE G.m.b.H.",
        )
        result = apply_curated_identity_review(self.conn, self.payload)
        self.assertEqual(result["summary"]["identity_evidence_supported_curated_records"], 1)
        self.assertEqual(result["summary"]["modeling_ready_curated_records"], 0)

    def test_parent_requires_correct_relationship_and_target(self):
        self.payload["queue_id"] = self.ids["CANADIAN_VEHICLE_PARENT"]
        for relationship, child in [("", "Example Canada Inc."), ("SUBSIDIARY_OF", "Example Canada Inc."),
                                    ("ULTIMATE_PARENT_OF", "Other Canada Inc.")]:
            with self.subTest(relationship=relationship, child=child):
                self.payload["evidence"][0].update(
                    relationship_type=relationship, related_subject_type="LEGAL_ENTITY", related_subject_name=child,
                )
                with self.assertRaisesRegex(ValueError, "Parent confirmation"):
                    apply_curated_identity_review(self.conn, self.payload)
        self.payload["evidence"][0].update(relationship_type="ULTIMATE_PARENT_OF", related_subject_name="Example Canada Inc.")
        result = apply_curated_identity_review(self.conn, self.payload)
        self.assertEqual(result["summary"]["identity_evidence_supported_curated_records"], 1)

    def test_existing_evidence_must_be_explicitly_cited(self):
        payload = deepcopy(self.payload)
        payload.pop("decision")
        apply_curated_identity_review(self.conn, payload)
        self.payload["evidence"] = []
        with self.assertRaisesRegex(ValueError, "cited primary-source"):
            apply_curated_identity_review(self.conn, self.payload)
        evidence_id = self.conn.execute("SELECT evidence_id FROM curated_identity_evidence").fetchone()[0]
        self.payload["evidence_ids"] = [evidence_id]
        result = apply_curated_identity_review(self.conn, self.payload)
        self.assertEqual(result["summary"]["identity_evidence_supported_curated_records"], 1)
        self.payload["queue_id"] = self.ids["CANADIAN_VEHICLE_PARENT"]
        with self.assertRaisesRegex(ValueError, "belong to this queue"):
            apply_curated_identity_review(self.conn, self.payload)

    def test_entire_review_batch_rolls_back_if_second_decision_is_invalid(self):
        second = deepcopy(self.payload)
        second["queue_id"] = self.ids["CANADIAN_VEHICLE_PARENT"]
        with self.assertRaises(ValueError):
            apply_curated_identity_review(self.conn, [self.payload, second])
        self.assertEqual(curated_identity_summary(self.conn)["confirmed_reviews"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM curated_identity_decisions").fetchone()[0], 0)

    def test_reapplying_prior_decision_uses_its_own_citations(self):
        apply_curated_identity_review(self.conn, self.payload)
        later = deepcopy(self.payload)
        later["evidence"][0]["source_url"] += "/new"
        later["decision"]["basis"] = "A later review."
        apply_curated_identity_review(self.conn, later)
        self.conn.execute("UPDATE curated_identity_evidence SET subject_name = 'Other GmbH' WHERE source_url LIKE '%/new'")
        self.conn.commit()
        result = apply_curated_identity_review(self.conn, self.payload)
        self.assertEqual(result["summary"]["identity_evidence_supported_curated_records"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM curated_identity_decisions").fetchone()[0], 2)

    def test_legacy_unsupported_decision_is_flagged_without_overwrite(self):
        apply_curated_identity_review(self.conn, self.payload)
        self.conn.execute("UPDATE curated_identity_evidence SET subject_name = 'Other GmbH'")
        self.conn.commit()
        before = [tuple(r) for r in self.conn.execute("SELECT * FROM curated_identity_decisions")]
        summary = curated_identity_summary(self.conn)
        self.assertEqual(summary["confirmed_reviews"], 1)
        self.assertEqual(summary["identity_evidence_supported_curated_records"], 0)
        self.assertEqual(summary["confirmations_requiring_evidence_review"], 1)
        self.assertEqual(before, [tuple(r) for r in self.conn.execute("SELECT * FROM curated_identity_decisions")])


if __name__ == "__main__":
    unittest.main()
