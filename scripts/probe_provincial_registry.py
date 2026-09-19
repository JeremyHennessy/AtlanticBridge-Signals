from __future__ import annotations

import json
import re
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

PAGE = "https://ised-isde.canada.ca/cbr-rec/en/search/results?search=Backbase+Canada+Inc."
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


def fetch(url: str) -> tuple[str, str, int]:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urlopen(req, timeout=60) as response:
        return (
            response.geturl(),
            response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            ),
            response.status,
        )


page_url, html, page_status = fetch(PAGE)
base_href = re.search(
    r'<base[^>]+href=["\']([^"\']+)["\']',
    html,
    flags=re.I,
)
doc_base = urljoin(page_url, base_href.group(1) if base_href else "/cbr-rec/")
config_url = urljoin(doc_base, "config.js")
_, config_text, _ = fetch(config_url)

search_match = re.search(
    r'window\.SEARCH_API_URL\s*=\s*"([^"]+)"',
    config_text,
)
if not search_match:
    raise RuntimeError(f"SEARCH_API_URL missing from {config_text!r}")
api_url = search_match.group(1)

bundle_src = re.search(
    r'<script[^>]+type=["\']module["\'][^>]+src=["\']([^"\']+)["\']',
    html,
    flags=re.I,
)
if not bundle_src:
    raise RuntimeError("MRAS module bundle not found")
bundle_url = urljoin(doc_base, bundle_src.group(1))
_, bundle, _ = fetch(bundle_url)


def around(pattern: str, radius: int = 2600, limit: int = 20):
    results = []
    for match in re.finditer(pattern, bundle, flags=re.I):
        start = max(0, match.start() - radius)
        end = min(len(bundle), match.end() + radius)
        snippet = re.sub(r"\s+", " ", bundle[start:end]).strip()
        if snippet not in results:
            results.append(snippet)
        if len(results) >= limit:
            break
    return results


api_error = {}
try:
    fetch(api_url)
except HTTPError as exc:
    api_error = {
        "status": exc.code,
        "reason": str(exc.reason),
        "headers": dict(exc.headers.items()),
        "body": exc.read().decode("utf-8", errors="replace")[:12000],
    }

print(
    json.dumps(
        {
            "api_url": api_url,
            "api_empty_request_error": api_error,
            "jL_search_sites": around(r"jL\.search"),
            "fetch_search_sites": around(r"fetch\(jL\.search"),
            "json_stringify_sites": [
                snippet
                for snippet in around(r"JSON\.stringify", radius=1800, limit=50)
                if "search" in snippet.casefold()
                or "jL" in snippet
                or "jurisdiction" in snippet.casefold()
            ][:20],
            "search_term_sites": around(r"searchTerm", radius=1800),
            "page_size_sites": around(r"pageSize", radius=1800),
            "jurisdiction_sites": around(r"jurisdiction", radius=1800, limit=20),
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
