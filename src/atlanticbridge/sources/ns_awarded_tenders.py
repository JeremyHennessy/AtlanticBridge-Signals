"""Bounded, manual exact-vendor context from Nova Scotia public tender awards.

Use only with a previously verified business legal name. Awards show prior
procurement activity, not an expansion mandate, investment intent, or site choice.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

DATASET_ID = "m6ps-8j6u"
DATASET_URL = "https://data.novascotia.ca/Procurement-and-Contracts/Awarded-Public-Tenders/m6ps-8j6u"
API_URL = "https://data.novascotia.ca/resource/m6ps-8j6u.json"
SOURCE_NAME = "nova_scotia_awarded_public_tenders"
LICENSE_ID = "OGL_NOVA_SCOTIA"
LICENSE_NAME = "Open Government Licence - Nova Scotia"
LICENSE_URL = "https://novascotia.ca/opendata/licence.asp"
ATTRIBUTION = "Contains information licensed under the Open Government Licence – Nova Scotia"
MAX_PAGE_SIZE = 50
MAX_RESPONSE_BYTES = 2_000_000
MAX_TIMEOUT_SECONDS = 30

FIELDS = (
    "tender_id",
    "entity",
    "goods",
    "service",
    "construction",
    "tender_start_date",
    "tender_close_date",
    "awarded_date",
    "awarded_amount",
    "vendor",
)
REQUIRED_TYPES = {
    "tender_id": "text",
    "entity": "text",
    "goods": "text",
    "service": "text",
    "construction": "text",
    "tender_start_date": "calendar_date",
    "tender_close_date": "calendar_date",
    "awarded_date": "calendar_date",
    "awarded_amount": "number",
    "vendor": "text",
}


class SameHostHttpsRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        old, new = urlsplit(req.full_url), urlsplit(newurl)
        if (new.scheme != "https" or new.hostname != old.hostname
                or new.username or new.password or new.port not in (None, 443)):
            raise ValueError("Refusing non-HTTPS or cross-host Nova Scotia redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()


def _validate_vendor_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("Vendor must be a verified business legal name")
    value = " ".join(value.split())
    if not value or len(value) > 200 or any(ord(char) < 32 for char in value):
        raise ValueError("Vendor name is empty or exceeds the reviewed input bound")
    return value


def build_query_url(vendor_name: str, limit: int = 20) -> str:
    vendor_name = _validate_vendor_name(vendor_name)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    escaped = vendor_name.replace("'", "''")
    params = {
        "$select": ",".join(FIELDS),
        "$where": f"upper(vendor) = '{escaped.upper()}'",
        "$order": "awarded_date DESC",
        "$limit": str(limit),
    }
    return API_URL + "?" + urlencode(params)


def _fetch_json(url: str, timeout_seconds: int) -> tuple[list, bytes]:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname != "data.novascotia.ca"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.path != "/resource/m6ps-8j6u.json"):
        raise ValueError("Unapproved Nova Scotia awarded tenders endpoint")
    request = Request(url, headers={"User-Agent": "AtlanticBridge-Signals/0.1",
                                    "Accept": "application/json"})
    opener = build_opener(SameHostHttpsRedirects())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            status = response.status
    except (HTTPError, URLError, TimeoutError) as exc:
        raise ValueError(f"Nova Scotia awarded tenders request failed: {type(exc).__name__}") from None
    if status != 200:
        raise ValueError(f"Nova Scotia awarded tenders returned HTTP {status}")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Nova Scotia awarded tenders response exceeded the 2 MB bound")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Nova Scotia awarded tenders returned invalid JSON at line {exc.lineno}, column {exc.colno}"
        ) from None
    if not isinstance(value, list):
        raise ValueError("Nova Scotia awarded tenders response is not a record list")
    return value, raw


def collect_awarded_tenders_context(
    vendor_name: str,
    *,
    limit: int = 20,
    timeout_seconds: int = 20,
    fetch_json=_fetch_json,
) -> dict:
    vendor_name = _validate_vendor_name(vendor_name)
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_TIMEOUT_SECONDS:
        raise ValueError(f"timeout_seconds must be between 1 and {MAX_TIMEOUT_SECONDS}")
    query_url = build_query_url(vendor_name, limit)
    injected_fetcher = fetch_json is not _fetch_json
    rows, raw = fetch_json(query_url, timeout_seconds)
    if not isinstance(raw, bytes):
        raise ValueError("Nova Scotia API raw response is not bytes")
    if not isinstance(rows, list):
        raise ValueError("Nova Scotia API response is not a record list")
    if len(rows) > limit:
        raise ValueError("Nova Scotia API returned more rows than the requested bound")

    projected = []
    excluded = 0
    for row in rows:
        if not isinstance(row, dict) or not set(FIELDS).issubset(row):
            raise ValueError("Nova Scotia awarded tender record schema changed")
        for field in ("tender_id", "entity", "goods", "service", "construction", "vendor"):
            value = row.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 500):
                raise ValueError(f"Nova Scotia {field} field has an unexpected type or size")
        returned_vendor = row.get("vendor")
        if not isinstance(returned_vendor, str) or _normalize(returned_vendor) != _normalize(vendor_name):
            excluded += 1
            continue
        for field in ("tender_start_date", "tender_close_date", "awarded_date"):
            value = row.get(field)
            if value is None:
                continue
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError(f"Nova Scotia {field} has an unexpected type or size")
            try:
                if "T" in value or " " in value:
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                else:
                    date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"Nova Scotia {field} is not a valid ISO date") from None
        amount = row.get("awarded_amount")
        # Socrata metadata declares number, while live JSON may serialize it as text.
        # Validate numeric content but retain the exact source value.
        if amount is not None:
            if isinstance(amount, bool) or not isinstance(amount, (int, float, str)):
                raise ValueError("Nova Scotia awarded tender amount has an unexpected JSON type")
            if isinstance(amount, str):
                if not amount or len(amount) > 128:
                    raise ValueError("Nova Scotia awarded tender amount has an unexpected size")
                numeric_text = amount.strip().replace("$", "").replace(",", "")
                try:
                    parsed_amount = Decimal(numeric_text)
                except InvalidOperation:
                    raise ValueError("Nova Scotia awarded tender amount is not numeric") from None
                if not parsed_amount.is_finite():
                    raise ValueError("Nova Scotia awarded tender amount is not finite")
        projected.append({field: row.get(field) for field in FIELDS})

    return {
        "schema_version": 1,
        "source": SOURCE_NAME,
        "dataset_id": DATASET_ID,
        "dataset_url": DATASET_URL,
        "api_url": query_url,
        "source_license_id": LICENSE_ID,
        "source_license": LICENSE_NAME,
        "source_license_url": LICENSE_URL,
        "source_attribution": ATTRIBUTION,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "collection_execution": (
            "INJECTED_FETCHER_FIXTURE_OR_REPLAY" if injected_fetcher else "LIVE_HTTP_RESPONSE"
        ),
        "independent_review_status": "NOT_INDEPENDENTLY_VERIFIED",
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "requested_vendor_legal_name": vendor_name,
        "requested_limit": limit,
        "records_returned_by_api": len(rows),
        "records_matching_exact_vendor": len(projected),
        "records_excluded_by_exact_vendor_check": excluded,
        "page_may_be_truncated": len(rows) == limit,
        "coverage": "ONE_EXACT_VENDOR_ONE_PAGE; NOT_AN_ABSENCE_PROOF",
        "interpretation": (
            "An award is evidence of a published procurement relationship only. It does not "
            "establish investment, expansion intent, a new Canadian entry, or site selection."
        ),
        "privacy_note": (
            "Use only for a previously verified business legal name. The source licence excludes "
            "personal information; tender descriptions are not requested or retained. This manual "
            "collector remains non-production pending privacy review."
        ),
        "records": projected,
    }
