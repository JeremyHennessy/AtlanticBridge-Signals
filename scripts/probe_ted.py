from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

URL = "https://api.ted.europa.eu/v3/notices/search"
BODY = {
    "query": (
        "publication-date = 20240125 "
        "AND notice-type IN (can-standard can-social can-desg can-tran) "
        "AND winner-selection-status IN (selec-w)"
    ),
    "fields": [
        "publication-number",
        "publication-date",
        "notice-type",
        "notice-title",
        "title-proc",
        "classification-cpv",
        "winner-name",
        "winner-country",
        "winner-identifier",
        "winner-decision-date",
        "tender-value",
        "tender-value-cur",
        "total-value",
        "total-value-cur",
    ],
    "page": 1,
    "limit": 5,
    "scope": "ALL",
    "checkQuerySyntax": True,
    "paginationMode": "PAGE_NUMBER",
    "onlyLatestVersions": False,
}

request = Request(
    URL,
    data=json.dumps(BODY).encode("utf-8"),
    method="POST",
    headers={
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": (
            "AtlanticBridge-Signals/0.1 "
            "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
        ),
    },
)

try:
    with urlopen(request, timeout=60) as response:
        payload = json.load(response)
except HTTPError as exc:
    body = exc.read().decode("utf-8", errors="replace")
    print(json.dumps({"http_status": exc.code, "error_body": body}, indent=2))
    raise

result = {
    "top_level_keys": sorted(payload.keys()),
    "payload": payload,
}
print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
