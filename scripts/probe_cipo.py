from __future__ import annotations

import http.cookiejar
import json
import re
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

PAGE_URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"
headers = {
    "User-Agent": (
        "AtlanticBridge-Signals/0.1 "
        "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
    )
}
jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))

with opener.open(Request(PAGE_URL, headers=headers), timeout=60) as response:
    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
search_script = next(urljoin(PAGE_URL, src) for src in scripts if "/js/search.js" in src)

with opener.open(Request(search_script, headers=headers), timeout=60) as response:
    js = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

patterns = [
    "pageNum",
    "pageLen",
    "numFound",
    "appNo",
    "st13ApplicationNumber",
    "markName",
    "detail",
    "trademark",
    "href",
    "fetchUrlContextPath",
]

snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), js, flags=re.IGNORECASE):
        start = max(0, match.start() - 700)
        end = min(len(js), match.end() + 1300)
        snippet = re.sub(r"\s+", " ", js[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 8:
            break
    snippets[pattern] = matches

print(
    json.dumps(
        {
            "search_script_url": search_script,
            "snippets": snippets,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
