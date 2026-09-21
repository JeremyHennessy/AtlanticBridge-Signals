from __future__ import annotations

import argparse
from datetime import date, timedelta, timezone, datetime
import hashlib
import json
from pathlib import Path
import unicodedata

from atlanticbridge.event_time_signals import cutoff_exclusive, OFFSETS_MONTHS
from atlanticbridge.sources.ted import search_winner_candidates


SIGNAL_FAMILY = "TED_CONTRACT_AWARD"
COVERAGE_START_DATE = date(2012, 1, 1)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def backtest_end_date(entities_payload: dict[str, object]) -> date:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list) or not entities:
        raise ValueError("entities payload requires non-empty entities list")
    cutoffs = []
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        anchor = str(entity["anchor_month"])
        for offset in OFFSETS_MONTHS:
            cutoffs.append(cutoff_exclusive(anchor, offset))
    return max(cutoffs) - timedelta(days=1)


def collect(
    *,
    entities_payload: dict[str, object],
    coverage_start: date = COVERAGE_START_DATE,
) -> dict[str, object]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entities payload requires entities list")

    end_date = backtest_end_date(entities_payload)
    if end_date < coverage_start:
        raise ValueError("TED coverage window is empty")

    records_by_key: dict[tuple[str, str], dict[str, object]] = {}
    coverage: list[dict[str, object]] = []
    query_proof: list[dict[str, object]] = []

    for entity in entities:
        assert isinstance(entity, dict)
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact_aliases: {entity_id}")

        normalized_aliases = []
        alias_queries = []
        all_queries_complete = True

        for alias in aliases:
            alias = str(alias).strip()
            normalized = normalize_name(alias)
            if not normalized or normalized in normalized_aliases:
                continue
            normalized_aliases.append(normalized)

            result = search_winner_candidates(
                alias,
                coverage_start.isoformat(),
                end_date.isoformat(),
                page_size=250,
                scope="ALL",
                only_latest_versions=False,
                timeout=90,
                attempts=4,
            )

            if len(result.notices) != result.total_notice_count:
                all_queries_complete = False

            exact_notice_count = 0
            nonexact_candidate_count = 0

            for notice in result.notices:
                mention_names = [
                    mention.winner_name
                    for mention in notice.winner_mentions()
                ]
                mention_normalized = {
                    normalize_name(value) for value in mention_names if value
                }
                if normalized not in mention_normalized:
                    nonexact_candidate_count += 1
                    continue

                exact_notice_count += 1
                publication_date = str(notice.publication_date or "")[:10]
                parsed = date.fromisoformat(publication_date)
                if parsed < coverage_start or parsed > end_date:
                    raise ValueError(
                        f"TED result outside requested coverage window: "
                        f"{notice.publication_number} {publication_date}"
                    )

                key = (entity_id, notice.publication_number)
                row = records_by_key.get(key)
                if row is None:
                    material = "\x1f".join(
                        [entity_id, notice.publication_number, publication_date]
                    )
                    row = {
                        "evidence_id": hashlib.sha256(
                            material.encode("utf-8")
                        ).hexdigest(),
                        "entity_id": entity_id,
                        "signal_family": SIGNAL_FAMILY,
                        "publication_number": notice.publication_number,
                        "publicly_available_date": publication_date,
                        "publicly_available_date_precision": "DAY",
                        "publicly_available_date_basis": (
                            "TED notice publication-date returned by the official "
                            "winner-name candidate query, then exact-normalized "
                            "against the reviewed legal-entity alias."
                        ),
                        "winner_names": sorted(set(mention_names)),
                        "matched_aliases": [],
                        "source_url": (
                            notice.english_url
                            or (
                                "https://ted.europa.eu/en/notice/-/detail/"
                                + notice.publication_number
                            )
                        ),
                    }
                    records_by_key[key] = row

                matched_aliases = row["matched_aliases"]
                assert isinstance(matched_aliases, list)
                if alias not in matched_aliases:
                    matched_aliases.append(alias)
                    matched_aliases.sort()

            alias_queries.append(
                {
                    "alias": alias,
                    "normalized_alias": normalized,
                    "query": result.query,
                    "query_hash": result.query_hash,
                    "response_hash": result.response_hash,
                    "candidate_notice_count": result.total_notice_count,
                    "returned_candidate_notice_count": len(result.notices),
                    "exact_notice_count": exact_notice_count,
                    "nonexact_candidate_count": nonexact_candidate_count,
                    "complete": (
                        len(result.notices) == result.total_notice_count
                    ),
                }
            )

        coverage.append(
            {
                "entity_id": entity_id,
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_WINNER_CANDIDATE_QUERY_WITH_EXACT_POSTFILTER_"
                    "SINCE_2012"
                    if all_queries_complete
                    else "INCOMPLETE_QUERY_RETRIEVAL"
                ),
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "absence_coverage_proven": all_queries_complete,
                "coverage_start_date": coverage_start.isoformat(),
                "coverage_end_date": end_date.isoformat(),
                "aliases_normalized": sorted(normalized_aliases),
                "alias_query_count": len(alias_queries),
            }
        )
        query_proof.append(
            {
                "entity_id": entity_id,
                "queries": alias_queries,
            }
        )

    records = sorted(
        records_by_key.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["publication_number"]),
        ),
    )

    return {
        "schema_version": 1,
        "source_family": SIGNAL_FAMILY,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "signal_definition": (
            "At least one TED notice published on or after 2012-01-01 and before "
            "the event-time cutoff where winner-name exactly matches a reviewed "
            "foreign legal-entity alias."
        ),
        "coverage_definition": (
            "Each reviewed alias is used in TED's winner-name field query as a "
            "candidate-retrieval superset over the bounded 2012-01-01 through "
            "Backtest 001 maximum-cutoff window. Every returned winner-name is "
            "then post-filtered to exact normalized legal-entity equality. "
            "Absence is only absence of that exact-alias TED winner signal after "
            "complete retrieval of every alias candidate query."
        ),
        "coverage_window": {
            "start_date": coverage_start.isoformat(),
            "end_date": end_date.isoformat(),
        },
        "summary": {
            "entity_count": len(entities),
            "entity_alias_query_count": sum(
                int(row["alias_query_count"]) for row in coverage
            ),
            "complete_entity_query_sets": sum(
                row["absence_coverage_proven"] is True
                for row in coverage
            ),
            "evidence_record_count": len(records),
            "entities_with_evidence": len(
                {str(row["entity_id"]) for row in records}
            ),
        },
        "coverage": coverage,
        "query_proof": query_proof,
        "records": records,
    }


def live_query_control() -> dict[str, object]:
    result = search_winner_candidates(
        "Siemens AG",
        "2023-01-01",
        "2023-12-31",
        page_size=250,
        scope="ALL",
        only_latest_versions=False,
        timeout=90,
        attempts=4,
    )
    if result.total_notice_count <= 0:
        raise RuntimeError(
            "TED live control query returned no Siemens AG winner notices"
        )
    if len(result.notices) != result.total_notice_count:
        raise RuntimeError("TED live control query was incomplete")

    normalized = normalize_name("Siemens AG")
    exact_notice_count = 0
    nonexact_candidate_count = 0
    for notice in result.notices:
        names = [mention.winner_name for mention in notice.winner_mentions()]
        if normalized in {normalize_name(name) for name in names}:
            exact_notice_count += 1
        else:
            nonexact_candidate_count += 1

    if exact_notice_count <= 0:
        raise RuntimeError(
            "TED live candidate query did not return any exact Siemens AG winner "
            "after post-filtering"
        )

    return {
        "winner_name": "Siemens AG",
        "start_date": "2023-01-01",
        "end_date": "2023-12-31",
        "query": result.query,
        "query_hash": result.query_hash,
        "response_hash": result.response_hash,
        "candidate_notice_count": result.total_notice_count,
        "returned_candidate_notice_count": len(result.notices),
        "exact_notice_count": exact_notice_count,
        "nonexact_candidate_count": nonexact_candidate_count,
        "complete": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--output",
        default="control-output/ted-historical-proof.json",
    )
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    control = live_query_control()
    payload = collect(entities_payload=entities)
    payload["live_query_control"] = control

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(control, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
