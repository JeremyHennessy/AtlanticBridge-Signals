from __future__ import annotations

import json
import re
from urllib.request import Request, urlopen

URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"

request = Request(
    URL,
    headers={
        "User-Agent": (
            "AtlanticBridge-Signals/0.1 "
            "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
        )
    },
)
with urlopen(request, timeout=60) as response:
    html = response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")

patterns = [
    "ownname",
    "searchfield1",
    "textfield1",
    "maxReturn",
    "domIntlFilter",
    "submitSearch",
    "searchCriteria",
    "query=",
]

snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), html, flags=re.IGNORECASE):
        start = max(0, match.start() - 350)
        end = min(len(html), match.end() + 700)
        snippet = re.sub(r"\s+", " ", html[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 5:
            break
    snippets[pattern] = matches

scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
forms = re.findall(
    r'<form\b([^>]*)>',
    html,
    flags=re.IGNORECASE,
)

print(
    json.dumps(
        {
            "url": URL,
            "html_bytes": len(html.encode("utf-8")),
            "scripts": scripts,
            "form_tags": [re.sub(r"\s+", " ", item).strip() for item in forms],
            "snippets": snippets,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
