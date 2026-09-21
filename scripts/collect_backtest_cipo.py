from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import ssl
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zipfile import ZipFile


DEFAULT_INTERESTED_PARTY_URL = (
    "https://opic-cipo.ca/cipo/client_downloads/TM_CSV_2025_01_28/"
    "TM_interested_party_2025-01-28.zip"
)
DEFAULT_EVENT_URL = (
    "https://opic-cipo.ca/cipo/client_downloads/TM_CSV_2025_01_28/"
    "TM_event_2025-01-28.zip"
)
SIGNAL_FAMILY = "CIPO_CANADIAN_TRADEMARK"
APPLICANT_PARTY_TYPE = "1"
ADVERTISED_ACTION_CODE = "42"
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(historical backtest research; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)
RAPIDSSL_INTERMEDIATE_URL = (
    "https://cacerts.digicert.com/RapidSSLTLSRSACAG1.crt.pem"
)
RAPIDSSL_INTERMEDIATE_SHA256 = (
    "4422e963ee53cd58cc9f85cd40bf5ffec0095fdf1a154535661c1c06bcadc69b"
)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (value or "").casefold())


def find_field(row: dict[str, str], prefix: str) -> str:
    prefix = normalize_header(prefix)
    matches = [
        value
        for key, value in row.items()
        if normalize_header(key).startswith(prefix)
    ]
    if not matches:
        raise ValueError(
            f"CIPO dataset missing field with normalized prefix {prefix!r}; "
            f"headers={list(row)[:20]!r}"
        )
    return str(matches[0] or "").strip()


def build_cipo_ssl_context(cache_dir: Path) -> tuple[ssl.SSLContext, dict[str, str]]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    pem_path = cache_dir / "RapidSSLTLSRSACAG1.crt.pem"
    request = Request(
        RAPIDSSL_INTERMEDIATE_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "application/x-pem-file,*/*"},
    )
    with urlopen(request, timeout=60) as response:
        pem_bytes = response.read()
    pem_text = pem_bytes.decode("ascii")
    der = ssl.PEM_cert_to_DER_cert(pem_text)
    fingerprint = hashlib.sha256(der).hexdigest()
    if fingerprint != RAPIDSSL_INTERMEDIATE_SHA256:
        raise ValueError(
            "DigiCert RapidSSL intermediate fingerprint mismatch: "
            f"{fingerprint} != {RAPIDSSL_INTERMEDIATE_SHA256}"
        )
    pem_path.write_bytes(pem_bytes)

    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(pem_path))
    return context, {
        "intermediate_url": RAPIDSSL_INTERMEDIATE_URL,
        "intermediate_sha256": fingerprint,
    }


def download(
    url: str,
    destination: Path,
    *,
    attempts: int = 4,
    timeout: int = 180,
    ssl_context: ssl.SSLContext | None = None,
) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(destination.suffix + ".part")
    for attempt in range(1, attempts + 1):
        digest = hashlib.sha256()
        byte_count = 0
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
                },
            )
            with urlopen(
                request,
                timeout=timeout,
                context=ssl_context,
            ) as response, temp.open("wb") as out:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    byte_count += len(chunk)
                    out.write(chunk)
            temp.replace(destination)
            return {
                "url": url,
                "sha256": digest.hexdigest(),
                "bytes": byte_count,
            }
        except HTTPError as exc:
            temp.unlink(missing_ok=True)
            retryable = exc.code == 429 or 500 <= exc.code <= 599
            if not retryable or attempt >= attempts:
                raise
        except (TimeoutError, URLError):
            temp.unlink(missing_ok=True)
            if attempt >= attempts:
                raise
        time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")


CIPO_CSV_FIELD_SIZE_LIMIT = 16 * 1024 * 1024


def iter_zip_rows(path: Path):
    previous_limit = csv.field_size_limit()
    if previous_limit < CIPO_CSV_FIELD_SIZE_LIMIT:
        csv.field_size_limit(CIPO_CSV_FIELD_SIZE_LIMIT)
    try:
        with ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if not name.endswith("/")
                and name.lower().endswith((".csv", ".txt"))
            ]
            if not members:
                raise ValueError(f"no CSV/TXT member found in {path}")
            for member in sorted(members):
                with archive.open(member) as raw:
                    text = io.TextIOWrapper(
                        raw,
                        encoding="utf-8-sig",
                        errors="replace",
                        newline="",
                    )
                    reader = csv.DictReader(text, delimiter="|")
                    if not reader.fieldnames:
                        raise ValueError(f"missing header in {path}:{member}")
                    for row in reader:
                        yield member, row
    finally:
        if previous_limit < CIPO_CSV_FIELD_SIZE_LIMIT:
            csv.field_size_limit(previous_limit)

def build_alias_index(entities_payload: dict[str, object]):
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("backtest entities payload requires entities list")
    alias_to_entities: dict[str, set[str]] = {}
    entity_aliases: dict[str, list[str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity row must be object")
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact_aliases: {entity_id}")
        cleaned = []
        for alias in aliases:
            normalized = normalize_name(str(alias))
            if not normalized:
                continue
            if normalized not in cleaned:
                cleaned.append(normalized)
            alias_to_entities.setdefault(normalized, set()).add(entity_id)
        entity_aliases[entity_id] = cleaned
    return alias_to_entities, entity_aliases


def collect(
    *,
    entities_payload: dict[str, object],
    interested_party_zip: Path,
    event_zip: Path,
    source_metadata: dict[str, object],
) -> dict[str, object]:
    alias_to_entities, entity_aliases = build_alias_index(entities_payload)

    matched_apps: dict[str, set[str]] = {}
    applicant_matches: list[dict[str, str]] = []
    interested_rows = 0
    applicant_rows = 0

    for member, row in iter_zip_rows(interested_party_zip):
        interested_rows += 1
        party_type = find_field(row, "Party Type Code")
        if party_type.lstrip("0") != APPLICANT_PARTY_TYPE:
            continue
        applicant_rows += 1
        party_name = find_field(row, "Party Name")
        normalized = normalize_name(party_name)
        entity_ids = alias_to_entities.get(normalized)
        if not entity_ids:
            continue
        application_number = find_field(row, "Application Number")
        for entity_id in sorted(entity_ids):
            matched_apps.setdefault(application_number, set()).add(entity_id)
            applicant_matches.append(
                {
                    "entity_id": entity_id,
                    "application_number": application_number,
                    "party_name": party_name,
                    "normalized_party_name": normalized,
                    "party_type_code": party_type,
                    "source_member": member,
                }
            )

    advertised: dict[str, list[dict[str, str]]] = {}
    event_rows = 0
    matched_event_rows = 0
    last_date_by_app: dict[str, str] = {}
    last_code_by_app: dict[str, str] = {}

    for member, row in iter_zip_rows(event_zip):
        event_rows += 1
        application_number = find_field(row, "Application Number")
        if application_number not in matched_apps:
            continue
        matched_event_rows += 1
        action_date = find_field(row, "Action Date")
        action_code_raw = find_field(row, "CIPO Action Code")
        action_code = action_code_raw.lstrip("0") or "0"
        if action_date:
            last_date_by_app[application_number] = action_date
            last_code_by_app[application_number] = action_code
        elif last_code_by_app.get(application_number) == action_code:
            action_date = last_date_by_app.get(application_number, "")

        if action_code != ADVERTISED_ACTION_CODE or not action_date:
            continue
        comment = find_field(row, "Additional Information Comment")
        advertised.setdefault(application_number, []).append(
            {
                "action_date": action_date,
                "comment": comment,
                "source_member": member,
            }
        )

    records: list[dict[str, object]] = []
    seen_evidence_ids: set[str] = set()
    for match in applicant_matches:
        app = match["application_number"]
        for event in advertised.get(app, []):
            material = "\x1f".join(
                [
                    match["entity_id"],
                    app,
                    event["action_date"],
                    match["normalized_party_name"],
                ]
            )
            evidence_id = hashlib.sha256(material.encode("utf-8")).hexdigest()
            if evidence_id in seen_evidence_ids:
                continue
            seen_evidence_ids.add(evidence_id)
            records.append(
                {
                    "evidence_id": evidence_id,
                    "entity_id": match["entity_id"],
                    "signal_family": SIGNAL_FAMILY,
                    "application_number": app,
                    "matched_applicant_name": match["party_name"],
                    "party_type_code": match["party_type_code"],
                    "publicly_available_date": event["action_date"],
                    "publicly_available_date_precision": "DAY",
                    "publicly_available_date_basis": (
                        "CIPO researcher TM_Event action code 42 (Advertised), "
                        "published in the Trademarks Journal"
                    ),
                    "journal_reference": event["comment"],
                    "source_url": (
                        "https://ised-isde.canada.ca/cipo/trademark-search/"
                        f"{app}"
                    ),
                    "match_method": "EXACT_REVIEWED_ALIAS_APPLICANT",
                }
            )

    records.sort(
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["application_number"]),
        )
    )

    coverage = []
    for entity in entities_payload["entities"]:
        entity_id = str(entity["entity_id"])
        coverage.append(
            {
                "entity_id": entity_id,
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": "COMPLETE_EXACT_ALIAS_HISTORY",
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "aliases_normalized": entity_aliases[entity_id],
                "applicant_party_type_codes_scanned": [1],
                "publication_action_codes_scanned": [42],
                "dataset_date": "2025-01-28",
            }
        )

    return {
        "schema_version": 1,
        "source_family": SIGNAL_FAMILY,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "coverage_definition": (
            "Complete exact-alias scan of the pinned CIPO researcher "
            "TM_Interested_Party dataset for Party Type 1 Applicant, joined to "
            "TM_Event action code 42 Advertised. Later owner/current-owner rows "
            "are deliberately excluded to prevent ownership backdating."
        ),
        "source_metadata": source_metadata,
        "summary": {
            "entity_count": len(entities_payload["entities"]),
            "interested_party_rows_scanned": interested_rows,
            "applicant_rows_scanned": applicant_rows,
            "matched_application_count": len(matched_apps),
            "applicant_match_rows": len(applicant_matches),
            "event_rows_scanned": event_rows,
            "matched_event_rows": matched_event_rows,
            "advertised_evidence_count": len(records),
        },
        "coverage": coverage,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--interested-party-url",
        default=DEFAULT_INTERESTED_PARTY_URL,
    )
    parser.add_argument("--event-url", default=DEFAULT_EVENT_URL)
    parser.add_argument("--cache-dir", default="control-output/cipo-cache")
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    cache = Path(args.cache_dir)
    interested_path = cache / "TM_interested_party_2025-01-28.zip"
    event_path = cache / "TM_event_2025-01-28.zip"

    ssl_context, tls_metadata = build_cipo_ssl_context(cache)
    interested_meta = download(
        args.interested_party_url,
        interested_path,
        ssl_context=ssl_context,
    )
    event_meta = download(
        args.event_url,
        event_path,
        ssl_context=ssl_context,
    )
    payload = collect(
        entities_payload=entities,
        interested_party_zip=interested_path,
        event_zip=event_path,
        source_metadata={
            "dataset_date": "2025-01-28",
            "tls_chain_repair": tls_metadata,
            "interested_party": interested_meta,
            "event": event_meta,
        },
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
