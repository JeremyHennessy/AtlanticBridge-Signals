from __future__ import annotations

import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from ..constants import is_eu27_country, normalize_country

BASE_URL = (
    "https://ised-isde.canada.ca/site/investment-canada-act/en/"
    "search/decisions-and-notification-index"
)
SOURCE_NAME = "investment_canada_act_decisions_notifications"
_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
_BUCKET_RE = re.compile(r"^(all|[a-z0-9])$", re.IGNORECASE)
HISTORY_BUCKETS = tuple(
    [str(value) for value in range(10)]
    + [chr(code) for code in range(ord("a"), ord("z") + 1)]
)
INDEX_PAGE_SIZE = 50
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class InvestmentCanadaRecord:
    certification_month: str
    notification_type: str
    investor_text: str
    investor_name: str
    investor_locality: str
    investor_node_id: str
    country_of_ultimate_control: str
    canadian_business_text: str
    canadian_businesses_json: str
    canadian_business_node_ids: tuple[str, ...]
    source_url: str
    source_bucket: str
    source_page: int = 0

    @property
    def is_new_business(self) -> bool:
        return "new business" in self.notification_type.casefold()

    @property
    def is_eu27(self) -> bool:
        return is_eu27_country(self.country_of_ultimate_control)

    @property
    def raw_record_hash(self) -> str:
        material = "\x1f".join(
            [
                self.certification_month,
                self.notification_type,
                self.investor_text,
                self.country_of_ultimate_control,
                self.canadian_business_text,
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @property
    def structural_material(self) -> str:
        if not self.investor_node_id:
            return "\x1f".join(["fallback", self.raw_record_hash])
        return "\x1f".join(
            [
                self.certification_month,
                self.notification_type,
                self.investor_node_id,
                self.country_of_ultimate_control,
                ",".join(self.canadian_business_node_ids),
            ]
        )

    @property
    def record_id(self) -> str:
        return hashlib.sha256(self.structural_material.encode("utf-8")).hexdigest()

    @property
    def record_json(self) -> str:
        return _canonical_json(
            {
                "certification_month": self.certification_month,
                "notification_type": self.notification_type,
                "investor_text": self.investor_text,
                "investor_name": self.investor_name,
                "investor_locality": self.investor_locality,
                "investor_node_id": self.investor_node_id,
                "country_of_ultimate_control": self.country_of_ultimate_control,
                "canadian_business_text": self.canadian_business_text,
                "canadian_businesses": json.loads(self.canadian_businesses_json),
                "canadian_business_node_ids": list(self.canadian_business_node_ids),
            }
        )


@dataclass(frozen=True, slots=True)
class InvestmentCanadaPageSnapshot:
    source_url: str
    source_bucket: str
    source_page: int
    sha256: str
    record_count: int


@dataclass(frozen=True, slots=True)
class InvestmentCanadaHistoryResult:
    records: tuple[InvestmentCanadaRecord, ...]
    page_snapshots: tuple[InvestmentCanadaPageSnapshot, ...]
    appearances: int
    duplicate_appearances: int
    bucket_count: int
    page_count: int

    @property
    def unique_records(self) -> int:
        return len(self.records)


def source_url(bucket: str) -> str:
    bucket = bucket.strip().lower()
    if not _BUCKET_RE.fullmatch(bucket):
        raise ValueError(f"Unsupported Investment Canada index bucket: {bucket!r}")
    return f"{BASE_URL}/{bucket}"


def page_url(bucket: str, page: int = 0) -> str:
    if page < 0:
        raise ValueError("Investment Canada page index must be non-negative")
    base = source_url(bucket)
    if page == 0:
        return base
    return f"{base}?page={page}"


def _fetch_url(
    url: str,
    timeout: int = 45,
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> str:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    request = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, errors="replace")
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            if attempt >= attempts:
                raise

        time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def fetch_index_page(
    bucket: str,
    page: int = 0,
    timeout: int = 45,
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> tuple[str, str]:
    url = page_url(bucket, page)
    return (
        url,
        _fetch_url(
            url,
            timeout,
            attempts=attempts,
            backoff_seconds=backoff_seconds,
        ),
    )


def fetch_bucket(
    bucket: str,
    timeout: int = 45,
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> tuple[str, str]:
    """Fetch only the first page of one index bucket.

    This remains intentionally lightweight for smoke tests. Use
    crawl_investment_canada_history() for the complete historical corpus.
    """
    return fetch_index_page(
        bucket,
        0,
        timeout,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
    )


def last_page_index(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    page_indexes = [0]
    for link in soup.find_all("a", href=True):
        query = parse_qs(urlparse(link["href"]).query)
        for raw_page in query.get("page", []):
            try:
                page_indexes.append(int(raw_page))
            except ValueError:
                continue
    return max(page_indexes)


def _field_text(container, selector: str) -> str:
    node = container.select_one(selector) if container is not None else None
    if node is None:
        return ""
    return _clean(node.get_text(" ", strip=True))


def _parse_businesses(cell) -> tuple[str, tuple[str, ...]]:
    businesses = []
    node_ids = []

    for article in cell.find_all("article"):
        node_id = str(article.get("data-history-node-id") or "").strip()
        if node_id:
            node_ids.append(node_id)

        activity_node = article.select_one(".field--name-field-if-activity .field--item")
        activity = (
            _clean(activity_node.get_text(" ", strip=True))
            if activity_node is not None
            else ""
        )
        businesses.append(
            {
                "node_id": node_id,
                "name": _field_text(article, ".field--name-title"),
                "locality": _field_text(article, ".locality-element"),
                "administrative_area": _field_text(
                    article,
                    ".administrative-area-element",
                ),
                "activity": activity,
            }
        )

    return _canonical_json(businesses), tuple(node_ids)


def parse_index_html(
    html: str,
    *,
    source_url_value: str,
    source_bucket: str,
    source_page: int = 0,
) -> list[InvestmentCanadaRecord]:
    """Parse one Decisions and Notification Index page.

    Full display text is retained, while structured source fields and Drupal
    node IDs are also captured for durable historical identity resolution.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidate_tables = []

    for table in soup.find_all("table"):
        header_text = _clean(
            " ".join(th.get_text(" ", strip=True) for th in table.find_all("th"))
        )
        folded = header_text.casefold()
        if "date certification" in folded and "notification type" in folded:
            candidate_tables.append(table)

    if not candidate_tables:
        raise ValueError("Investment Canada index table not found")

    records: list[InvestmentCanadaRecord] = []

    for table in candidate_tables:
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 5:
                cells = row.find_all("td")
            if len(cells) < 5:
                continue

            values = [_clean(cell.get_text(" ", strip=True)) for cell in cells[:5]]
            certification_month, notification_type, investor, country, business = values

            if not _MONTH_RE.fullmatch(certification_month):
                continue
            if not notification_type or not investor or not country:
                continue

            investor_article = cells[2].find("article")
            investor_node_id = (
                str(investor_article.get("data-history-node-id") or "").strip()
                if investor_article is not None
                else ""
            )
            investor_name = (
                _field_text(investor_article, ".field--name-title")
                if investor_article is not None
                else ""
            )
            investor_locality = (
                _field_text(investor_article, ".locality-element")
                if investor_article is not None
                else ""
            )
            if not investor_name:
                investor_name = investor

            businesses_json, business_node_ids = _parse_businesses(cells[4])

            records.append(
                InvestmentCanadaRecord(
                    certification_month=certification_month,
                    notification_type=notification_type,
                    investor_text=investor,
                    investor_name=investor_name,
                    investor_locality=investor_locality,
                    investor_node_id=investor_node_id,
                    country_of_ultimate_control=normalize_country(country),
                    canadian_business_text=business,
                    canadian_businesses_json=businesses_json,
                    canadian_business_node_ids=business_node_ids,
                    source_url=source_url_value,
                    source_bucket=source_bucket,
                    source_page=source_page,
                )
            )

    return records


def _crawl_bucket_history(
    bucket: str,
    *,
    timeout: int,
    attempts: int,
    backoff_seconds: float,
    page_delay_seconds: float,
) -> tuple[list[InvestmentCanadaRecord], list[InvestmentCanadaPageSnapshot]]:
    first_url, first_html = fetch_index_page(
        bucket,
        0,
        timeout,
        attempts=attempts,
        backoff_seconds=backoff_seconds,
    )
    final_page = last_page_index(first_html)

    records: list[InvestmentCanadaRecord] = []
    snapshots: list[InvestmentCanadaPageSnapshot] = []

    for page in range(final_page + 1):
        if page == 0:
            url, html = first_url, first_html
        else:
            url, html = fetch_index_page(
                bucket,
                page,
                timeout,
                attempts=attempts,
                backoff_seconds=backoff_seconds,
            )

        page_records = parse_index_html(
            html,
            source_url_value=url,
            source_bucket=bucket,
            source_page=page,
        )

        if not page_records:
            raise ValueError(
                f"Investment Canada history page returned zero records: "
                f"bucket={bucket!r} page={page}"
            )
        if page < final_page and len(page_records) != INDEX_PAGE_SIZE:
            raise ValueError(
                f"Investment Canada non-terminal page was incomplete: "
                f"bucket={bucket!r} page={page} "
                f"expected={INDEX_PAGE_SIZE} got={len(page_records)}"
            )
        if page == final_page and len(page_records) > INDEX_PAGE_SIZE:
            raise ValueError(
                f"Investment Canada terminal page exceeded page size: "
                f"bucket={bucket!r} page={page} got={len(page_records)}"
            )

        missing_nodes = [record for record in page_records if not record.investor_node_id]
        if missing_nodes:
            raise ValueError(
                f"Investment Canada history identity gate failed: "
                f"bucket={bucket!r} page={page} "
                f"records_without_investor_node_id={len(missing_nodes)}"
            )

        records.extend(page_records)
        snapshots.append(
            InvestmentCanadaPageSnapshot(
                source_url=url,
                source_bucket=bucket,
                source_page=page,
                sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                record_count=len(page_records),
            )
        )

        if page < final_page and page_delay_seconds > 0:
            time.sleep(page_delay_seconds)

    return records, snapshots


def crawl_investment_canada_history(
    *,
    buckets: tuple[str, ...] = HISTORY_BUCKETS,
    workers: int = 4,
    timeout: int = 45,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
    page_delay_seconds: float = 0.05,
) -> InvestmentCanadaHistoryResult:
    if not buckets:
        raise ValueError("At least one Investment Canada history bucket is required")
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")

    normalized = tuple(bucket.strip().lower() for bucket in buckets)
    if len(set(normalized)) != len(normalized):
        raise ValueError("Investment Canada history buckets must be unique")
    for bucket in normalized:
        if bucket == "all" or not _BUCKET_RE.fullmatch(bucket):
            raise ValueError(
                f"Unsupported historical Investment Canada bucket: {bucket!r}"
            )

    bucket_results = {}
    with ThreadPoolExecutor(max_workers=min(workers, len(normalized))) as executor:
        futures = {
            executor.submit(
                _crawl_bucket_history,
                bucket,
                timeout=timeout,
                attempts=attempts,
                backoff_seconds=backoff_seconds,
                page_delay_seconds=page_delay_seconds,
            ): bucket
            for bucket in normalized
        }

        for future in as_completed(futures):
            bucket = futures[future]
            bucket_results[bucket] = future.result()

    ordered_records: list[InvestmentCanadaRecord] = []
    ordered_snapshots: list[InvestmentCanadaPageSnapshot] = []
    for bucket in normalized:
        bucket_records, bucket_snapshots = bucket_results[bucket]
        ordered_records.extend(bucket_records)
        ordered_snapshots.extend(bucket_snapshots)

    unique: dict[str, InvestmentCanadaRecord] = {}
    duplicate_appearances = 0
    for record in ordered_records:
        existing = unique.get(record.record_id)
        if existing is None:
            unique[record.record_id] = record
            continue

        duplicate_appearances += 1
        if existing.raw_record_hash != record.raw_record_hash:
            raise ValueError(
                "Investment Canada structural identity conflict: "
                f"record_id={record.record_id} "
                f"first_url={existing.source_url!r} duplicate_url={record.source_url!r}"
            )

    records = tuple(
        sorted(
            unique.values(),
            key=lambda record: (
                record.certification_month,
                record.record_id,
            ),
        )
    )
    snapshots = tuple(
        sorted(
            ordered_snapshots,
            key=lambda snapshot: (
                normalized.index(snapshot.source_bucket),
                snapshot.source_page,
            ),
        )
    )

    return InvestmentCanadaHistoryResult(
        records=records,
        page_snapshots=snapshots,
        appearances=len(ordered_records),
        duplicate_appearances=duplicate_appearances,
        bucket_count=len(normalized),
        page_count=len(snapshots),
    )
