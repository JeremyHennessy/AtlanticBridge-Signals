from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.us.socrata.com/api/catalog/v1"
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(source-backed commercial research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)

QUERIES = [
    "Registry Joint Stock Companies",
    "business registry",
    "corporations",
    "companies",
    "co-operatives registry",
]

results = {}
for query in QUERIES:
    url = BASE + "?" + urlencode(
        {
            "search_context": "data.novascotia.ca",
            "q": query,
            "limit": "100",
        }
    )
    req = Request(url, headers={"Accept": "application/json", "User-Agent": UA})
    with urlopen(req, timeout=60) as response:
        payload = json.load(response)

    rows = []
    for item in payload.get("results") or []:
        resource = item.get("resource") or {}
        metadata = item.get("metadata") or {}
        classification = item.get("classification") or {}
        rows.append(
            {
                "id": resource.get("id"),
                "name": resource.get("name"),
                "description": resource.get("description"),
                "type": resource.get("type"),
                "updatedAt": resource.get("updatedAt"),
                "permalink": item.get("permalink"),
                "domain": metadata.get("domain"),
                "license": metadata.get("license"),
                "attribution": metadata.get("attribution"),
                "tags": classification.get("tags"),
            }
        )
    results[query] = rows

print(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True))
