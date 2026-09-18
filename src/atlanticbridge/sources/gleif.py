from __future__ import annotations

import json
import time
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

GLEIF_API_BASE = "https://api.gleif.org/api/v1/lei-records"
SOURCE_NAME = "gleif_api"


def normalize_entity_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized.casefold() if char.isalnum())


def _similarity(left: str, right: str) -> float:
    a = normalize_entity_name(left)
    b = normalize_entity_name(right)
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _match_class(source_name: str, source_country: str, legal_name: str, jurisdiction: str) -> str:
    source_norm = normalize_entity_name(source_name)
    legal_norm = normalize_entity_name(legal_name)
    exact = bool(source_norm) and source_norm == legal_norm
    same_country = bool(source_country) and source_country.upper() == jurisdiction.upper()
    similarity = _similarity(source_name, legal_name)

    if exact and same_country:
        return "EXACT_NAME_COUNTRY"
    if exact:
        return "EXACT_NAME"
    if similarity >= 0.92 and same_country:
        return "SIMILAR_NAME_COUNTRY"
    if same_country:
        return "COUNTRY_MATCH_CANDIDATE"
    return "CANDIDATE"


@dataclass(frozen=True, slots=True)
class GLEIFCandidate:
    rank: int
    lei: str
    legal_name: str
    jurisdiction: str
    entity_status: str
    entity_category: str
    registered_as: str
    registration_authority_id: str
    legal_address_city: str
    legal_address_country: str
    headquarters_city: str
    headquarters_country: str
    name_similarity: float
    exact_normalized_name: bool
    jurisdiction_match: bool
    match_class: str
    relationship_links_json: str
    record_json: str


@dataclass(frozen=True, slots=True)
class GLEIFSearchResult:
    query_url: str
    golden_copy_publish_date: str
    total_results: int
    candidates: tuple[GLEIFCandidate, ...]


def _request_json(
    url: str,
    *,
    timeout: int = 30,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> dict:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    request = Request(
        url,
        headers={
            "Accept": "application/vnd.api+json",
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            ),
        },
    )

    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            if attempt >= attempts:
                raise

        time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def search_legal_name(
    source_name: str,
    *,
    source_country: str = "",
    page_size: int = 5,
    timeout: int = 30,
    attempts: int = 3,
) -> GLEIFSearchResult:
    source_name = " ".join((source_name or "").split()).strip()
    if not source_name:
        raise ValueError("source_name is required")
    if not 1 <= page_size <= 100:
        raise ValueError("page_size must be between 1 and 100")

    query_url = GLEIF_API_BASE + "?" + urlencode(
        {
            "filter[entity.legalName]": source_name,
            "page[size]": str(page_size),
        }
    )
    payload = _request_json(query_url, timeout=timeout, attempts=attempts)

    meta = payload.get("meta") or {}
    golden_copy = meta.get("goldenCopy") or {}
    pagination = meta.get("pagination") or {}
    candidates: list[GLEIFCandidate] = []

    for rank, row in enumerate(payload.get("data") or [], start=1):
        attributes = row.get("attributes") or {}
        entity = attributes.get("entity") or {}
        legal_name = ((entity.get("legalName") or {}).get("name") or "").strip()
        jurisdiction = (entity.get("jurisdiction") or "").strip()
        registered_at = entity.get("registeredAt") or {}
        legal_address = entity.get("legalAddress") or {}
        headquarters = entity.get("headquartersAddress") or {}

        source_norm = normalize_entity_name(source_name)
        legal_norm = normalize_entity_name(legal_name)
        candidates.append(
            GLEIFCandidate(
                rank=rank,
                lei=(row.get("id") or "").strip(),
                legal_name=legal_name,
                jurisdiction=jurisdiction,
                entity_status=(entity.get("status") or "").strip(),
                entity_category=(entity.get("category") or "").strip(),
                registered_as=(entity.get("registeredAs") or "").strip(),
                registration_authority_id=(registered_at.get("id") or "").strip(),
                legal_address_city=(legal_address.get("city") or "").strip(),
                legal_address_country=(legal_address.get("country") or "").strip(),
                headquarters_city=(headquarters.get("city") or "").strip(),
                headquarters_country=(headquarters.get("country") or "").strip(),
                name_similarity=_similarity(source_name, legal_name),
                exact_normalized_name=bool(source_norm) and source_norm == legal_norm,
                jurisdiction_match=(
                    bool(source_country)
                    and source_country.upper() == jurisdiction.upper()
                ),
                match_class=_match_class(
                    source_name,
                    source_country,
                    legal_name,
                    jurisdiction,
                ),
                relationship_links_json=json.dumps(
                    row.get("relationships") or {},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                record_json=json.dumps(
                    row,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            )
        )

    return GLEIFSearchResult(
        query_url=query_url,
        golden_copy_publish_date=(golden_copy.get("publishDate") or "").strip(),
        total_results=int(pagination.get("total") or len(candidates)),
        candidates=tuple(candidates),
    )
