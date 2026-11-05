"""Bounded context collector for official BODACC commercial notices.

This collector is deliberately one SIREN, one date-bounded page, at most 100
records per run. It stores only identifiers, publication metadata, event
taxonomy, the official notice URL, and source provenance; it never persists
the full source payload or the notice's free-text/person fields.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API_BASE = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.0"
DATASET_ID = "annonces-commerciales"
DATASET_URL = "https://www.data.gouv.fr/datasets/bodacc"
SOURCE_NAME = "bodacc_commercial_notices"
SOURCE_LICENSE = "Etalab Open Licence 2.0"
SOURCE_LICENSE_ID = "etalab-2.0"
SOURCE_LICENSE_URL = "https://www.data.gouv.fr/pages/legal/licences/etalab-2-0"
SOURCE_ATTRIBUTION = (
    "Source: bodacc.fr / Direction de l’information légale et administrative (DILA), "
    "annonces-commerciales dataset; Etalab Open Licence 2.0. "
    "Source-file name: unknown; source-file date: unknown "
    "(not supplied by the bounded API response)."
)
MAX_PAGE_SIZE = 100
MAX_RESPONSE_BYTES = 5_000_000
API_FIELDS = (
    "id",
    "publicationavis",
    "dateparution",
    "familleavis",
    "familleavis_lib",
    "typeavis",
    "typeavis_lib",
    "registre",
    "url_complete",
)
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


@dataclass(frozen=True, slots=True)
class BODACCNotice:
    record_id: str
    siren: str
    registry_source_type: str
    publication_date: str
    bulletin_edition: str
    notice_type: str
    notice_family_code: str
    notice_family_label: str
    official_notice_url: str
    publication_age_days: int
    publication_freshness: str


@dataclass(frozen=True, slots=True)
class BODACCCollection:
    source: str
    dataset_id: str
    dataset_url: str
    api_url: str
    source_license: str
    source_license_id: str
    retrieved_at: str
    collection_execution: str
    independent_review_status: str
    requested_siren: str
    requested_since: str
    requested_limit: int
    total_count_for_query: int
    records_returned_by_api: int
    records_matching_exact_siren: int
    records_excluded_by_exact_siren_check: int
    api_query_has_more_results: bool
    coverage: str
    freshness_note: str
    response_sha256: str
    records: tuple[BODACCNotice, ...]

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "dataset_id": self.dataset_id,
            "dataset_url": self.dataset_url,
            "api_url": self.api_url,
            "source_license": self.source_license,
            "source_license_id": self.source_license_id,
            "source_license_url": SOURCE_LICENSE_URL,
            "source_attribution": SOURCE_ATTRIBUTION,
            # Neither notice publication nor retrieval time proves a source-file date.
            "source_file_name": None,
            "source_file_date": None,
            "retrieved_at": self.retrieved_at,
            "collection_execution": self.collection_execution,
            "independent_review_status": self.independent_review_status,
            "requested_siren": self.requested_siren,
            "requested_since": self.requested_since,
            "requested_limit": self.requested_limit,
            "total_count_for_query": self.total_count_for_query,
            "records_returned_by_api": self.records_returned_by_api,
            "records_matching_exact_siren": self.records_matching_exact_siren,
            "records_excluded_by_exact_siren_check": self.records_excluded_by_exact_siren_check,
            "api_query_has_more_results": self.api_query_has_more_results,
            "registry_source_types": sorted({item.registry_source_type for item in self.records}),
            "coverage": self.coverage,
            "freshness_note": self.freshness_note,
            "response_sha256": self.response_sha256,
            "records": [
                {
                    "record_id": item.record_id,
                    "siren": item.siren,
                    "registry_source_type": item.registry_source_type,
                    "publication_date": item.publication_date,
                    "bulletin_edition": item.bulletin_edition,
                    "notice_type": item.notice_type,
                    "notice_family_code": item.notice_family_code,
                    "notice_family_label": item.notice_family_label,
                    "official_notice_url": item.official_notice_url,
                    "publication_age_days": item.publication_age_days,
                    "publication_freshness": item.publication_freshness,
                }
                for item in self.records
            ],
            "interpretation_limit": (
                "French corporate notice context only; not evidence of Canadian activity, "
                "Canada-directed expansion, an uncommitted mandate, investment intent, or market fit."
            ),
        }


def _validate_inputs(siren: str, since: str, limit: int) -> date:
    if not isinstance(siren, str) or not re.fullmatch(r"[0-9]{9}", siren):
        raise ValueError("siren must be exactly nine digits")
    if not isinstance(since, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", since):
        raise ValueError("since must be an ISO date (YYYY-MM-DD)")
    try:
        since_date = date.fromisoformat(since)
    except ValueError as exc:
        raise ValueError("since must be an ISO date (YYYY-MM-DD)") from exc
    if since_date.isoformat() != since:
        raise ValueError("since must be an ISO date (YYYY-MM-DD)")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return since_date


def build_query_url(siren: str, since: str, limit: int = 50) -> str:
    """Build the fixed, one-page query; caller values are validated before interpolation."""
    _validate_inputs(siren, since, limit)
    where = f'search(registre, "{siren}") AND dateparution >= date\'{since}\''
    params = {
        "select": ",".join(API_FIELDS),
        "where": where,
        "order_by": "dateparution DESC",
        "limit": str(limit),
        "offset": "0",
    }
    return (
        f"{API_BASE}/catalog/datasets/{DATASET_ID}/records?"
        f"{urlencode(params)}"
    )


def _fetch_payload(url: str, timeout: int) -> tuple[dict, str]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    )
    with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("BODACC response exceeded the 5 MB safety cap")
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("BODACC API returned invalid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("BODACC API response must be a JSON object")
    return payload, digest


_ORIGINAL_FETCH_PAYLOAD = _fetch_payload


def _registry_sirens(value: object) -> set[str]:
    """Extract only documented plain or space-grouped ASCII SIRENs."""
    if isinstance(value, bool) or value is None:
        raise ValueError(f"BODACC registre field has an unsupported {type(value).__name__} type")
    values = value if isinstance(value, list) else [value]
    found: set[str] = set()
    for item in values:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ValueError(f"BODACC registre list contains an unsupported {type(item).__name__} value")
        text = str(item).strip()
        if re.fullmatch(r"[0-9]{9}", text):
            found.add(text)
            continue
        if re.fullmatch(r"[0-9]{3}(?:[ \t]+[0-9]{3}){2}", text):
            found.add(re.sub(r"[ \t]", "", text))
            continue
        if isinstance(value, str) and "," in value and isinstance(item, str):
            # A scalar may publish both the compact and space-grouped SIREN.
            parts = [part.strip() for part in value.split(",")]
            if all(
                re.fullmatch(r"[0-9]{9}", part)
                or re.fullmatch(r"[0-9]{3}(?:[ \t]+[0-9]{3}){2}", part)
                for part in parts
            ):
                for part in parts:
                    found.add(re.sub(r"[ \t]", "", part))
                return found
        raise ValueError("BODACC registre field has an unsupported identifier format")
    return found


def _nonempty_text(fields: dict, name: str) -> str:
    value = fields.get(name)
    if value is None:
        return ""
    if not isinstance(value, (str, int)):
        raise ValueError(f"BODACC field {name!r} has an unexpected type")
    return str(value).strip()


def _notice_url(value: str, record_id: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("BODACC notice URL has an invalid authority") from exc
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "www.bodacc.fr"
        or port not in (None, 443)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path != "/pages/annonces-commerciales-detail/"
        or parsed.fragment
        or query.get("q.id") != [f"id:{record_id}"]
    ):
        raise ValueError("BODACC notice URL is not a canonical official detail URL")
    return value


class _NoRedirect(HTTPRedirectHandler):
    """Reject redirects so a single collector request cannot follow another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _parse_records(
    rows: object,
    *,
    siren: str,
    retrieved_date: date,
    limit: int,
    since_date: date,
) -> tuple[tuple[BODACCNotice, ...], int]:
    if not isinstance(rows, list):
        raise ValueError("BODACC response is missing its records array")
    if len(rows) > limit:
        raise ValueError("BODACC response exceeded the requested page limit")
    records: list[BODACCNotice] = []
    by_id: dict[str, BODACCNotice] = {}
    excluded = 0
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("record"), dict):
            raise ValueError("BODACC record has an unexpected response shape")
        fields = row["record"].get("fields")
        if not isinstance(fields, dict):
            raise ValueError("BODACC record is missing its fields object")
        record_id = _nonempty_text(fields, "id")
        publication_date_text = _nonempty_text(fields, "dateparution")
        registry_value = fields.get("registre")
        registry_source_type = type(registry_value).__name__
        official_url = _nonempty_text(fields, "url_complete")
        if not record_id or registry_value is None or not publication_date_text or not official_url:
            raise ValueError("BODACC record is missing a required provenance field")
        try:
            published = date.fromisoformat(publication_date_text)
        except ValueError as exc:
            raise ValueError("BODACC dateparution is not an ISO date") from exc
        if published.isoformat() != publication_date_text:
            raise ValueError("BODACC dateparution is not an ISO date")
        if published < since_date:
            raise ValueError("BODACC returned a notice before the requested lower date bound")
        if siren not in _registry_sirens(registry_value):
            excluded += 1
            continue
        age_days = (retrieved_date - published).days
        if age_days < 0:
            freshness = "FUTURE_DATED_REVIEW"
        elif age_days <= 90:
            freshness = "NOTICE_PUBLISHED_WITHIN_90_DAYS"
        else:
            freshness = "NOTICE_PUBLISHED_OVER_90_DAYS_AGO"
        notice = BODACCNotice(
            record_id=record_id,
            siren=siren,
            publication_date=published.isoformat(),
            bulletin_edition=_nonempty_text(fields, "publicationavis"),
            notice_type=_nonempty_text(fields, "typeavis_lib"),
            notice_family_code=_nonempty_text(fields, "familleavis"),
            notice_family_label=_nonempty_text(fields, "familleavis_lib"),
            official_notice_url=_notice_url(official_url, record_id),
            registry_source_type=registry_source_type,
            publication_age_days=age_days,
            publication_freshness=freshness,
        )
        previous = by_id.get(record_id)
        if previous is not None:
            if previous != notice:
                raise ValueError("BODACC returned conflicting copies of one notice ID")
            continue
        by_id[record_id] = notice
        records.append(notice)
    return tuple(records), excluded


def collect_siren_notices(
    siren: str,
    since: str,
    *,
    limit: int = 50,
    timeout: int = 20,
    retrieved_at: datetime | None = None,
    fetch_payload=None,
) -> BODACCCollection:
    """Collect one bounded page for one verified SIREN; never paginates or retries."""
    since_date = _validate_inputs(siren, since, limit)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ValueError("timeout must be a positive whole number of seconds")
    retrieved = retrieved_at or datetime.now(timezone.utc)
    if retrieved.tzinfo is None or retrieved.utcoffset() is None:
        raise ValueError("retrieved_at must include a timezone")
    retrieved = retrieved.astimezone(timezone.utc)
    url = build_query_url(siren, since, limit)
    fetcher = fetch_payload or _fetch_payload
    injected_fetcher = fetcher is not _ORIGINAL_FETCH_PAYLOAD
    payload, response_hash = fetcher(url, timeout)
    rows = payload.get("records")
    total_count = payload.get("total_count")
    if isinstance(total_count, bool) or not isinstance(total_count, int) or total_count < 0:
        raise ValueError("BODACC response is missing a valid total_count")
    if not isinstance(rows, list):
        raise ValueError("BODACC response is missing its records array")
    if total_count < len(rows):
        raise ValueError("BODACC total_count is smaller than the returned records array")
    notices, excluded = _parse_records(
        rows,
        siren=siren,
        retrieved_date=retrieved.date(),
        limit=limit,
        since_date=since_date,
    )
    return BODACCCollection(
        source=SOURCE_NAME,
        dataset_id=DATASET_ID,
        dataset_url=DATASET_URL,
        api_url=url,
        source_license=SOURCE_LICENSE,
        source_license_id=SOURCE_LICENSE_ID,
        retrieved_at=retrieved.isoformat(),
        collection_execution=(
            "INJECTED_FETCHER_FIXTURE_OR_REPLAY" if injected_fetcher else "LIVE_HTTP_RESPONSE"
        ),
        independent_review_status="NOT_INDEPENDENTLY_VERIFIED",
        requested_siren=siren,
        requested_since=since_date.isoformat(),
        requested_limit=limit,
        total_count_for_query=total_count,
        records_returned_by_api=len(rows),
        records_matching_exact_siren=len(notices),
        records_excluded_by_exact_siren_check=excluded,
        api_query_has_more_results=(total_count > len(rows)),
        coverage="ONE_SIREN_ONE_DATE_BOUNDED_PAGE; NOT_AN_ABSENCE_PROOF",
        freshness_note=(
            "retrieved_at is this collector's observation time; publication age is derived from "
            "dateparution. Upstream update lag and full-query coverage have not been live-verified."
        ),
        response_sha256=response_hash,
        records=notices,
    )


def write_collection(path, collection: BODACCCollection) -> None:
    """Atomically write a single JSON envelope; never append or retain raw API payloads."""
    from pathlib import Path

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(
        json.dumps(collection.as_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
