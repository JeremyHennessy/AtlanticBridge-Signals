from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import ssl
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from bs4 import BeautifulSoup


HISTORY_PAGE_URL = (
    "https://ised-isde.canada.ca/site/canadian-intellectual-property-office/"
    "en/trademark-data-applications-and-registrations-xml-png"
)
ARCHIVE_PREFIX = "CA-TMK-GLOBAL_2025-06-14_"
ARCHIVE_RE = re.compile(
    r"CA-TMK-GLOBAL_2025-06-14_"
    r"(?P<first>\d+)_(?P<last>\d+)_(?P<sequence>\d{3})\.zip$"
)
EXPECTED_ARCHIVE_COUNT = 145
RAPIDSSL_INTERMEDIATE_URL = (
    "https://cacerts.digicert.com/RapidSSLTLSRSACAG1.crt.pem"
)
RAPIDSSL_INTERMEDIATE_SHA256 = (
    "4422e963ee53cd58cc9f85cd40bf5ffec0095fdf1a154535661c1c06bcadc69b"
)
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(complete historical CIPO XML research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def build_ssl_context(cache_dir: Path) -> ssl.SSLContext:
    cache_dir.mkdir(parents=True, exist_ok=True)
    pem_path = cache_dir / "RapidSSLTLSRSACAG1.crt.pem"
    if not pem_path.exists():
        request = Request(
            RAPIDSSL_INTERMEDIATE_URL,
            headers={"User-Agent": USER_AGENT},
        )
        with urlopen(request, timeout=60) as response:
            pem_path.write_bytes(response.read())

    pem_text = pem_path.read_text(encoding="ascii")
    der = ssl.PEM_cert_to_DER_cert(pem_text)
    fingerprint = hashlib.sha256(der).hexdigest()
    if fingerprint != RAPIDSSL_INTERMEDIATE_SHA256:
        raise ValueError(
            "DigiCert RapidSSL intermediate fingerprint mismatch: "
            f"{fingerprint} != {RAPIDSSL_INTERMEDIATE_SHA256}"
        )

    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(pem_path))
    return context


def _open_with_retry(
    request: Request,
    *,
    timeout: int,
    context: ssl.SSLContext | None = None,
    attempts: int = 4,
):
    for attempt in range(1, attempts + 1):
        try:
            return urlopen(request, timeout=timeout, context=context)
        except HTTPError as exc:
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            if attempt >= attempts:
                raise
        time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")


def fetch_archive_manifest() -> list[dict[str, object]]:
    request = Request(
        HISTORY_PAGE_URL,
        headers={"User-Agent": USER_AGENT},
    )
    with _open_with_retry(request, timeout=90) as response:
        html = response.read().decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )

    soup = BeautifulSoup(html, "html.parser")
    by_sequence: dict[int, dict[str, object]] = {}
    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "").strip()
        filename = Path(href).name
        match = ARCHIVE_RE.search(filename)
        if not match:
            continue
        sequence = int(match.group("sequence"))
        row = {
            "sequence": sequence,
            "first_application": int(match.group("first")),
            "last_application": int(match.group("last")),
            "filename": filename,
            "url": urljoin(HISTORY_PAGE_URL, href),
        }
        existing = by_sequence.get(sequence)
        if existing is not None and existing != row:
            raise ValueError(
                f"conflicting CIPO archive metadata for sequence {sequence}"
            )
        by_sequence[sequence] = row

    expected_sequences = list(range(1, EXPECTED_ARCHIVE_COUNT + 1))
    actual_sequences = sorted(by_sequence)
    if actual_sequences != expected_sequences:
        raise ValueError(
            "CIPO historical XML archive manifest is incomplete: "
            f"expected sequences 1..{EXPECTED_ARCHIVE_COUNT}, "
            f"got {actual_sequences[:10]}...{actual_sequences[-10:]}"
        )

    rows = [by_sequence[sequence] for sequence in expected_sequences]
    for previous, current in zip(rows, rows[1:]):
        if int(current["first_application"]) <= int(previous["first_application"]):
            raise ValueError("CIPO archive application ranges are not increasing")
        if int(current["last_application"]) <= int(previous["last_application"]):
            raise ValueError("CIPO archive application ranges are not increasing")
    return rows


def build_alias_index(
    entities_payload: dict[str, object],
) -> tuple[dict[str, set[str]], re.Pattern[bytes]]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("backtest entities payload requires entities list")

    alias_to_entities: dict[str, set[str]] = {}
    raw_aliases: set[str] = set()
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact aliases: {entity_id}")
        for alias in aliases:
            alias_text = str(alias).strip()
            normalized = normalize_name(alias_text)
            if not normalized:
                continue
            alias_to_entities.setdefault(normalized, set()).add(entity_id)
            raw_aliases.add(alias_text)

    if not raw_aliases:
        raise ValueError("no aliases configured")

    variants: set[bytes] = set()
    for alias in raw_aliases:
        for variant in (alias, alias.upper(), alias.lower()):
            variants.add(variant.encode("utf-8"))
    pattern = re.compile(
        b"|".join(
            re.escape(value)
            for value in sorted(variants, key=lambda item: (-len(item), item))
        ),
        flags=re.IGNORECASE,
    )
    return alias_to_entities, pattern


def _ancestor_with_fields(
    element: ET.Element,
    parent_map: dict[ET.Element, ET.Element],
    *,
    required_names: set[str],
    max_depth: int = 6,
) -> ET.Element | None:
    node: ET.Element | None = element
    for _ in range(max_depth):
        if node is None:
            return None
        names = {local_name(desc.tag) for desc in node.iter()}
        if required_names.issubset(names):
            return node
        node = parent_map.get(node)
    return None


def extract_applicant_names(root: ET.Element) -> list[str]:
    parent_map = {
        child: parent
        for parent in root.iter()
        for child in parent
    }
    applicants: list[str] = []
    for element in root.iter():
        if local_name(element.tag) != "InterestedPartyCategory":
            continue
        category = " ".join((element.text or "").split())
        if category.casefold() != "applicant":
            continue
        container = _ancestor_with_fields(
            element,
            parent_map,
            required_names={"InterestedPartyCategory", "EntityName"},
        )
        if container is None:
            continue
        categories = [
            " ".join((desc.text or "").split())
            for desc in container.iter()
            if local_name(desc.tag) == "InterestedPartyCategory"
            and (desc.text or "").strip()
        ]
        if not any(value.casefold() == "applicant" for value in categories):
            continue
        names = [
            " ".join((desc.text or "").split())
            for desc in container.iter()
            if local_name(desc.tag) == "EntityName"
            and (desc.text or "").strip()
        ]
        for name in names:
            if name not in applicants:
                applicants.append(name)
        if names:
            continue

    return applicants


def extract_advertised_dates(root: ET.Element) -> list[str]:
    dates: set[str] = set()
    parent_map = {
        child: parent
        for parent in root.iter()
        for child in parent
    }

    for element in root.iter():
        name = local_name(element.tag)
        text = " ".join((element.text or "").split())
        if not text:
            continue

        if (
            name == "PublicationStatusCategory"
            and text.casefold() == "advertised"
        ):
            container = _ancestor_with_fields(
                element,
                parent_map,
                required_names={
                    "PublicationStatusCategory",
                    "PublicationActionDate",
                },
            )
            if container is not None:
                for desc in container.iter():
                    if local_name(desc.tag) != "PublicationActionDate":
                        continue
                    value = " ".join((desc.text or "").split())
                    if value:
                        date.fromisoformat(value)
                        dates.add(value)

        if (
            name == "MarkEventDescriptionText"
            and text.casefold() == "advertised"
        ):
            container = _ancestor_with_fields(
                element,
                parent_map,
                required_names={
                    "MarkEventDescriptionText",
                    "MarkEventDate",
                },
            )
            if container is not None:
                for desc in container.iter():
                    if local_name(desc.tag) != "MarkEventDate":
                        continue
                    value = " ".join((desc.text or "").split())
                    if value:
                        date.fromisoformat(value)
                        dates.add(value)

    return sorted(dates)


def extract_application_number(
    root: ET.Element,
    archive_entry: str,
) -> str:
    filename_match = re.search(r"(\d+)(?:-\d+)?\.xml$", Path(archive_entry).name)
    filename_number = filename_match.group(1) if filename_match else ""

    candidates = []
    for element in root.iter():
        name = local_name(element.tag)
        text = " ".join((element.text or "").split())
        if not text:
            continue
        if name in {
            "ApplicationNumber",
            "ApplicationNumberText",
        }:
            candidates.append(text)
        elif name == "ST13ApplicationNumber":
            digits = "".join(char for char in text if char.isdigit())
            if len(digits) >= 9:
                # Canadian ST.13 values embed the application number before
                # a two-digit extension counter.
                core = digits.lstrip("0")
                if len(core) >= 3:
                    candidates.append(core[:-2])

    if filename_number:
        return filename_number
    if candidates:
        return candidates[0]
    raise ValueError(f"unable to derive application number from {archive_entry}")


def inspect_candidate_xml(
    data: bytes,
    *,
    archive_entry: str,
    alias_to_entities: dict[str, set[str]],
) -> list[dict[str, object]]:
    root = ET.fromstring(data)
    application_number = extract_application_number(root, archive_entry)
    applicants = extract_applicant_names(root)
    advertised_dates = extract_advertised_dates(root)

    matches: list[dict[str, object]] = []
    for applicant in applicants:
        normalized = normalize_name(applicant)
        entity_ids = alias_to_entities.get(normalized)
        if not entity_ids:
            continue
        for entity_id in sorted(entity_ids):
            matches.append(
                {
                    "entity_id": entity_id,
                    "application_number": application_number,
                    "matched_applicant_name": applicant,
                    "normalized_applicant_name": normalized,
                    "advertised_dates": advertised_dates,
                    "earliest_advertised_date": (
                        advertised_dates[0] if advertised_dates else None
                    ),
                    "xml_sha256": hashlib.sha256(data).hexdigest(),
                    "archive_entry": archive_entry,
                }
            )
    return matches


def download_archive(
    row: dict[str, object],
    destination: Path,
    *,
    context: ssl.SSLContext,
) -> dict[str, object]:
    digest = hashlib.sha256()
    byte_count = 0
    temp = destination.with_suffix(".part")
    request = Request(
        str(row["url"]),
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
        },
    )
    try:
        with _open_with_retry(
            request,
            timeout=300,
            context=context,
        ) as response, temp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
                handle.write(chunk)
        temp.replace(destination)
    except Exception:
        temp.unlink(missing_ok=True)
        raise

    return {
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def scan_archive(
    archive_path: Path,
    *,
    row: dict[str, object],
    alias_to_entities: dict[str, set[str]],
    alias_pattern: re.Pattern[bytes],
) -> dict[str, object]:
    xml_entries = 0
    candidate_raw_hits = 0
    confirmed_matches: list[dict[str, object]] = []

    with ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir() or not info.filename.lower().endswith(".xml"):
                continue
            xml_entries += 1
            data = archive.read(info)
            if alias_pattern.search(data) is None:
                continue
            candidate_raw_hits += 1
            confirmed_matches.extend(
                inspect_candidate_xml(
                    data,
                    archive_entry=info.filename,
                    alias_to_entities=alias_to_entities,
                )
            )

    return {
        "sequence": row["sequence"],
        "first_application": row["first_application"],
        "last_application": row["last_application"],
        "filename": row["filename"],
        "url": row["url"],
        "xml_entries_scanned": xml_entries,
        "candidate_raw_alias_hits": candidate_raw_hits,
        "confirmed_match_count": len(confirmed_matches),
        "matches": confirmed_matches,
    }


def run_worker(
    *,
    entities_payload: dict[str, object],
    worker_id: int,
    worker_count: int,
    temp_dir: Path,
) -> dict[str, object]:
    if worker_count < 1:
        raise ValueError("worker_count must be positive")
    if not 0 <= worker_id < worker_count:
        raise ValueError("worker_id must be in [0, worker_count)")

    manifest = fetch_archive_manifest()
    selected = [
        row
        for row in manifest
        if (int(row["sequence"]) - 1) % worker_count == worker_id
    ]
    if not selected:
        raise ValueError(f"worker {worker_id} has no assigned archives")

    alias_to_entities, alias_pattern = build_alias_index(entities_payload)
    context = build_ssl_context(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    chunk_results: list[dict[str, object]] = []
    all_matches: list[dict[str, object]] = []
    total_bytes = 0
    total_xml_entries = 0

    for index, row in enumerate(selected, start=1):
        archive_path = temp_dir / str(row["filename"])
        print(
            json.dumps(
                {
                    "worker_id": worker_id,
                    "archive_index": index,
                    "archive_count": len(selected),
                    "sequence": row["sequence"],
                    "filename": row["filename"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        download_meta = download_archive(
            row,
            archive_path,
            context=context,
        )
        try:
            scan = scan_archive(
                archive_path,
                row=row,
                alias_to_entities=alias_to_entities,
                alias_pattern=alias_pattern,
            )
        finally:
            archive_path.unlink(missing_ok=True)

        scan["download_bytes"] = download_meta["bytes"]
        scan["archive_sha256"] = download_meta["sha256"]
        total_bytes += int(download_meta["bytes"])
        total_xml_entries += int(scan["xml_entries_scanned"])
        matches = scan.pop("matches")
        assert isinstance(matches, list)
        for match in matches:
            match["archive_sequence"] = row["sequence"]
            match["archive_filename"] = row["filename"]
            all_matches.append(match)
        chunk_results.append(scan)

    all_matches.sort(
        key=lambda item: (
            str(item["entity_id"]),
            str(item["application_number"]),
            str(item.get("earliest_advertised_date") or ""),
        )
    )

    return {
        "schema_version": 1,
        "design": "CIPO_FULL_HISTORICAL_XML_EXACT_APPLICANT_SCAN_WORKER",
        "collection_date": "2025-06-14",
        "worker_id": worker_id,
        "worker_count": worker_count,
        "expected_full_archive_count": EXPECTED_ARCHIVE_COUNT,
        "summary": {
            "assigned_archive_count": len(selected),
            "download_bytes": total_bytes,
            "xml_entries_scanned": total_xml_entries,
            "confirmed_match_records": len(all_matches),
            "entities_with_match": len(
                {str(row["entity_id"]) for row in all_matches}
            ),
        },
        "chunks": chunk_results,
        "matches": all_matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument("--worker-id", type=int, required=True)
    parser.add_argument("--worker-count", type=int, required=True)
    parser.add_argument(
        "--temp-dir",
        default="control-output/cipo-xml-full-scan-temp",
    )
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    payload = run_worker(
        entities_payload=entities,
        worker_id=args.worker_id,
        worker_count=args.worker_count,
        temp_dir=Path(args.temp_dir),
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["matches"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
