"""Bounded, manual context lookup for federal Grants and Contributions awards.

This source provides evidence of a published federal transfer-payment agreement.
It does not establish cash disbursement, Canadian expansion intent, or site
selection. The collector requests a small allowlist and never stores descriptions,
personal fields, or raw response bodies.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DATASET_ID = "432527ab-7aac-45b5-81d6-7597107a7013"
RESOURCE_ID = "1d15a62f-5656-49ad-8c88-f40ce689d831"
DATASET_URL = f"https://open.canada.ca/data/en/dataset/{DATASET_ID}"
API_BASE = "https://open.canada.ca/data/api/3/action/datastore_search"
SOURCE_NAME = "canada_federal_grants_contributions"
SOURCE_LICENSE = "Open Government Licence - Canada"
SOURCE_LICENSE_ID = "ogl-canada"
RECIPIENT_TYPE = "For-profit organization"
MAX_PAGE_SIZE = 50
MAX_RESPONSE_BYTES = 5_000_000
MAX_TIMEOUT_SECONDS = 60
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)
FIELDS = (
    "_id",
    "ref_number",
    "amendment_number",
    "amendment_date",
    "agreement_type",
    "recipient_type",
    "recipient_legal_name",
    "recipient_operating_name",
    "recipient_country",
    "recipient_province",
    "recipient_city",
    "prog_name_en",
    "agreement_number",
    "agreement_value",
    "foreign_currency_type",
    "foreign_currency_value",
    "agreement_start_date",
    "agreement_end_date",
    "coverage",
    "naics_identifier",
    "owner_org_title",
)
REQUIRED_SCHEMA = frozenset(FIELDS)


class OfficialHttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old = urlsplit(req.full_url)
        new = urlsplit(newurl)
        if (
            new.scheme != "https"
            or new.hostname != old.hostname
            or new.username
            or new.password
            or new.port not in (None, 443)
        ):
            raise ValueError("Refusing non-official or non-HTTPS redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _normalize_legal_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _validate_recipient_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Recipient legal name must be text")
    normalized = " ".join(value.split())
    if not normalized or len(normalized) > 200 or any(ord(ch) < 32 for ch in normalized):
        raise ValueError("Recipient legal name is empty or exceeds the reviewed input bound")
    return normalized


def build_query_url(recipient_name: str, limit: int = 20) -> str:
    recipient_name = _validate_recipient_name(recipient_name)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    filters = {
        "recipient_legal_name": recipient_name,
        "recipient_type": RECIPIENT_TYPE,
    }
    params = {
        "resource_id": RESOURCE_ID,
        "limit": str(limit),
        "sort": "amendment_date desc",
        "fields": ",".join(FIELDS),
        "filters": json.dumps(filters, ensure_ascii=False, separators=(",", ":")),
    }
    return API_BASE + "?" + urlencode(params)


def _fetch_json(url: str, timeout_seconds: int) -> tuple[dict, bytes]:
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "open.canada.ca"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or not parsed.path.startswith("/data/api/3/action/datastore_search")
    ):
        raise ValueError("Unapproved Grants and Contributions API endpoint")
    opener = build_opener(OfficialHttpsRedirects())
    request = Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Grants and Contributions API request failed: {type(exc).__name__}") from None
    if status != 200:
        raise ValueError(f"Grants and Contributions API returned HTTP {status}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Grants and Contributions response exceeded the 5 MB bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Grants and Contributions API returned invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from None
    if not isinstance(value, dict) or value.get("success") is not True:
        raise ValueError("Grants and Contributions API response was unsuccessful")
    return value, raw


def collect_grants_context(
    recipient_name: str,
    *,
    limit: int = 20,
    timeout_seconds: int = 20,
    fetch_json=_fetch_json,
) -> dict:
    recipient_name = _validate_recipient_name(recipient_name)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    query_url = build_query_url(recipient_name, limit)
    payload, raw = fetch_json(query_url, timeout_seconds)
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict):
        raise ValueError("Grants and Contributions response is missing result data")
    if result.get("resource_id") != RESOURCE_ID:
        raise ValueError("Grants and Contributions response resource ID changed")
    total = result.get("total")
    rows = result.get("records")
    schema = result.get("fields")
    if type(total) is not int or total < 0 or not isinstance(rows, list):
        raise ValueError("Grants and Contributions response count or records are invalid")
    if total < len(rows) or len(rows) > limit:
        raise ValueError("Grants and Contributions response count is inconsistent")
    if not isinstance(schema, list):
        raise ValueError("Grants and Contributions response schema is missing")
    field_names = {
        item.get("id") for item in schema
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if not REQUIRED_SCHEMA.issubset(field_names):
        missing = sorted(REQUIRED_SCHEMA - field_names)
        raise ValueError("Grants and Contributions schema drift: missing " + ", ".join(missing))

    normalized_target = _normalize_legal_name(recipient_name)
    projected = []
    excluded = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Grants and Contributions API returned a malformed record")
        legal_name = row.get("recipient_legal_name")
        recipient_type = row.get("recipient_type")
        if (
            not isinstance(legal_name, str)
            or _normalize_legal_name(legal_name) != normalized_target
            or recipient_type != RECIPIENT_TYPE
        ):
            excluded += 1
            continue
        projected_row = {name: row.get(name) for name in FIELDS}
        if type(projected_row["_id"]) is not int:
            raise ValueError("Grants and Contributions source row ID is invalid")
        projected.append(projected_row)

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "resource_id": RESOURCE_ID,
        "api_url": query_url,
        "source_license": SOURCE_LICENSE,
        "source_license_id": SOURCE_LICENSE_ID,
        "source_update_frequency": "QUARTERLY",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "requested_recipient_legal_name": recipient_name,
        "requested_recipient_type": RECIPIENT_TYPE,
        "requested_limit": limit,
        "total_count_for_exact_query": total,
        "records_returned_by_api": len(rows),
        "records_matching_exact_recipient": len(projected),
        "records_excluded_by_exact_recipient_check": excluded,
        "api_query_has_more_results": total > len(rows),
        "coverage": "ONE_EXACT_LEGAL_NAME_ONE_PAGE; NOT_AN_ABSENCE_PROOF",
        "interpretation": (
            "Published transfer-payment agreement context. Agreement value is not necessarily "
            "cash disbursed; an award does not establish expansion intent, site selection, "
            "commercial market fit, or current Canadian operating status."
        ),
        "privacy_note": (
            "The request filters to the exact legal recipient and for-profit recipient type, "
            "requests only allowlisted metadata, and omits descriptive free text, postal codes, "
            "business numbers, and all unrequested source fields."
        ),
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "records": projected,
    }


def write_collection(path, collection: dict) -> None:
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(collection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
