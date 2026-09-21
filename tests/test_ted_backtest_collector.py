from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from atlanticbridge.sources.ted import (
    TEDSearchResult,
    build_winner_candidate_search_body,
    parse_notice,
)


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/collect_backtest_ted.py"
SPEC = importlib.util.spec_from_file_location("collect_backtest_ted", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


def _result(alias: str, winner_names: list[str]) -> TEDSearchResult:
    notices = []
    for index, winner in enumerate(winner_names, start=1):
        notices.append(
            parse_notice(
                {
                    "publication-number": f"N-{index}",
                    "publication-date": "2020-01-15",
                    "notice-type": "can-standard",
                    "winner-name": {"eng": [winner]},
                    "winner-country": ["DEU"],
                    "winner-identifier": [f"ID-{index}"],
                    "winner-decision-date": ["2020-01-01"],
                    "links": {
                        "html": {
                            "ENG": (
                                "https://ted.europa.eu/en/notice/-/detail/"
                                f"N-{index}"
                            )
                        }
                    },
                }
            )
        )
    body = build_winner_candidate_search_body(
        alias,
        "2012-01-01",
        "2023-05-31",
        page=1,
        page_size=250,
    )
    return TEDSearchResult(
        start_date="2012-01-01",
        end_date="2023-05-31",
        scope="ALL",
        page_size=250,
        only_latest_versions=False,
        query=str(body["query"]),
        query_body_json=json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        total_notice_count=len(notices),
        notices=tuple(notices),
    )


class TEDBacktestCollectorTests(unittest.TestCase):
    def test_exact_postfilter_rejects_longer_candidate_name(self):
        entities = {
            "entities": [
                {
                    "entity_id": "e",
                    "anchor_month": "2023-09",
                    "exact_aliases": ["Siemens AG"],
                    "foreign_signal_identity_eligible": True,
                }
            ]
        }
        with patch.object(
            collector,
            "search_winner_candidates",
            return_value=_result(
                "Siemens AG",
                ["Siemens AG", "Siemens AG Österreich"],
            ),
        ):
            payload = collector.collect(entities_payload=entities)

        self.assertEqual(payload["summary"]["evidence_record_count"], 1)
        self.assertEqual(payload["records"][0]["winner_names"], ["Siemens AG"])
        proof = payload["query_proof"][0]["queries"][0]
        self.assertEqual(proof["candidate_notice_count"], 2)
        self.assertEqual(proof["exact_notice_count"], 1)
        self.assertEqual(proof["nonexact_candidate_count"], 1)
        self.assertTrue(proof["complete"])

    def test_complete_zero_candidate_query_proves_narrow_absence(self):
        entities = {
            "entities": [
                {
                    "entity_id": "e",
                    "anchor_month": "2023-09",
                    "exact_aliases": ["No Winner Ltd."],
                    "foreign_signal_identity_eligible": True,
                }
            ]
        }
        with patch.object(
            collector,
            "search_winner_candidates",
            return_value=_result("No Winner Ltd.", []),
        ):
            payload = collector.collect(entities_payload=entities)

        self.assertEqual(payload["records"], [])
        coverage = payload["coverage"][0]
        self.assertTrue(coverage["absence_coverage_proven"])
        self.assertEqual(coverage["coverage_start_date"], "2012-01-01")
        self.assertEqual(coverage["coverage_end_exclusive"], "2023-06-01")

    def test_alias_normalization_deduplicates_equivalent_aliases(self):
        entities = {
            "entities": [
                {
                    "entity_id": "e",
                    "anchor_month": "2023-09",
                    "exact_aliases": [
                        "LINET spol. s.r.o.",
                        "LINET SPOL S R O",
                    ],
                    "foreign_signal_identity_eligible": True,
                }
            ]
        }
        with patch.object(
            collector,
            "search_winner_candidates",
            return_value=_result("LINET spol. s.r.o.", []),
        ) as search:
            payload = collector.collect(entities_payload=entities)

        self.assertEqual(search.call_count, 1)
        self.assertEqual(payload["summary"]["entity_alias_query_count"], 1)


if __name__ == "__main__":
    unittest.main()
