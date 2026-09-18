from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://api.gleif.org/api/v1/lei-records"

QUERIES = [
    ("fulltext", {"filter[fulltext]": "Siemens AG", "page[size]": "3"}),
    ("legal_name", {"filter[entity.legalName]": "Siemens AG", "page[size]": "3"}),
]

results = []
for label, params in QUERIES:
    url = BASE + "?" + urlencode(params)
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
    item = {"label": label, "url": url}
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
        item["ok"] = True
        item["meta"] = payload.get("meta", {})
        data = payload.get("data", [])
        item["result_count_returned"] = len(data)
        item["sample"] = []
        for row in data[:3]:
            attrs = row.get("attributes", {})
            entity = attrs.get("entity", {})
            item["sample"].append(
                {
                    "lei": row.get("id"),
                    "legal_name": (entity.get("legalName") or {}).get("name"),
                    "jurisdiction": entity.get("jurisdiction"),
                    "status": entity.get("status"),
                    "category": entity.get("category"),
                    "registered_as": entity.get("registeredAs"),
                    "registered_at": entity.get("registeredAt", {}),
                }
            )
    except Exception as exc:
        item["ok"] = False
        item["error_type"] = type(exc).__name__
        item["error"] = str(exc)
    results.append(item)

print(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True))
