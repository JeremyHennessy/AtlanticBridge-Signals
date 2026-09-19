from __future__ import annotations

import csv
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ACTIVE_BUSINESS_URL = "https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv"
INACTIVE_BUSINESS_URL = (
    "https://d4bf66bykfyaf.cloudfront.net/"
    "corporations-inactive-or-dissolved-cbca-en.csv"
)
FEDERAL_CORPORATION_JSON_BASE = (
    "https://www.ic.gc.ca/app/scr/cc/CorporationsCanada/api/corporations"
)
SOURCE_NAME = "corporations_canada_active_business"
SOURCE_BUCKET = "active-cbca"
INACTIVE_SOURCE_NAME = "corporations_canada_inactive_business"
INACTIVE_SOURCE_BUCKET = "inactive-cbca"
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)

EXPECTED_HEADER = [
    "Corporation number",
    "Business number (BN)",
    "Corporate name - form 1",
    "Corporate name - form 2",
    "Governing legislation",
    "Status",
    "Status Detail",
    "Anniversary date",
    "Year of last annual filing",
    "Date of last annual meeting",
    "Street",
    "Street 2",
    "City/town",
    "Province/territory",
    "Country",
    "Postal code",
    "Minimum number of directors",
    "Maximum number of directors",
]


def _clean(value: str | None) -> str:
    return " ".join((value or "").split()).strip()


@dataclass(frozen=True, slots=True)
class CorporationCanadaRecord:
    corporation_number: str
    business_number: str
    corporate_name_form_1: str
    corporate_name_form_2: str
    governing_legislation: str
    status: str
    status_detail: str
    anniversary_date: str
    year_last_annual_filing: str
    date_last_annual_meeting: str
    street: str
    street_2: str
    city_town: str
    province_territory: str
    country: str
    postal_code: str
    minimum_number_of_directors: str
    maximum_number_of_directors: str
    source_url: str = ACTIVE_BUSINESS_URL

    @property
    def source_state(self) -> str:
        if self.source_url == INACTIVE_BUSINESS_URL:
            return "INACTIVE"
        return "ACTIVE"

    @property
    def payload(self) -> dict[str, str]:
        return {
            "corporation_number": self.corporation_number,
            "business_number": self.business_number,
            "corporate_name_form_1": self.corporate_name_form_1,
            "corporate_name_form_2": self.corporate_name_form_2,
            "governing_legislation": self.governing_legislation,
            "status": self.status,
            "status_detail": self.status_detail,
            "anniversary_date": self.anniversary_date,
            "year_last_annual_filing": self.year_last_annual_filing,
            "date_last_annual_meeting": self.date_last_annual_meeting,
            "street": self.street,
            "street_2": self.street_2,
            "city_town": self.city_town,
            "province_territory": self.province_territory,
            "country": self.country,
            "postal_code": self.postal_code,
            "minimum_number_of_directors": self.minimum_number_of_directors,
            "maximum_number_of_directors": self.maximum_number_of_directors,
        }

    @property
    def record_json(self) -> str:
        return json.dumps(
            self.payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def record_hash(self) -> str:
        return hashlib.sha256(self.record_json.encode("utf-8")).hexdigest()

    def stage_tuple(self) -> tuple[str, ...]:
        return (
            self.corporation_number,
            self.business_number,
            self.corporate_name_form_1,
            self.corporate_name_form_2,
            self.governing_legislation,
            self.status,
            self.status_detail,
            self.anniversary_date,
            self.year_last_annual_filing,
            self.date_last_annual_meeting,
            self.street,
            self.street_2,
            self.city_town,
            self.province_territory,
            self.country,
            self.postal_code,
            self.minimum_number_of_directors,
            self.maximum_number_of_directors,
            self.record_hash,
            self.record_json,
            self.source_url,
        )


@dataclass(frozen=True, slots=True)
class DownloadResult:
    path: Path
    sha256: str
    byte_count: int
    source_url: str


def download_business_csv(
    destination: str | Path,
    *,
    source_url: str,
    timeout: int = 180,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> DownloadResult:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(source_url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, attempts + 1):
        part = destination.with_suffix(destination.suffix + ".part")
        try:
            digest = hashlib.sha256()
            byte_count = 0
            with urlopen(request, timeout=timeout) as response, part.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
                    handle.write(chunk)
            part.replace(destination)
            return DownloadResult(
                path=destination,
                sha256=digest.hexdigest(),
                byte_count=byte_count,
                source_url=source_url,
            )
        except HTTPError as exc:
            part.unlink(missing_ok=True)
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            part.unlink(missing_ok=True)
            if attempt >= attempts:
                raise
        time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def download_active_business_csv(
    destination: str | Path,
    *,
    source_url: str = ACTIVE_BUSINESS_URL,
    timeout: int = 120,
) -> DownloadResult:
    return download_business_csv(
        destination,
        source_url=source_url,
        timeout=timeout,
    )


def download_inactive_business_csv(
    destination: str | Path,
    *,
    source_url: str = INACTIVE_BUSINESS_URL,
    timeout: int = 180,
) -> DownloadResult:
    return download_business_csv(
        destination,
        source_url=source_url,
        timeout=timeout,
    )


def iter_business_csv(
    path: str | Path,
    *,
    source_url: str,
):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_HEADER:
            raise ValueError(
                "Corporations Canada business schema changed. "
                f"Expected {EXPECTED_HEADER!r}, received {reader.fieldnames!r}"
            )

        for row in reader:
            corporation_number = _clean(row["Corporation number"])
            if not corporation_number:
                continue

            yield CorporationCanadaRecord(
                corporation_number=corporation_number,
                business_number=_clean(row["Business number (BN)"]),
                corporate_name_form_1=_clean(row["Corporate name - form 1"]),
                corporate_name_form_2=_clean(row["Corporate name - form 2"]),
                governing_legislation=_clean(row["Governing legislation"]),
                status=_clean(row["Status"]),
                status_detail=_clean(row["Status Detail"]),
                anniversary_date=_clean(row["Anniversary date"]),
                year_last_annual_filing=_clean(row["Year of last annual filing"]),
                date_last_annual_meeting=_clean(row["Date of last annual meeting"]),
                street=_clean(row["Street"]),
                street_2=_clean(row["Street 2"]),
                city_town=_clean(row["City/town"]),
                province_territory=_clean(row["Province/territory"]),
                country=_clean(row["Country"]),
                postal_code=_clean(row["Postal code"]),
                minimum_number_of_directors=_clean(row["Minimum number of directors"]),
                maximum_number_of_directors=_clean(row["Maximum number of directors"]),
                source_url=source_url,
            )


def iter_active_business_csv(
    path: str | Path,
    *,
    source_url: str = ACTIVE_BUSINESS_URL,
):
    yield from iter_business_csv(path, source_url=source_url)


def iter_inactive_business_csv(
    path: str | Path,
    *,
    source_url: str = INACTIVE_BUSINESS_URL,
):
    yield from iter_business_csv(path, source_url=source_url)


def corporation_json_url(corporation_number: str) -> str:
    identifier = "".join(ch for ch in corporation_number if ch.isdigit())
    if not identifier:
        raise ValueError("corporation_number must contain digits")
    return f"{FEDERAL_CORPORATION_JSON_BASE}/{identifier}.json?lang=eng"


def fetch_corporation_json(
    corporation_number: str,
    *,
    timeout: int = 45,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> tuple[str, dict]:
    url = corporation_json_url(corporation_number)
    request = Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            if not isinstance(payload, list) or not payload:
                raise ValueError(
                    f"Unexpected Corporations Canada JSON response for {corporation_number}"
                )
            english = payload[0]
            if not isinstance(english, dict):
                raise ValueError(
                    f"Corporations Canada JSON did not return an English corporation "
                    f"object for {corporation_number}: {payload!r}"
                )
            return url, english
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            if attempt >= attempts:
                raise
        time.sleep(backoff_seconds * (2 ** (attempt - 1)))

    raise AssertionError("unreachable")


def detail_corporation_names(payload: dict) -> tuple[str, ...]:
    names: list[str] = []
    for wrapper in payload.get("corporationNames") or []:
        if not isinstance(wrapper, dict):
            continue
        item = wrapper.get("CorporationName")
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name"))
        if name and name not in names:
            names.append(name)
    return tuple(names)


def first_federal_jurisdiction_event(payload: dict) -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []
    for wrapper in payload.get("activities") or []:
        if not isinstance(wrapper, dict):
            continue
        item = wrapper.get("activity")
        if not isinstance(item, dict):
            continue
        activity = _clean(item.get("activity"))
        event_date = _clean(item.get("date"))
        folded = activity.casefold()
        if not event_date:
            continue
        if any(
            token in folded
            for token in ("incorporation", "amalgamation", "continuance")
        ):
            candidates.append((event_date, activity))
    if not candidates:
        return "", ""
    event_date, activity = min(candidates, key=lambda item: item[0])
    return activity, event_date
