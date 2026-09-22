from __future__ import annotations

import hashlib
import http.cookiejar
import json
import re
import time
import unicodedata
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from bs4 import BeautifulSoup

SEARCH_PAGE_URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch?lang=eng"
SEARCH_API_URL = "https://ised-isde.canada.ca/cipo/trademark-search/srch"
DETAIL_BASE_URL = "https://ised-isde.canada.ca/cipo/trademark-search"
SOURCE_NAME = "cipo_live_trademark_search"
MAX_RETURN = 5000

_OWNER_LABELS = (
    "Registered Owner",
    "Applicant",
    "Registrant",
    "Owner",
)
_DATE_LABELS = (
    "Filed",
    "Registered",
    "International Registration",
    "Registration Expiry Date",
)
_SPACE_RE = re.compile(r"\s+")


def normalize_owner_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized.casefold() if char.isalnum())


def _clean(value: object) -> str:
    return _SPACE_RE.sub(" ", str(value or "")).strip()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class CIPOSearchRecord:
    record_id: str
    application_number: str
    international_registration_numbers: tuple[str, ...]
    mark_name: str
    nice_codes: tuple[int, ...]
    status_code: str
    status_description: str
    mark_type: str
    st13_application_number: str
    raw_json: str

    @property
    def raw_hash(self) -> str:
        return hashlib.sha256(self.raw_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CIPOOwnerSearchResult:
    owner_query: str
    normalized_owner_query: str
    request_payload_json: str
    num_found: int
    num_returned: int
    response_hash: str
    records: tuple[CIPOSearchRecord, ...]


@dataclass(frozen=True, slots=True)
class CIPOTrademarkDetail:
    record_id: str
    application_number: str
    registration_number: str
    international_registration_number: str
    mark_name: str
    mark_type: str
    category: str
    cipo_status: str
    filed_date: str
    registered_date: str
    international_registration_date: str
    registration_expiry_date: str
    owner_label: str
    owner_name: str
    owner_lines: tuple[str, ...]
    priority_claims: tuple[str, ...]
    action_history: tuple[dict[str, str], ...]
    detail_url: str
    detail_html_hash: str
    facts_json: str

    def match_status(self, owner_query: str) -> str:
        query = normalize_owner_name(owner_query)
        owner = normalize_owner_name(self.owner_name)
        if query and owner and query == owner:
            return "EXACT_DETAIL_OWNER"
        if owner:
            return "DETAIL_OWNER_MISMATCH"
        return "DETAIL_OWNER_MISSING"


class CIPOResultCapExceeded(ValueError):
    pass


class CIPOIncompleteSearch(RuntimeError):
    pass


class CIPOSession:
    def __init__(
        self,
        *,
        timeout: int = 60,
        attempts: int = 3,
        backoff_seconds: float = 1.0,
    ):
        if attempts < 1:
            raise ValueError("attempts must be at least 1")
        if backoff_seconds < 0:
            raise ValueError("backoff_seconds must be non-negative")
        self.timeout = timeout
        self.attempts = attempts
        self.backoff_seconds = backoff_seconds
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookie_jar))
        self.headers = {
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; "
                "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            )
        }
        self._initialized = False

    def _open(self, request: Request):
        for attempt in range(1, self.attempts + 1):
            try:
                return self.opener.open(request, timeout=self.timeout)
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code <= 599
                if not retryable or attempt >= self.attempts:
                    raise
            except (TimeoutError, URLError) as exc:
                if attempt >= self.attempts:
                    raise
            time.sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        raise AssertionError("unreachable")

    def initialize(self) -> None:
        if self._initialized:
            return
        request = Request(SEARCH_PAGE_URL, headers=self.headers)
        with self._open(request) as response:
            response.read()
        self._initialized = True

    def search_owner(
        self,
        owner_name: str,
        *,
        max_return: int = MAX_RETURN,
    ) -> CIPOOwnerSearchResult:
        owner_name = _clean(owner_name)
        if not owner_name:
            raise ValueError("owner_name is required")
        if max_return != MAX_RETURN:
            raise ValueError(
                f"Production owner search requires max_return={MAX_RETURN} "
                "to support completeness checks"
            )

        self.initialize()
        payload = {
            "domIntlFilter": "1",
            "searchfield1": "ownname",
            "textfield1": owner_name,
            "nicetextfield1": [],
            "cipotextfield1": [],
            "display": "list",
            "maxReturn": str(max_return),
        }
        payload_json = _canonical_json(payload)

        request = Request(
            SEARCH_API_URL,
            data=payload_json.encode("utf-8"),
            method="POST",
            headers={
                **self.headers,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": SEARCH_PAGE_URL,
            },
        )
        with self._open(request) as response:
            body = response.read()
            content_type = response.headers.get_content_type()

        if content_type != "application/json":
            raise CIPOIncompleteSearch(
                f"CIPO owner search returned unexpected content type {content_type!r}"
            )

        data = json.loads(body.decode("utf-8", errors="replace"))
        num_found = int(data.get("numFound") or 0)
        num_returned = int(data.get("numReturned") or 0)
        docs = data.get("docs") or []
        if not isinstance(docs, list):
            raise CIPOIncompleteSearch("CIPO owner search 'docs' is not a list")

        if num_found > max_return:
            raise CIPOResultCapExceeded(
                f"CIPO owner search found {num_found} records, exceeding "
                f"the {max_return} result cap. Narrow the owner query."
            )
        if num_returned != len(docs):
            raise CIPOIncompleteSearch(
                f"CIPO reported numReturned={num_returned}, but {len(docs)} docs were received"
            )
        if num_returned != num_found:
            raise CIPOIncompleteSearch(
                f"CIPO returned {num_returned} of {num_found} records. "
                "Refusing to treat the result as complete."
            )

        records = tuple(_parse_search_record(item) for item in docs)
        response_hash = hashlib.sha256(
            _canonical_json(data).encode("utf-8")
        ).hexdigest()
        return CIPOOwnerSearchResult(
            owner_query=owner_name,
            normalized_owner_query=normalize_owner_name(owner_name),
            request_payload_json=payload_json,
            num_found=num_found,
            num_returned=num_returned,
            response_hash=response_hash,
            records=records,
        )

    def fetch_detail(self, record_id: str) -> CIPOTrademarkDetail:
        record_id = _clean(record_id)
        if not record_id:
            raise ValueError("record_id is required")

        self.initialize()
        detail_url = f"{DETAIL_BASE_URL}/{record_id}?lang=eng"
        request = Request(
            detail_url,
            headers={
                **self.headers,
                "Referer": SEARCH_PAGE_URL,
            },
        )
        with self._open(request) as response:
            html = response.read().decode(
                response.headers.get_content_charset() or "utf-8",
                errors="replace",
            )

        return parse_detail_html(
            html,
            record_id=record_id,
            detail_url=detail_url,
        )


def _parse_search_record(item: object) -> CIPOSearchRecord:
    if not isinstance(item, dict):
        raise CIPOIncompleteSearch("CIPO search record is not an object")

    record_id = _clean(item.get("id"))
    if not record_id:
        raise CIPOIncompleteSearch("CIPO search record missing id")

    intl_values = item.get("intlRegNos")
    if isinstance(intl_values, list):
        intl_registrations = tuple(
            _clean(value)
            for value in intl_values
            if _clean(value)
        )
    else:
        single = _clean(intl_values)
        intl_registrations = (single,) if single else ()

    nice_values = item.get("niceCodes")
    nice_codes: list[int] = []
    if isinstance(nice_values, list):
        for value in nice_values:
            try:
                nice_codes.append(int(value))
            except (TypeError, ValueError):
                continue

    raw_json = _canonical_json(item)
    return CIPOSearchRecord(
        record_id=record_id,
        application_number=_clean(item.get("appNo")),
        international_registration_numbers=intl_registrations,
        mark_name=_clean(item.get("markName")),
        nice_codes=tuple(nice_codes),
        status_code=_clean(item.get("statusCode")),
        status_description=_clean(item.get("statusDesc")),
        mark_type=_clean(item.get("type")),
        st13_application_number=_clean(item.get("st13ApplicationNumber")),
        raw_json=raw_json,
    )


def _row_facts(soup: BeautifulSoup) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    facts: dict[str, str] = {}
    lines_by_label: dict[str, tuple[str, ...]] = {}

    for row in soup.select("div.row"):
        header = row.find("h3")
        # Only consume headings owned by this row. An outer layout row may
        # contain the entire facts panel and an unrelated final column.
        if header is None or header.find_parent("div", class_="row") is not row:
            continue
        label = _clean(header.get_text(" ", strip=True)).rstrip(":")
        if not label or label in facts:
            continue

        cells = row.find_all("div", recursive=False)
        if len(cells) < 2:
            continue
        value_cell = cells[-1]
        lines = tuple(
            _clean(text)
            for text in value_cell.stripped_strings
            if _clean(text)
        )
        if not lines:
            continue
        lines_by_label[label] = lines
        facts[label] = " | ".join(lines)

    return facts, lines_by_label


def _parse_action_history(soup: BeautifulSoup) -> tuple[dict[str, str], ...]:
    section = soup.select_one("#details-act-hist")
    if section is None:
        return ()
    table = section.find("table")
    if table is None:
        return ()

    headers = [
        _clean(cell.get_text(" ", strip=True))
        for cell in table.find_all("th")
    ]
    if not headers:
        return ()

    rows: list[dict[str, str]] = []
    for tr in table.select("tbody tr"):
        cells = [
            _clean(cell.get_text(" ", strip=True))
            for cell in tr.find_all("td")
        ]
        if not cells:
            continue
        rows.append(
            {
                headers[index]: value
                for index, value in enumerate(cells)
                if index < len(headers)
            }
        )
    return tuple(rows)


def parse_detail_html(
    html: str,
    *,
    record_id: str,
    detail_url: str,
) -> CIPOTrademarkDetail:
    soup = BeautifulSoup(html, "html.parser")
    facts, lines_by_label = _row_facts(soup)

    title = soup.select_one("h1#wb-cont")
    title_text = _clean(title.get_text(" ", strip=True)) if title else ""
    mark_name = title_text
    suffix = f"— {record_id}"
    if suffix in mark_name:
        mark_name = _clean(mark_name.split(suffix, 1)[0])

    owner_label = ""
    owner_lines: tuple[str, ...] = ()
    for candidate in _OWNER_LABELS:
        if candidate in lines_by_label:
            owner_label = candidate
            owner_lines = lines_by_label[candidate]
            break
    owner_name = owner_lines[0] if owner_lines else ""

    claims: list[str] = []
    for heading in soup.find_all(["h2", "h3"]):
        if _clean(heading.get_text(" ", strip=True)).casefold() != "claims":
            continue
        parent = heading.parent
        if parent is None:
            continue
        for li in parent.find_all("li"):
            text = _clean(li.get_text(" ", strip=True))
            if text and text not in claims:
                claims.append(text)

    action_history = _parse_action_history(soup)
    detail_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()

    normalized_facts = {
        key: value
        for key, value in sorted(facts.items())
    }
    return CIPOTrademarkDetail(
        record_id=record_id,
        application_number=facts.get("Application number", ""),
        registration_number=facts.get("Registration number", ""),
        international_registration_number=facts.get(
            "International Registration Number",
            "",
        ),
        mark_name=mark_name,
        mark_type=facts.get("Type(s)", ""),
        category=facts.get("Category", ""),
        cipo_status=facts.get("CIPO Status", ""),
        filed_date=facts.get("Filed", ""),
        registered_date=facts.get("Registered", ""),
        international_registration_date=facts.get(
            "International Registration",
            "",
        ),
        registration_expiry_date=facts.get(
            "Registration Expiry Date",
            "",
        ),
        owner_label=owner_label,
        owner_name=owner_name,
        owner_lines=owner_lines,
        priority_claims=tuple(claims),
        action_history=action_history,
        detail_url=detail_url,
        detail_html_hash=detail_hash,
        facts_json=_canonical_json(normalized_facts),
    )
