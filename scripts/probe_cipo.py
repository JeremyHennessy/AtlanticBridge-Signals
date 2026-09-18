from __future__ import annotations

import http.cookiejar
import json
import re
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

payload = {
    "domIntlFilter": "1",
    "searchfield1": "ownname",
    "textfield1": "Siemens",
    "nicetextfield1": [],
    "cipotextfield1": [],
    "display": "list",
    "maxReturn": "10",
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
    search = json.load(response)

docs = search.get("docs") or []
if not docs:
    raise RuntimeError("No CIPO owner-search results returned")

sample = docs[0]
record_id = str(sample["id"])
DETAIL_URL = f"https://ised-isde.canada.ca/cipo/trademark-search/{record_id}?lang=eng"

with opener.open(Request(DETAIL_URL, headers={**headers, "Referer": PAGE_URL}), timeout=60) as response:
    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
    detail_status = response.status

patterns = [
    "Application number",
    "Filing date",
    "Filed",
    "Registration date",
    "Current owner",
    "Owner",
    "Siemens",
    "2319647",
    "1783639",
    "json",
]

snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), html, flags=re.IGNORECASE):
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 900)
        snippet = re.sub(r"\s+", " ", html[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 6:
            break
    snippets[pattern] = matches

scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)

print(
    json.dumps(
        {
            "search_num_found": search.get("numFound"),
            "sample_search_record": sample,
            "detail_url": DETAIL_URL,
            "detail_status": detail_status,
            "detail_html_bytes": len(html.encode("utf-8")),
            "scripts": scripts,
            "snippets": snippets,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
