from __future__ import annotations

import json

from atlanticbridge.sources.ted import (
    AWARD_FIELDS,
    AWARD_NOTICE_TYPES,
    _post_json,
)

query = (
    "publication-date = (20240101 <> 20241231) "
    f"AND notice-type IN ({' '.join(AWARD_NOTICE_TYPES)}) "
    "AND winner-selection-status IN (selec-w) "
    'AND winner-name = "Siemens Aktiengesellschaft"'
)

body = {
    "query": query,
    "fields": list(AWARD_FIELDS),
    "page": 1,
    "limit": 10,
    "scope": "ALL",
    "checkQuerySyntax": False,
    "paginationMode": "PAGE_NUMBER",
    "onlyLatestVersions": False,
}

payload = _post_json(body, timeout=60, attempts=3)

print(
    json.dumps(
        {
            "query": query,
            "total_notice_count": payload.get("totalNoticeCount"),
            "returned_notices": len(payload.get("notices") or []),
            "timed_out": payload.get("timedOut"),
            "sample_notices": (payload.get("notices") or [])[:3],
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
