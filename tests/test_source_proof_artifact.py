from __future__ import annotations

import unittest

from scripts.build_source_proof_artifact import (
    MAX_BACKTEST_CUTOFF_EXCLUSIVE,
    normalize_canadabuys,
    normalize_cipo,
    normalize_ted,
)


class SourceProofArtifactTests(unittest.TestCase):
    def test_cipo_drops_collection_clock_but_preserves_source_hashes(self):
        payload = {
            "collected_at": "volatile",
            "source_family": "CIPO_CANADIAN_TRADEMARK",
            "coverage_definition": "coverage",
            "known_coverage_gap": {"application_number": "1799092"},
            "source_metadata": {"dataset_date": "2025-01-28", "sha256": "x"},
            "summary": {"entity_count": 12},
            "coverage": [{"entity_id": "e"}],
            "records": [{"evidence_id": "r", "entity_id": "e", "publicly_available_date": "2020-01-01"}],
        }
        normalized = normalize_cipo(payload)
        self.assertNotIn("collected_at", normalized)
        self.assertEqual(normalized["source_metadata"]["sha256"], "x")
        self.assertEqual(normalized["known_coverage_gap"]["application_number"], "1799092")

    def test_canadabuys_clamps_coverage_and_filters_post_window_records(self):
        payload = {
            "source_family": "CANADABUYS_AWARD",
            "source_definition": "signal",
            "coverage_definition": "coverage",
            "semantic_window": {
                "unique_reference_amendment_keys": 5,
                "exact_reviewed_alias_matches": 1,
            },
            "summary": {"entity_count": 12, "source_file_count": 3},
            "coverage": [
                {
                    "entity_id": "e",
                    "coverage_end_exclusive": "2026-10-01",
                }
            ],
            "records": [
                {"publicly_available_date": "2023-05-31", "evidence_id": "keep"},
                {"publicly_available_date": "2023-06-01", "evidence_id": "drop"},
            ],
        }
        normalized = normalize_canadabuys(payload)
        self.assertEqual(
            normalized["coverage"][0]["coverage_end_exclusive"],
            MAX_BACKTEST_CUTOFF_EXCLUSIVE,
        )
        self.assertEqual(
            [row["evidence_id"] for row in normalized["records"]],
            ["keep"],
        )
        self.assertNotIn("rows_scanned", normalized["summary"])

    def test_ted_uses_exclusive_upper_bound_and_drops_live_control(self):
        payload = {
            "collected_at": "volatile",
            "source_family": "TED_CONTRACT_AWARD",
            "signal_definition": "signal",
            "coverage_definition": "coverage",
            "coverage_window": {
                "start_date": "2012-01-01",
                "end_date": "2023-05-31",
            },
            "summary": {"entity_count": 12},
            "coverage": [
                {
                    "entity_id": "e",
                    "coverage_end_date": "2023-05-31",
                }
            ],
            "query_proof": [{"entity_id": "e", "queries": []}],
            "records": [],
            "live_query_control": {"winner_name": "Siemens AG"},
        }
        normalized = normalize_ted(payload)
        self.assertNotIn("collected_at", normalized)
        self.assertNotIn("live_query_control", normalized)
        self.assertNotIn("coverage_end_date", normalized["coverage"][0])
        self.assertEqual(
            normalized["coverage"][0]["coverage_end_exclusive"],
            MAX_BACKTEST_CUTOFF_EXCLUSIVE,
        )
        self.assertEqual(
            normalized["coverage_window"],
            {
                "start_date": "2012-01-01",
                "end_exclusive": MAX_BACKTEST_CUTOFF_EXCLUSIVE,
            },
        )


if __name__ == "__main__":
    unittest.main()
