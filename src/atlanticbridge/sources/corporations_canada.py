from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

ACTIVE_BUSINESS_URL = "https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv"
SOURCE_NAME = "corporations_canada_active_business"
SOURCE_BUCKET = "active-cbca"

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
        return json.dumps(self.payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

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


def download_active_business_csv(
    destination: str | Path,
    *,
    source_url: str = ACTIVE_BUSINESS_URL,
    timeout: int = 120,
) -> DownloadResult:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(
        source_url,
        headers={
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            )
        },
    )

    digest = hashlib.sha256()
    byte_count = 0

    with urlopen(request, timeout=timeout) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            byte_count += len(chunk)
            handle.write(chunk)

    return DownloadResult(
        path=destination,
        sha256=digest.hexdigest(),
        byte_count=byte_count,
        source_url=source_url,
    )


def iter_active_business_csv(
    path: str | Path,
    *,
    source_url: str = ACTIVE_BUSINESS_URL,
):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_HEADER:
            raise ValueError(
                "Corporations Canada active-business schema changed. "
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
