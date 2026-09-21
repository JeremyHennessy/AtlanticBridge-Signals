from __future__ import annotations

import json
from pathlib import Path

from atlanticbridge.sources.ted import search_awards_exact_winner


def main() -> int:
    result = search_awards_exact_winner(
        "Siemens AG",
        "2023-01-01",
        "2023-12-31",
        page_size=250,
        scope="ALL",
        only_latest_versions=False,
        timeout=90,
        attempts=4,
    )
    rows = []
    for notice in result.notices:
        rows.append(
            {
                "publication_number": notice.publication_number,
                "publication_date": notice.publication_date,
                "winner_name_raw": notice.payload.get("winner-name"),
                "winner_country_raw": notice.payload.get("winner-country"),
                "winner_identifier_raw": notice.payload.get("winner-identifier"),
                "winner_mentions": [
                    {
                        "winner_name": mention.winner_name,
                        "normalized_name": mention.normalized_name,
                        "languages": list(mention.languages),
                        "alignment_status": mention.alignment_status,
                    }
                    for mention in notice.winner_mentions()
                ],
            }
        )
    payload = {
        "query": result.query,
        "total_notice_count": result.total_notice_count,
        "returned_notice_count": len(result.notices),
        "rows": rows,
    }
    output = Path("control-output/ted-siemens-diagnostic.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
