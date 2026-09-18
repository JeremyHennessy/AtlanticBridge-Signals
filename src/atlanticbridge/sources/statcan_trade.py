from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..constants import EU27

USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)

MONTHLY_PID = "12100175"
ANNUAL_PID = "12100173"

MONTHLY_MAJOR_EU_PARTNERS = {
    "Belgium",
    "France",
    "Germany",
    "Italy",
    "Netherlands",
    "Spain",
}

TARGET_GEOS = {"Canada", "Nova Scotia"}

MONTHLY_HEADER = [
    "REF_DATE",
    "GEO",
    "DGUID",
    "Trade",
    "North American Product Classification System (NAPCS)",
    "Principal trading partners",
    "UOM",
    "UOM_ID",
    "SCALAR_FACTOR",
    "SCALAR_ID",
    "VECTOR",
    "COORDINATE",
    "VALUE",
    "STATUS",
    "SYMBOL",
    "TERMINATED",
    "DECIMALS",
]

ANNUAL_HEADER = [
    "REF_DATE",
    "GEO",
    "DGUID",
    "Trading partner",
    "North American Product Classification System (NAPCS)",
    "Trade",
    "UOM",
    "UOM_ID",
    "SCALAR_FACTOR",
    "SCALAR_ID",
    "VECTOR",
    "COORDINATE",
    "VALUE",
    "STATUS",
    "SYMBOL",
    "TERMINATED",
    "DECIMALS",
]

MONTHLY_TOTAL_COMMODITY = "Total of all merchandise"
ANNUAL_TOTAL_COMMODITY = "All sections"

# These broad sections can contain defence-related or non-comparable activity.
# They are preserved as aggregate source context but are never score inputs.
SCORING_EXCLUDED_COMMODITIES = {
    "Aircraft and other transportation equipment and parts [C21]",
    "Special transactions trade [C23]",
}


@dataclass(frozen=True, slots=True)
class StatCanSourceConfig:
    pid: str
    cadence: str
    partner_field: str
    expected_header: tuple[str, ...]
    target_partners: frozenset[str]
    data_member: str
    source_name: str
    source_bucket: str


MONTHLY_CONFIG = StatCanSourceConfig(
    pid=MONTHLY_PID,
    cadence="monthly",
    partner_field="Principal trading partners",
    expected_header=tuple(MONTHLY_HEADER),
    target_partners=frozenset(MONTHLY_MAJOR_EU_PARTNERS),
    data_member=f"{MONTHLY_PID}.csv",
    source_name=f"statcan_trade_{MONTHLY_PID}",
    source_bucket="monthly-major-eu",
)

ANNUAL_CONFIG = StatCanSourceConfig(
    pid=ANNUAL_PID,
    cadence="annual",
    partner_field="Trading partner",
    expected_header=tuple(ANNUAL_HEADER),
    target_partners=frozenset(EU27),
    data_member=f"{ANNUAL_PID}.csv",
    source_name=f"statcan_trade_{ANNUAL_PID}",
    source_bucket="annual-eu27",
)


@dataclass(frozen=True, slots=True)
class StatCanDownload:
    config: StatCanSourceConfig
    archive_path: Path
    download_url: str
    archive_sha256: str
    archive_bytes: int


@dataclass(frozen=True, slots=True)
class StatCanTradeRecord:
    source_pid: str
    cadence: str
    ref_date: str
    geo: str
    dguid: str
    trade: str
    commodity: str
    partner: str
    uom: str
    scalar_factor: str
    vector: str
    coordinate: str
    value: str
    status: str
    symbol: str
    terminated: str
    decimals: str
    raw_json: str
    raw_hash: str

    @property
    def record_id(self) -> str:
        material = "\x1f".join(
            [
                self.source_pid,
                self.ref_date,
                self.geo,
                self.trade,
                self.commodity,
                self.partner,
                self.vector,
            ]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_json(
    url: str,
    *,
    timeout: int = 60,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT})
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


def _download_file(
    url: str,
    destination: Path,
    *,
    timeout: int = 180,
    attempts: int = 3,
    backoff_seconds: float = 1.0,
) -> tuple[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": USER_AGENT})

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
            return digest.hexdigest(), byte_count
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


def resolve_download_url(config: StatCanSourceConfig) -> str:
    wds_url = (
        "https://www150.statcan.gc.ca/t1/wds/rest/"
        f"getFullTableDownloadCSV/{config.pid}/en"
    )
    payload = _request_json(wds_url)
    if payload.get("status") != "SUCCESS" or not payload.get("object"):
        raise RuntimeError(
            f"Statistics Canada WDS did not return a download URL for {config.pid}: "
            f"{payload!r}"
        )
    return str(payload["object"])


def download_table(
    config: StatCanSourceConfig,
    destination_dir: str | Path,
) -> StatCanDownload:
    destination_dir = Path(destination_dir)
    download_url = resolve_download_url(config)
    archive_path = destination_dir / f"{config.pid}-eng.zip"
    sha256, byte_count = _download_file(download_url, archive_path)
    return StatCanDownload(
        config=config,
        archive_path=archive_path,
        download_url=download_url,
        archive_sha256=sha256,
        archive_bytes=byte_count,
    )


def iter_filtered_records(download: StatCanDownload):
    config = download.config
    with zipfile.ZipFile(download.archive_path) as archive:
        names = set(archive.namelist())
        if config.data_member not in names:
            raise ValueError(
                f"Statistics Canada archive {config.pid} missing "
                f"{config.data_member}; members={sorted(names)!r}"
            )

        with archive.open(config.data_member) as raw:
            import io

            handle = io.TextIOWrapper(
                raw,
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            )
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != config.expected_header:
                raise ValueError(
                    f"Statistics Canada {config.pid} schema changed. "
                    f"Expected {list(config.expected_header)!r}, "
                    f"received {reader.fieldnames!r}"
                )

            commodity_field = "North American Product Classification System (NAPCS)"

            for row in reader:
                geo = (row.get("GEO") or "").strip()
                if geo not in TARGET_GEOS:
                    continue

                partner = (row.get(config.partner_field) or "").strip()
                if partner not in config.target_partners:
                    continue

                raw_json = _canonical_json(row)
                yield StatCanTradeRecord(
                    source_pid=config.pid,
                    cadence=config.cadence,
                    ref_date=(row.get("REF_DATE") or "").strip(),
                    geo=geo,
                    dguid=(row.get("DGUID") or "").strip(),
                    trade=(row.get("Trade") or "").strip(),
                    commodity=(row.get(commodity_field) or "").strip(),
                    partner=partner,
                    uom=(row.get("UOM") or "").strip(),
                    scalar_factor=(row.get("SCALAR_FACTOR") or "").strip(),
                    vector=(row.get("VECTOR") or "").strip(),
                    coordinate=(row.get("COORDINATE") or "").strip(),
                    value=(row.get("VALUE") or "").strip(),
                    status=(row.get("STATUS") or "").strip(),
                    symbol=(row.get("SYMBOL") or "").strip(),
                    terminated=(row.get("TERMINATED") or "").strip(),
                    decimals=(row.get("DECIMALS") or "").strip(),
                    raw_json=raw_json,
                    raw_hash=hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
                )


def download_default_sources(destination_dir: str | Path) -> tuple[StatCanDownload, ...]:
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    return (
        download_table(MONTHLY_CONFIG, destination_dir),
        download_table(ANNUAL_CONFIG, destination_dir),
    )
