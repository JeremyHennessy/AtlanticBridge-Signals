"""Read-only, schema-only probe for the federal Grants and Contributions dataset.

It uses CKAN GET endpoints and requests datastore_search with limit=0. It does
not retrieve, print, or retain grant rows.
"""
from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DATASET_ID = "432527ab-7aac-45b5-81d6-7597107a7013"
API_ROOT = "https://open.canada.ca/data/api/3/action/"
MAX_RESPONSE_BYTES = 1_000_000
MAX_SCHEMA_REQUESTS = 10


class OfficialHttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if (new.scheme != "https" or new.hostname != old.hostname
                or new.username or new.password or new.port not in (None, 443)):
            raise ValueError("Refusing non-official or non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get_json(action: str, params: dict[str, str]) -> dict:
    if action not in {"package_show", "datastore_search"}:
        raise ValueError("Unapproved CKAN action")
    url = API_ROOT + action + "?" + urlencode(params)
    opener = build_opener(OfficialHttpsRedirects())
    request = Request(url, headers={"User-Agent": "AtlanticBridge-SourceSchemaCheck/1.0",
                                    "Accept": "application/json"})
    try:
        with opener.open(request, timeout=20) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Official CKAN {action} request failed: {type(exc).__name__}") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError(f"Official CKAN {action} response exceeded size bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Official CKAN {action} returned invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from None
    if not isinstance(value, dict) or value.get("success") is not True:
        raise ValueError(f"Official CKAN {action} response was unsuccessful")
    return value


def probe_schema(fetch_json=_get_json) -> dict:
    package = fetch_json("package_show", {"id": DATASET_ID})
    details = package.get("result")
    if not isinstance(details, dict) or details.get("id") != DATASET_ID:
        raise ValueError("CKAN metadata did not match the expected dataset")
    resources = details.get("resources")
    if not isinstance(resources, list):
        raise ValueError("CKAN dataset resources were missing")
    candidates = [
        item for item in resources
        if isinstance(item, dict)
        and str(item.get("format", "")).casefold() == "csv"
        and item.get("datastore_active") is True
        and isinstance(item.get("id"), str)
    ]
    if not candidates:
        raise ValueError("No active CSV datastore is available for schema-only verification")
    if len(candidates) > MAX_SCHEMA_REQUESTS:
        raise ValueError("CSV datastore count exceeds the bounded schema-probe cap")

    checked = []
    for resource in candidates:
        result = fetch_json("datastore_search", {"resource_id": resource["id"], "limit": "0"})
        payload = result.get("result")
        if not isinstance(payload, dict) or payload.get("records") not in ([], None):
            raise ValueError("Schema-only request unexpectedly returned data rows")
        fields = payload.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("CKAN datastore returned no field schema")
        normalized = []
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("id"), str):
                raise ValueError("CKAN datastore field schema is malformed")
            normalized.append({"name": field["id"], "type": str(field.get("type", ""))})
        checked.append({
            "resource_id": resource["id"],
            "resource_name": str(resource.get("name", "")),
            "row_count": payload.get("total"),
            "fields": normalized,
            "records_returned": 0,
        })
    return {"dataset_id": DATASET_ID, "resources": checked}


if __name__ == "__main__":
    print(json.dumps(probe_schema(), sort_keys=True))
