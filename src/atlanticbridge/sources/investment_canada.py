from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass
from urllib.error import URLError
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


def _clean(value: str) -> str:
    return " ".join(value.split()).strip()


@dataclass(frozen=True, slots=True)
class InvestmentCanadaRecord:
    certification_month: str
    notification_type: str
    investor_text: str
    country_of_ultimate_control: str
    canadian_business_text: str
    source_url: str
    source_bucket: str

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
    def record_id(self) -> str:
        material = "\x1f".join([self.source_url, self.raw_record_hash])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def source_url(bucket: str) -> str:
    bucket = bucket.strip().lower()
    if not _BUCKET_RE.fullmatch(bucket):
        raise ValueError(f"Unsupported Investment Canada index bucket: {bucket!r}")
    return f"{BASE_URL}/{bucket}"


def fetch_bucket(
    bucket: str,
    timeout: int = 45,
    *,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> tuple[str, str]:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must be non-negative")

    url = source_url(bucket)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            )
        },
    )

    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return url, response.read().decode(charset, errors="replace")
        except (TimeoutError, URLError):
            if attempt >= attempts:
                raise
            time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def parse_index_html(
    html: str,
    *,
    source_url_value: str,
    source_bucket: str,
) -> list[InvestmentCanadaRecord]:
    """Parse one Decisions and Notification Index page.

    The parser intentionally preserves the full Canadian-business cell as text.
    Business-name/city/activity normalization is deferred until variation across
    historical source pages is measured.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidate_tables = []

    for table in soup.find_all("table"):
        header_text = _clean(" ".join(th.get_text(" ", strip=True) for th in table.find_all("th")))
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
                # Some table implementations wrap cells; retry without direct-child restriction.
                cells = row.find_all("td")
            if len(cells) < 5:
                continue

            values = [_clean(cell.get_text(" ", strip=True)) for cell in cells[:5]]
            certification_month, notification_type, investor, country, business = values

            if not _MONTH_RE.fullmatch(certification_month):
                continue
            if not notification_type or not investor or not country:
                continue

            records.append(
                InvestmentCanadaRecord(
                    certification_month=certification_month,
                    notification_type=notification_type,
                    investor_text=investor,
                    country_of_ultimate_control=normalize_country(country),
                    canadian_business_text=business,
                    source_url=source_url_value,
                    source_bucket=source_bucket,
                )
            )

    return records
