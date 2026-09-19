from __future__ import annotations

import json
from urllib.request import Request, urlopen

BASE = "https://api.gleif.org/api/v1/lei-records"
LEIS = [
    "984500EFD2E94YM6IC47",
    "2138001R35G3IZJZZC68",
]
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(source-backed commercial research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)

def get(url: str):
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "User-Agent": UA,
        },
    )
    try:
        with urlopen(req, timeout=45) as response:
            return {
                "status": response.status,
                "url": response.geturl(),
                "payload": json.load(response),
            }
    except Exception as exc:
        return {
            "status": None,
            "url": url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

out = {}
for lei in LEIS:
    record = get(f"{BASE}/{lei}")
    result = {"record": record, "followed_relationship_links": {}}
    payload = record.get("payload") or {}
    data = payload.get("data") or {}
    relationships = data.get("relationships") or {}

    for relationship_name in ("direct-parent", "ultimate-parent"):
        relationship = relationships.get(relationship_name) or {}
        links = relationship.get("links") or {}
        for link_type in ("related", "reporting-exception"):
            url = links.get(link_type)
            if url:
                result["followed_relationship_links"][
                    f"{relationship_name}:{link_type}"
                ] = get(url)
    out[lei] = result

print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
