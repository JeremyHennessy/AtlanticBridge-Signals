"""Bounded metadata-only schema probe for Nova Scotia awarded tenders."""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DATASET_ID = "m6ps-8j6u"
DATASET_URL = "https://data.novascotia.ca/Procurement-and-Contracts/Awarded-Public-Tenders/m6ps-8j6u"
METADATA_URL = "https://data.novascotia.ca/api/views/m6ps-8j6u.json"
MAX_RESPONSE_BYTES = 2_000_000
TIMEOUT_SECONDS = 20


class SameHostHttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (new.scheme != "https" or new.hostname != old.hostname
                or new.username or new.password or new.port not in (None, 443)):
            raise ValueError("Refusing non-HTTPS or cross-host redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_metadata(url: str = METADATA_URL) -> dict:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "data.novascotia.ca"
            or parsed.path != "/api/views/m6ps-8j6u.json"
            or parsed.username or parsed.password or parsed.port not in (None, 443)):
        raise ValueError("Unapproved Nova Scotia dataset metadata endpoint")
    request = Request(url, headers={"Accept": "application/json",
                                   "User-Agent": "AtlanticBridge-SourceSchemaCheck/1.0"})
    opener = build_opener(SameHostHttpsRedirects())
    try:
        with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Nova Scotia dataset metadata request failed: {type(exc).__name__}") from None
    if status != 200:
        raise ValueError(f"Nova Scotia dataset metadata returned HTTP {status}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Nova Scotia dataset metadata exceeded the 2 MB bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Nova Scotia dataset metadata returned invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from None
    if not isinstance(value, dict):
        raise ValueError("Nova Scotia dataset metadata is not an object")
    return value


def probe_metadata(fetch_json=_fetch_metadata) -> dict:
    value = fetch_json()
    if value.get("id") != DATASET_ID:
        raise ValueError("Nova Scotia dataset ID did not match the reviewed source")
    columns = value.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("Nova Scotia dataset metadata has no columns")
    fields = []
    seen = set()
    for column in columns:
        if not isinstance(column, dict):
            raise ValueError("Nova Scotia dataset column metadata is malformed")
        field_name = column.get("fieldName")
        if not isinstance(field_name, str) or not field_name:
            raise ValueError("Nova Scotia dataset column has no field name")
        if field_name in seen:
            raise ValueError("Nova Scotia dataset metadata contains duplicate fields")
        seen.add(field_name)
        fields.append({
            "field_name": field_name,
            "name": str(column.get("name", "")),
            "type": str(column.get("dataTypeName", "")),
        })
    return {
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "metadata_url": METADATA_URL,
        "title": str(value.get("name", "")),
        "license_id": str(value.get("licenseId", "")),
        "attribution": str(value.get("attribution", "")),
        "last_updated": value.get("rowsUpdatedAt"),
        "columns": fields,
        "records_requested": 0,
    }


if __name__ == "__main__":
    print(json.dumps(probe_metadata(), ensure_ascii=False, sort_keys=True))
