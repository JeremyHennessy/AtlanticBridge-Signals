from __future__ import annotations

import json
from urllib.request import Request, urlopen

BASE = "https://api.gleif.org/api/v1/lei-records"
LEIS = [
    "984500EFD2E94YM6IC47",
    "2138001R35G3IZJZZC68",
]
RELATIONSHIPS = [
    "direct-parent-relationship",
    "ultimate-parent-relationship",
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
    out[lei] = {
        "record": get(f"{BASE}/{lei}"),
        "relationships": {
            relationship: get(f"{BASE}/{lei}/{relationship}")
            for relationship in RELATIONSHIPS
        },
    }

print(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True))
