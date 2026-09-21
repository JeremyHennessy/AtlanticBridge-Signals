from __future__ import annotations

from datetime import date
import unittest

from atlanticbridge.event_time_signals import (
    build_event_time_snapshots,
    cutoff_exclusive,
    evidence_available_before,
)


class EventTimeSignalTests(unittest.TestCase):
    def test_cutoffs_use_first_day_of_anchor_month(self):
        self.assertEqual(cutoff_exclusive("2019-10", 3), date(2019, 7, 1))
        self.assertEqual(cutoff_exclusive("2019-10", 6), date(2019, 4, 1))
        self.assertEqual(cutoff_exclusive("2019-10", 12), date(2018, 10, 1))
        self.assertEqual(cutoff_exclusive("2019-10", 24), date(2017, 10, 1))

    def test_publication_interval_must_end_strictly_before_cutoff(self):
        self.assertTrue(
            evidence_available_before(
                {
                    "publicly_available_date": "2019-06-30",
                    "publicly_available_date_precision": "DAY",
                },
                date(2019, 7, 1),
            )
        )
        self.assertFalse(
            evidence_available_before(
                {
                    "publicly_available_date": "2019-07-01",
                    "publicly_available_date_precision": "DAY",
                },
                date(2019, 7, 1),
            )
        )
        self.assertFalse(
            evidence_available_before(
                {
                    "publicly_available_date": "2019",
                    "publicly_available_date_precision": "YEAR",
                },
                date(2019, 7, 1),
            )
        )

    def test_missing_evidence_never_becomes_absent_without_complete_coverage(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "ENTRANT",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {
            "sources": [
                {"signal_family": "S", "status": "UNVERIFIED"}
            ]
        }
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={"coverage": [], "records": []},
        )
        self.assertTrue(all(
            row["state"] == "UNKNOWN_UNVERIFIED_COVERAGE"
            for row in payload["snapshots"]
        ))

    def test_complete_coverage_allows_absence(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "CONTROL",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {"sources": [{"signal_family": "S", "status": "ENABLED"}]}
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "COMPLETE_EXACT_ALIAS_HISTORY",
                    }
                ],
                "records": [],
            },
        )
        self.assertTrue(all(
            row["state"] == "ABSENT_WITH_PROVEN_COVERAGE"
            for row in payload["snapshots"]
        ))

    def test_presence_only_known_gap_never_allows_absence(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "CONTROL",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {
            "sources": [
                {
                    "signal_family": "S",
                    "status": "PRESENCE_ONLY_KNOWN_COVERAGE_GAP",
                }
            ]
        }
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "PRESENCE_ONLY_KNOWN_GAP",
                    }
                ],
                "records": [],
            },
        )
        self.assertTrue(all(
            row["state"] == "UNKNOWN_UNVERIFIED_COVERAGE"
            for row in payload["snapshots"]
        ))

    def test_presence_is_usable_even_when_absence_coverage_is_unproven(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "ENTRANT",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {
            "sources": [
                {
                    "signal_family": "S",
                    "status": "PRESENCE_ONLY_KNOWN_COVERAGE_GAP",
                }
            ]
        }
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "PRESENCE_ONLY_KNOWN_GAP",
                    }
                ],
                "records": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "publicly_available_date": "2010-01-01",
                        "publicly_available_date_precision": "DAY",
                        "evidence_id": "x",
                    }
                ],
            },
        )
        self.assertTrue(all(
            row["state"] == "PRESENT"
            for row in payload["snapshots"]
        ))

    def test_bounded_explicit_absence_coverage_allows_absence(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "CONTROL",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {
            "sources": [
                {"signal_family": "S", "status": "ENABLED"}
            ]
        }
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "COMPLETE_BOUNDED_HISTORY",
                        "absence_coverage_proven": True,
                        "coverage_start_date": "2012-02-03",
                        "coverage_end_exclusive": "2026-09-20",
                    }
                ],
                "records": [],
            },
        )
        self.assertTrue(all(
            row["state"] == "ABSENT_WITH_PROVEN_COVERAGE"
            and row["absence_coverage_proven"]
            for row in payload["snapshots"]
        ))

    def test_bounded_coverage_before_source_start_fails_closed(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "CONTROL",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2013-01",
                    "identity_confidence": "HIGH",
                    "foreign_signal_identity_eligible": True,
                }
            ],
        }
        semantics = {
            "sources": [
                {"signal_family": "S", "status": "ENABLED"}
            ]
        }
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "COMPLETE_BOUNDED_HISTORY",
                        "absence_coverage_proven": True,
                        "coverage_start_date": "2012-02-03",
                        "coverage_end_exclusive": "2026-09-20",
                    }
                ],
                "records": [],
            },
        )
        states_by_offset = {
            row["offset_months"]: row["state"]
            for row in payload["snapshots"]
        }
        self.assertEqual(
            states_by_offset[24],
            "UNKNOWN_UNVERIFIED_COVERAGE",
        )

    def test_unresolved_identity_fails_closed_even_with_source_coverage(self):
        entities = {
            "cutoff_rule": "test",
            "entities": [
                {
                    "entity_id": "e",
                    "role": "ENTRANT",
                    "candidate_outcome_id": "c",
                    "anchor_month": "2020-01",
                    "identity_confidence": "LOW",
                    "foreign_signal_identity_eligible": False,
                }
            ],
        }
        semantics = {"sources": [{"signal_family": "S", "status": "ENABLED"}]}
        payload = build_event_time_snapshots(
            entities_payload=entities,
            semantics_payload=semantics,
            evidence_payload={
                "coverage": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "coverage_status": "COMPLETE_EXACT_ALIAS_HISTORY",
                    }
                ],
                "records": [
                    {
                        "entity_id": "e",
                        "signal_family": "S",
                        "publicly_available_date": "2010-01-01",
                        "publicly_available_date_precision": "DAY",
                        "evidence_id": "x",
                    }
                ],
            },
        )
        self.assertTrue(all(
            row["state"] == "UNKNOWN_UNVERIFIED_COVERAGE"
            for row in payload["snapshots"]
        ))


if __name__ == "__main__":
    unittest.main()
