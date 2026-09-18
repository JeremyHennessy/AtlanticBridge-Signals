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

# Establish the same session/context used by the public search UI.
with opener.open(Request(PAGE_URL, headers=headers), timeout=60) as response:
    page_status = response.status
    response.read(1)

payload = {
    "domIntlFilter": "1",
    "searchfield1": "ownname",
    "textfield1": "Siemens",
    "nicetextfield1": [],
    "cipotextfield1": [],
    "display": "list",
    "maxReturn": "1000",
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
    body = response.read()
    content_type = response.headers.get_content_type()
    response_status = response.status

result = {
    "page_status": page_status,
    "search_status": response_status,
    "content_type": content_type,
    "response_bytes": len(body),
    "cookies": [cookie.name for cookie in jar],
}

if content_type == "application/json":
    data = json.loads(body.decode("utf-8", errors="replace"))
    result["top_level_keys"] = sorted(data.keys())
    result["numFound"] = data.get("numFound")
    for key in ("docs", "results", "documents", "trademarks"):
        value = data.get(key)
        if isinstance(value, list):
            result["result_key"] = key
            result["returned_count"] = len(value)
            result["sample"] = value[:3]
            break
else:
    result["body_prefix"] = body[:1000].decode("utf-8", errors="replace")

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
