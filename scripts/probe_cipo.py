from __future__ import annotations

import http.cookiejar
import json
import re
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"

jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))
headers = {
    "User-Agent": (
        "AtlanticBridge-Signals/0.1 "
        "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
    )
}

with opener.open(Request(URL, headers=headers), timeout=60) as response:
    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
search_script = next(
    (urljoin(URL, src) for src in scripts if "/js/search.js" in src),
    None,
)
if not search_script:
    raise RuntimeError("CIPO search.js URL not found")

with opener.open(Request(search_script, headers=headers), timeout=60) as response:
    js = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

patterns = [
    "tm-search-form",
    "serializeJSON",
    "JSON.stringify",
    "window.location",
    "location.href",
    "encodeURIComponent",
    "/srch",
    "searchfield1",
    "maxReturn",
    "$.ajax",
]

snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), js, flags=re.IGNORECASE):
        start = max(0, match.start() - 650)
        end = min(len(js), match.end() + 1100)
        snippet = re.sub(r"\s+", " ", js[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 6:
            break
    snippets[pattern] = matches

print(
    json.dumps(
        {
            "page_url": URL,
            "search_script_url": search_script,
            "search_script_bytes": len(js.encode("utf-8")),
            "snippets": snippets,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
