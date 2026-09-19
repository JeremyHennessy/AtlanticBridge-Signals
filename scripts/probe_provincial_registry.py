from __future__ import annotations

import json
import re
from urllib.parse import quote_plus, urljoin
from urllib.request import Request, urlopen

BASE = "https://ised-isde.canada.ca/cbr-rec/en/search/results"
QUERY = "Backbase Canada Inc."
URL = f"{BASE}?search={quote_plus(QUERY)}"
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)

req = Request(URL, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
with urlopen(req, timeout=60) as response:
    html = response.read().decode(
        response.headers.get_content_charset() or "utf-8",
        errors="replace",
    )
    final_url = response.geturl()
    status = response.status

scripts = [
    urljoin(final_url, src)
    for src in re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
]

patterns = [
    "Backbase",
    "search",
    "api",
    "ajax",
    "fetch(",
    "registry",
    "jurisdiction",
    "inception",
    "incorpor",
    "businessNumber",
    "entity",
    "results",
]
snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), html, flags=re.I):
        start = max(0, match.start() - 500)
        end = min(len(html), match.end() + 900)
        snippet = re.sub(r"\s+", " ", html[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 8:
            break
    snippets[pattern] = matches

linked = {}
for script_url in scripts:
    if not any(token in script_url.lower() for token in ("search", "app", "main", "bundle", "cbr", "mras")):
        continue
    try:
        with urlopen(Request(script_url, headers={"User-Agent": UA}), timeout=60) as response:
            js = response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )
    except Exception as exc:
        linked[script_url] = {"error": f"{type(exc).__name__}: {exc}"}
        continue

    js_snippets = {}
    for pattern in (
        "/api/",
        "fetch(",
        "axios",
        "search",
        "registry",
        "jurisdiction",
        "inception",
        "businessNumber",
    ):
        matches = []
        for match in re.finditer(re.escape(pattern), js, flags=re.I):
            start = max(0, match.start() - 650)
            end = min(len(js), match.end() + 1100)
            snippet = re.sub(r"\s+", " ", js[start:end]).strip()
            if snippet not in matches:
                matches.append(snippet)
            if len(matches) >= 6:
                break
        if matches:
            js_snippets[pattern] = matches
    linked[script_url] = {
        "bytes": len(js.encode("utf-8")),
        "snippets": js_snippets,
    }

print(
    json.dumps(
        {
            "query": QUERY,
            "requested_url": URL,
            "final_url": final_url,
            "status": status,
            "html_bytes": len(html.encode("utf-8")),
            "page_title": (
                re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S).group(1).strip()
                if re.search(r"<title>(.*?)</title>", html, flags=re.I | re.S)
                else ""
            ),
            "scripts": scripts,
            "html_snippets": snippets,
            "linked_script_evidence": linked,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
