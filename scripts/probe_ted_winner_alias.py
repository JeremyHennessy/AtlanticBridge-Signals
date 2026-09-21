from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

from atlanticbridge.sources.ted import (
    AWARD_FIELDS,
    AWARD_NOTICE_TYPES,
    _post_json,
    parse_notice,
)


START_DATE = "2012-02-03"
END_DATE = "2023-05-31"
PAGE_SIZE = 250
MAX_PAGE_RESULTS = 15_000
SIGNAL_FAMILY = "TED_EXACT_WINNER_ALIAS"


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def escape_query_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_query(alias: str) -> str:
    notice_types = " ".join(AWARD_NOTICE_TYPES)
    return (
        "publication-date = (20120203 <> 20230531) "
        f"AND notice-type IN ({notice_types}) "
        "AND winner-selection-status IN (selec-w) "
        f'AND winner-name ~ "{escape_query_text(alias)}"'
    )


def search_alias(alias: str) -> dict[str, object]:
    query = build_query(alias)
    notices = []
    total_notice_count = None
    page = 1
    timed_out = False

    while True:
        body = {
            "query": query,
            "fields": list(AWARD_FIELDS),
            "page": page,
            "limit": PAGE_SIZE,
            "scope": "ALL",
            "checkQuerySyntax": False,
            "paginationMode": "PAGE_NUMBER",
            "onlyLatestVersions": False,
        }
        payload = _post_json(body, timeout=90, attempts=4)
        if payload.get("timedOut") is True:
            timed_out = True
            break

        raw_notices = payload.get("notices") or []
        if not isinstance(raw_notices, list):
            raise ValueError("TED notices response is not a list")

        if total_notice_count is None:
            total_notice_count = int(payload.get("totalNoticeCount") or 0)
            if total_notice_count > MAX_PAGE_RESULTS:
                raise ValueError(
                    f"TED alias query exceeds PAGE_NUMBER cap: {alias!r} "
                    f"{total_notice_count}"
                )

        for raw in raw_notices:
            if not isinstance(raw, dict):
                raise ValueError("TED notice row is not an object")
            notices.append(parse_notice(raw))

        if not raw_notices:
            break
        if len(notices) >= total_notice_count:
            break
        if len(raw_notices) < PAGE_SIZE:
            break
        page += 1

    if total_notice_count is None:
        total_notice_count = 0

    complete = (
        not timed_out
        and total_notice_count <= MAX_PAGE_RESULTS
        and len(notices) == total_notice_count
    )

    normalized_alias = normalize_name(alias)
    exact_matches = []
    surfaced_names = set()
    for notice in notices:
        for mention in notice.winner_mentions():
            surfaced_names.add(mention.winner_name)
            if mention.normalized_name == normalized_alias:
                exact_matches.append(
                    {
                        "publication_number": notice.publication_number,
                        "publication_date": notice.publication_date,
                        "winner_name": mention.winner_name,
                        "winner_country": mention.winner_country,
                        "winner_identifier": mention.winner_identifier,
                        "alignment_status": mention.alignment_status,
                        "source_url": notice.english_url,
                    }
                )

    material = "\n".join(
        sorted(
            f"{item['publication_number']}\x1f{item['winner_name']}"
            for item in exact_matches
        )
    )
    return {
        "alias": alias,
        "normalized_alias": normalized_alias,
        "query": query,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        "total_notice_count": total_notice_count,
        "returned_notice_count": len(notices),
        "page_count": page,
        "timed_out": timed_out,
        "complete": complete,
        "surfaced_winner_names": sorted(surfaced_names),
        "exact_match_count": len(exact_matches),
        "exact_match_sha256": hashlib.sha256(
            material.encode("utf-8")
        ).hexdigest(),
        "exact_matches": exact_matches,
    }


def collect(entities_payload: dict[str, object]) -> dict[str, object]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entities payload requires entities list")

    entity_results = []
    total_queries = 0
    all_exact_matches = []

    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity row must be object")
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact_aliases: {entity_id}")

        unique_aliases = []
        seen = set()
        for alias in aliases:
            text = str(alias).strip()
            normalized = normalize_name(text)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique_aliases.append(text)

        alias_results = []
        for alias in unique_aliases:
            result = search_alias(alias)
            total_queries += 1
            alias_results.append(result)
            for match in result["exact_matches"]:
                all_exact_matches.append(
                    {
                        "entity_id": entity_id,
                        "alias": alias,
                        **match,
                    }
                )

        entity_complete = all(
            bool(row["complete"]) for row in alias_results
        )
        entity_results.append(
            {
                "entity_id": entity_id,
                "role": entity["role"],
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "identity_confidence": entity["identity_confidence"],
                "alias_query_count": len(alias_results),
                "all_alias_queries_complete": entity_complete,
                "exact_match_count": sum(
                    int(row["exact_match_count"])
                    for row in alias_results
                ),
                "aliases": alias_results,
            }
        )

    exact_key_material = "\n".join(
        sorted(
            f"{row['entity_id']}\x1f{row['publication_number']}\x1f"
            f"{normalize_name(str(row['winner_name']))}"
            for row in all_exact_matches
        )
    )

    return {
        "schema_version": 1,
        "signal_family": SIGNAL_FAMILY,
        "source": "TED Search API v3",
        "window": {
            "start_date": START_DATE,
            "end_date_inclusive": END_DATE,
        },
        "signal_definition": (
            "A TED contract-award notice published in the fixed historical "
            "window returns a winner-name whose normalized value exactly equals "
            "one of the reviewed foreign legal-entity aliases."
        ),
        "absence_rule": (
            "Absence is permitted only when every reviewed alias query for the "
            "entity is complete, not timed out, below the 15,000 PAGE_NUMBER "
            "cap, and all reported notices were retrieved."
        ),
        "summary": {
            "entity_count": len(entity_results),
            "alias_query_count": total_queries,
            "entities_with_complete_alias_queries": sum(
                bool(row["all_alias_queries_complete"])
                for row in entity_results
            ),
            "entities_with_exact_match": sum(
                int(row["exact_match_count"]) > 0
                for row in entity_results
            ),
            "exact_match_count": len(all_exact_matches),
            "exact_match_key_sha256": hashlib.sha256(
                exact_key_material.encode("utf-8")
            ).hexdigest(),
        },
        "entities": entity_results,
        "exact_matches": sorted(
            all_exact_matches,
            key=lambda row: (
                str(row["entity_id"]),
                str(row["publication_date"]),
                str(row["publication_number"]),
            ),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--output",
        default="control-output/ted-winner-proof.json",
    )
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    payload = collect(entities)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    for row in payload["entities"]:
        print(
            json.dumps(
                {
                    "entity_id": row["entity_id"],
                    "complete": row["all_alias_queries_complete"],
                    "exact_match_count": row["exact_match_count"],
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
