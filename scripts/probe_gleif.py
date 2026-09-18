from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.gleif.org/api/v1/lei-records"
SAMPLE_LEI = "529900QBVWXMWANH7H45"

def get_json(url: str):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            ),
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)

result = {}

params = {"filter[entity.legalName]": "Siemens AG", "page[size]": "3"}
payload = get_json(BASE + "?" + urlencode(params))
result["search"] = {
    "meta": payload.get("meta", {}),
    "rows": [
        {
            "lei": row.get("id"),
            "attributes_keys": sorted((row.get("attributes") or {}).keys()),
            "relationship_keys": sorted((row.get("relationships") or {}).keys()),
            "links": row.get("links"),
            "entity": (row.get("attributes") or {}).get("entity", {}),
        }
        for row in payload.get("data", [])
    ],
}

relationship_endpoints = [
    f"{BASE}/{SAMPLE_LEI}/direct-parent-relationship",
    f"{BASE}/{SAMPLE_LEI}/ultimate-parent-relationship",
    f"{BASE}/{SAMPLE_LEI}/direct-child-relationships",
]
result["relationships"] = {}
for url in relationship_endpoints:
    key = url.rsplit("/", 1)[-1]
    try:
        rel = get_json(url)
        data = rel.get("data")
        if isinstance(data, list):
            sample = data[:2]
            count = len(data)
        else:
            sample = data
            count = 1 if data else 0
        result["relationships"][key] = {
            "ok": True,
            "count_returned": count,
            "sample": sample,
            "meta": rel.get("meta", {}),
        }
    except Exception as exc:
        result["relationships"][key] = {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
