from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import date
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"
SOURCE_NAME = "ted_search_api_v3"
SOURCE_BUCKET = "contract-awards"

AWARD_NOTICE_TYPES = ("can-standard", "can-social", "can-desg", "can-tran")
AWARD_FIELDS = (
    "publication-number",
    "publication-date",
    "notice-type",
    "notice-title",
    "title-proc",
    "classification-cpv",
    "winner-name",
    "winner-country",
    "winner-identifier",
    "winner-decision-date",
    "tender-value",
    "tender-value-cur",
    "total-value",
    "total-value-cur",
)
_MAX_PAGE_RESULTS = 15_000
_SPACE_RE = re.compile(r"\s+")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _clean(value: object) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _scalar_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        values = value
    else:
        values = [value]
    result = []
    for item in values:
        cleaned = _clean(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _normalize_winner_name(value: str) -> str:
    return _SPACE_RE.sub(" ", value).strip().casefold()


def _validate_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Expected ISO date YYYY-MM-DD, received {value!r}") from exc


def build_award_query(start_date: str, end_date: str) -> str:
    start = _validate_iso_date(start_date)
    end = _validate_iso_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    if start == end:
        date_clause = f"publication-date = {start:%Y%m%d}"
    else:
        date_clause = f"publication-date = ({start:%Y%m%d} <> {end:%Y%m%d})"

    notice_types = " ".join(AWARD_NOTICE_TYPES)
    return (
        f"{date_clause} "
        f"AND notice-type IN ({notice_types}) "
        "AND winner-selection-status IN (selec-w)"
    )


def build_search_body(
    start_date: str,
    end_date: str,
    *,
    page: int,
    page_size: int,
    scope: str,
    only_latest_versions: bool,
) -> dict[str, object]:
    if page < 1:
        raise ValueError("page must be at least 1")
    if not 1 <= page_size <= 250:
        raise ValueError("page_size must be between 1 and 250")
    if scope not in {"ACTIVE", "ALL", "LATEST"}:
        raise ValueError("scope must be ACTIVE, ALL, or LATEST")

    return {
        "query": build_award_query(start_date, end_date),
        "fields": list(AWARD_FIELDS),
        "page": page,
        "limit": page_size,
        "scope": scope,
        "checkQuerySyntax": False,
        "paginationMode": "PAGE_NUMBER",
        "onlyLatestVersions": only_latest_versions,
    }


def _post_json(
    body: dict[str, object],
    *,
    timeout: int = 60,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> dict:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    request = Request(
        TED_SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; "
                "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
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


@dataclass(frozen=True, slots=True)
class TEDWinnerMention:
    winner_name: str
    normalized_name: str
    languages: tuple[str, ...]
    alignment_status: str
    winner_country: str
    winner_identifier: str
    winner_decision_date: str


@dataclass(frozen=True, slots=True)
class TEDNoticeRecord:
    publication_number: str
    publication_date: str
    notice_type: str
    payload: dict[str, object]

    @property
    def raw_record_json(self) -> str:
        return _canonical_json(self.payload)

    @property
    def raw_record_hash(self) -> str:
        return hashlib.sha256(self.raw_record_json.encode("utf-8")).hexdigest()

    @property
    def english_url(self) -> str:
        links = self.payload.get("links")
        if not isinstance(links, dict):
            return ""
        html = links.get("html")
        if not isinstance(html, dict):
            return ""
        return _clean(html.get("ENG") or html.get("eng"))

    def winner_mentions(self) -> tuple[TEDWinnerMention, ...]:
        raw_names = self.payload.get("winner-name")
        grouped: dict[str, dict[str, object]] = {}

        if isinstance(raw_names, dict):
            items = raw_names.items()
        else:
            items = [("", raw_names)]

        for language, raw_values in items:
            for name in _scalar_list(raw_values):
                normalized = _normalize_winner_name(name)
                if not normalized:
                    continue
                group = grouped.setdefault(
                    normalized,
                    {"names": [], "languages": set()},
                )
                names = group["names"]
                languages = group["languages"]
                if isinstance(names, list) and name not in names:
                    names.append(name)
                if isinstance(languages, set) and language:
                    languages.add(str(language).lower())

        countries = _scalar_list(self.payload.get("winner-country"))
        identifiers = _scalar_list(self.payload.get("winner-identifier"))
        decision_dates = _scalar_list(self.payload.get("winner-decision-date"))
        is_unambiguous = (
            len(grouped) == 1
            and len(countries) <= 1
            and len(identifiers) <= 1
            and len(decision_dates) <= 1
        )

        mentions: list[TEDWinnerMention] = []
        for normalized in sorted(grouped):
            group = grouped[normalized]
            names = group["names"]
            languages = group["languages"]
            assert isinstance(names, list)
            assert isinstance(languages, set)

            english_names = []
            if isinstance(raw_names, dict):
                english_names = _scalar_list(raw_names.get("eng"))
            canonical_name = (
                next((name for name in english_names if _normalize_winner_name(name) == normalized), "")
                or sorted(names)[0]
            )

            mentions.append(
                TEDWinnerMention(
                    winner_name=canonical_name,
                    normalized_name=normalized,
                    languages=tuple(sorted(languages)),
                    alignment_status=(
                        "SINGLE_WINNER_ALIGNED"
                        if is_unambiguous
                        else "NAME_ONLY_UNALIGNED"
                    ),
                    winner_country=countries[0] if is_unambiguous and countries else "",
                    winner_identifier=(
                        identifiers[0] if is_unambiguous and identifiers else ""
                    ),
                    winner_decision_date=(
                        decision_dates[0] if is_unambiguous and decision_dates else ""
                    ),
                )
            )

        return tuple(mentions)


@dataclass(frozen=True, slots=True)
class TEDSearchResult:
    start_date: str
    end_date: str
    scope: str
    page_size: int
    only_latest_versions: bool
    query: str
    query_body_json: str
    total_notice_count: int
    notices: tuple[TEDNoticeRecord, ...]

    @property
    def query_hash(self) -> str:
        return hashlib.sha256(self.query_body_json.encode("utf-8")).hexdigest()

    @property
    def response_hash(self) -> str:
        material = "\x1f".join(
            sorted(
                f"{notice.publication_number}:{notice.raw_record_hash}"
                for notice in self.notices
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def parse_notice(payload: dict[str, object]) -> TEDNoticeRecord:
    publication_number = _clean(payload.get("publication-number"))
    if not publication_number:
        raise ValueError("TED notice missing publication-number")

    return TEDNoticeRecord(
        publication_number=publication_number,
        publication_date=_clean(payload.get("publication-date")),
        notice_type=_clean(payload.get("notice-type")),
        payload=payload,
    )


def search_awards(
    start_date: str,
    end_date: str,
    *,
    page_size: int = 250,
    scope: str = "ALL",
    only_latest_versions: bool = False,
    timeout: int = 60,
    attempts: int = 3,
) -> TEDSearchResult:
    first_body = build_search_body(
        start_date,
        end_date,
        page=1,
        page_size=page_size,
        scope=scope,
        only_latest_versions=only_latest_versions,
    )
    query_body_json = _canonical_json(first_body)
    notices: list[TEDNoticeRecord] = []
    total_notice_count: int | None = None
    page = 1

    while True:
        body = dict(first_body)
        body["page"] = page
        payload = _post_json(body, timeout=timeout, attempts=attempts)

        if payload.get("timedOut") is True:
            raise RuntimeError("TED search timed out and may be incomplete")

        raw_notices = payload.get("notices") or []
        if not isinstance(raw_notices, list):
            raise ValueError("TED response 'notices' is not a list")

        for item in raw_notices:
            if not isinstance(item, dict):
                raise ValueError("TED notice entry is not an object")
            notices.append(parse_notice(item))

        if total_notice_count is None and payload.get("totalNoticeCount") is not None:
            total_notice_count = int(payload["totalNoticeCount"])
            if total_notice_count > _MAX_PAGE_RESULTS:
                raise ValueError(
                    "TED result count exceeds the 15,000-result PAGE_NUMBER cap; "
                    "split the date window"
                )

        if not raw_notices:
            break
        if total_notice_count is not None and len(notices) >= total_notice_count:
            break
        if len(raw_notices) < page_size:
            break

        page += 1
        if page * page_size > _MAX_PAGE_RESULTS:
            raise ValueError(
                "TED pagination reached the 15,000-result PAGE_NUMBER cap; "
                "split the date window"
            )

    if total_notice_count is None:
        total_notice_count = len(notices)

    return TEDSearchResult(
        start_date=start_date,
        end_date=end_date,
        scope=scope,
        page_size=page_size,
        only_latest_versions=only_latest_versions,
        query=str(first_body["query"]),
        query_body_json=query_body_json,
        total_notice_count=total_notice_count,
        notices=tuple(notices),
    )
