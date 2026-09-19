from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://orgbook.gov.bc.ca/api/v4"
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(source-backed commercial research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


def get_json(path: str, params: dict[str, object] | None = None):
    url = BASE + path
    if params:
        url += "?" + urlencode(params)
    req = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": UA,
        },
    )
    with urlopen(req, timeout=60) as response:
        payload = json.load(response)
        return {
            "url": response.geturl(),
            "status": response.status,
            "payload": payload,
        }


autocomplete = get_json(
    "/search/autocomplete",
    {
        "q": "U3 POWER CORP.",
        "inactive": "true",
        "revoked": "true",
    },
)

topic = get_json(
    "/search/topic",
    {
        "q": "BC0772006",
        "inactive": "true",
        "revoked": "true",
        "latest": "false",
    },
)

credential_sets = []
for result in (topic["payload"].get("results") or [])[:3]:
    topic_id = result.get("id")
    if topic_id is None:
        continue
    credential_sets.append(
        get_json(f"/topic/{topic_id}/credential-set")
    )

print(
    json.dumps(
        {
            "base": BASE,
            "autocomplete": autocomplete,
            "topic": topic,
            "credential_sets": credential_sets,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
