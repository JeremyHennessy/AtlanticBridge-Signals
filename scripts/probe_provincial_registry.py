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


def fetch_text(url: str) -> tuple[str, str, int]:
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/javascript,application/json,*/*",
        },
    )
    with urlopen(req, timeout=60) as response:
        return (
            response.geturl(),
            response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            ),
            response.status,
        )


final_url, html, status = fetch_text(URL)
base_match = re.search(r'<base[^>]+href=["\']([^"\']+)["\']', html, flags=re.I)
document_base = (
    urljoin(final_url, base_match.group(1))
    if base_match
    else final_url
)

script_srcs = re.findall(
    r'<script[^>]+src=["\']([^"\']+)["\']',
    html,
    flags=re.I,
)
scripts = [urljoin(document_base, src) for src in script_srcs]

config_url = urljoin(document_base, "config.js")
config_final, config_text, config_status = fetch_text(config_url)

bundle_url = next(
    (
        script_url
        for script_url in scripts
        if "/assets/index-" in script_url
    ),
    None,
)
if not bundle_url:
    raise RuntimeError(f"MRAS application bundle not found: {scripts!r}")

bundle_final, bundle, bundle_status = fetch_text(bundle_url)

config_assignments = {}
for key in (
    "SEARCH_API_URL",
    "LAST_UPDATED_API_URL",
    "EMAIL_API_URL",
    "MAINTENANCE_API_URL",
):
    match = re.search(
        rf"(?:globalThis|window)\.{key}\s*=\s*[\"']([^\"']+)[\"']",
        config_text,
    )
    if match:
        config_assignments[key] = match.group(1)

api_url = config_assignments.get("SEARCH_API_URL", "")

patterns = [
    "jL.search",
    "SEARCH_API_URL",
    "searchTerm",
    "search",
    "pageSize",
    "pageNumber",
    "jurisdiction",
    "status",
    "registrationDate",
    "creationDate",
    "inception",
    "registryId",
    "businessNumber",
    "fetch(jL.search",
    "method:\"POST\"",
    "method:\"GET\"",
]
bundle_snippets = {}
for pattern in patterns:
    matches = []
    for match in re.finditer(re.escape(pattern), bundle, flags=re.I):
        start = max(0, match.start() - 1000)
        end = min(len(bundle), match.end() + 1800)
        snippet = re.sub(r"\s+", " ", bundle[start:end]).strip()
        if snippet not in matches:
            matches.append(snippet)
        if len(matches) >= 10:
            break
    bundle_snippets[pattern] = matches

api_probe = None
if api_url:
    # First test is intentionally a GET without invented query parameters.
    # Its status/body often exposes method/schema requirements without
    # guessing or sending a broad search.
    try:
        api_final, api_text, api_status = fetch_text(api_url)
        api_probe = {
            "requested_url": api_url,
            "final_url": api_final,
            "status": api_status,
            "body_prefix": api_text[:4000],
        }
    except Exception as exc:
        api_probe = {
            "requested_url": api_url,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }

print(
    json.dumps(
        {
            "query_page": {
                "requested_url": URL,
                "final_url": final_url,
                "status": status,
                "html_bytes": len(html.encode("utf-8")),
                "document_base": document_base,
            },
            "config": {
                "url": config_final,
                "status": config_status,
                "bytes": len(config_text.encode("utf-8")),
                "text": config_text[:10000],
                "assignments": config_assignments,
            },
            "bundle": {
                "url": bundle_final,
                "status": bundle_status,
                "bytes": len(bundle.encode("utf-8")),
                "snippets": bundle_snippets,
            },
            "api_probe": api_probe,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
