from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import ssl
from urllib.request import Request, urlopen
from zipfile import ZipFile


SOURCE_URL = (
    "https://opic-cipo.ca/cipo/client_downloads/Trademarks_Historical_2025_06/"
    "CA-TMK-GLOBAL_2025-06-14_1794865_1805452_087.zip"
)
RAPIDSSL_INTERMEDIATE_URL = (
    "https://cacerts.digicert.com/RapidSSLTLSRSACAG1.crt.pem"
)
RAPIDSSL_INTERMEDIATE_SHA256 = (
    "4422e963ee53cd58cc9f85cd40bf5ffec0095fdf1a154535661c1c06bcadc69b"
)
TARGET_APPLICATION = "1799092"
USER_AGENT = (
    "AtlanticBridge-Signals/0.1 "
    "(historical CIPO XML validation; "
    "https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


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
            f"unexpected RapidSSL intermediate fingerprint {fingerprint}"
        )

    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(pem_path))
    return context


def download(
    url: str,
    destination: Path,
    *,
    context: ssl.SSLContext,
) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    byte_count = 0
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/zip,application/octet-stream,*/*;q=0.8",
        },
    )
    temp = destination.with_suffix(".part")
    try:
        with urlopen(
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
        "url": url,
        "sha256": digest.hexdigest(),
        "bytes": byte_count,
    }


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def inspect_target(archive_path: Path) -> dict[str, object]:
    from xml.etree import ElementTree as ET

    candidates: list[str] = []
    with ZipFile(archive_path) as archive:
        names = [
            name
            for name in archive.namelist()
            if not name.endswith("/") and name.lower().endswith(".xml")
        ]
        target_token = TARGET_APPLICATION.casefold()
        candidates = [
            name for name in names
            if target_token in Path(name).name.casefold()
        ]

        if not candidates:
            for name in names:
                with archive.open(name) as raw:
                    data = raw.read()
                if TARGET_APPLICATION.encode("ascii") in data:
                    candidates.append(name)
                    break

        if len(candidates) != 1:
            raise ValueError(
                f"expected exactly one target XML for {TARGET_APPLICATION}; "
                f"found {candidates!r}"
            )

        entry = candidates[0]
        data = archive.read(entry)

    root = ET.fromstring(data)
    interesting = []
    for elem in root.iter():
        text = " ".join((elem.text or "").split())
        if not text:
            continue
        folded_tag = local_name(elem.tag).casefold()
        folded_text = text.casefold()
        if (
            TARGET_APPLICATION in text
            or "sioo" in folded_text
            or "woodprotection" in folded_text
            or "2018-12-12" in text
            or "advertis" in folded_text
            or "applicant" in folded_tag
            or "party" in folded_tag
            or "action" in folded_tag
        ):
            interesting.append(
                {
                    "tag": local_name(elem.tag),
                    "text": text[:1000],
                }
            )

    xml_text = data.decode("utf-8", errors="replace")
    return {
        "target_application": TARGET_APPLICATION,
        "archive_entry": entry,
        "xml_sha256": hashlib.sha256(data).hexdigest(),
        "xml_bytes": len(data),
        "contains_application_number": TARGET_APPLICATION in xml_text,
        "contains_sioo_owner_text": (
            "sioo woodprotection ab" in xml_text.casefold()
            or "sioo wood protection" in xml_text.casefold()
        ),
        "contains_advertised_date": "2018-12-12" in xml_text,
        "interesting_text_nodes": interesting,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cache-dir",
        default="control-output/cipo-xml-gap-cache",
    )
    parser.add_argument(
        "--output",
        default="control-output/cipo-xml-gap-proof.json",
    )
    args = parser.parse_args()

    cache = Path(args.cache_dir)
    context = build_ssl_context(cache)
    archive_path = cache / Path(SOURCE_URL).name
    if archive_path.exists():
        digest = hashlib.sha256()
        byte_count = 0
        with archive_path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                byte_count += len(chunk)
        download_meta = {
            "url": SOURCE_URL,
            "sha256": digest.hexdigest(),
            "bytes": byte_count,
            "cache_hit": True,
        }
    else:
        download_meta = download(
            SOURCE_URL,
            archive_path,
            context=context,
        )
        download_meta["cache_hit"] = False

    proof = inspect_target(archive_path)
    payload = {
        "schema_version": 1,
        "purpose": (
            "Test whether CIPO's annual full historical XML collection contains "
            "the known Sioo application omitted by the researcher CSV/search "
            "source used in Backtest 001."
        ),
        "source_archive": download_meta,
        "proof": proof,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "source_archive": download_meta,
                "proof": {
                    key: value
                    for key, value in proof.items()
                    if key != "interesting_text_nodes"
                },
                "interesting_text_nodes_count": len(
                    proof["interesting_text_nodes"]
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
