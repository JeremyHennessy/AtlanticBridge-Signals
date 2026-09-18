from __future__ import annotations

import http.cookiejar
import json
from urllib.request import HTTPCookieProcessor, Request, build_opener

PAGE_URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"
SEARCH_URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch"

headers = {
    "User-Agent": (
        "AtlanticBridge-Signals/0.1 "
        "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
    )
}
jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))
with opener.open(Request(PAGE_URL, headers=headers), timeout=60) as response:
    response.read()

def search(term: str) -> dict:
    payload = {
        "domIntlFilter": "1",
        "searchfield1": "ownname",
        "textfield1": term,
        "nicetextfield1": [],
        "cipotextfield1": [],
        "display": "list",
        "maxReturn": "5000",
    }
    request = Request(
        SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            **headers,
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Referer": PAGE_URL,
        },
    )
    with opener.open(request, timeout=60) as response:
        data = json.load(response)
    return {
        "term": term,
        "numFound": data.get("numFound"),
        "numReturned": data.get("numReturned"),
        "returned_count": len(data.get("docs") or []),
        "sample": [
            {
                "id": row.get("id"),
                "appNo": row.get("appNo"),
                "markName": row.get("markName"),
                "statusDesc": row.get("statusDesc"),
            }
            for row in (data.get("docs") or [])[:5]
        ],
    }

print(
    json.dumps(
        {
            "unquoted": search("Siemens Aktiengesellschaft"),
            "quoted": search('"Siemens Aktiengesellschaft"'),
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
