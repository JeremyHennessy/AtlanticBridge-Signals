from __future__ import annotations

import csv
import io
import json
import zipfile
from urllib.request import Request, urlopen

SOURCES = {
    "main": "https://opic-cipo.ca/cipo/client_downloads/TM_CSV_2025_01_28/TM_application_main_2025-01-28.zip",
    "interested_party": "https://opic-cipo.ca/cipo/client_downloads/TM_CSV_2025_01_28/TM_interested_party_2025-01-28.zip",
}

result = {}
for label, url in SOURCES.items():
    request = Request(
        url,
        headers={
            "User-Agent": (
                "AtlanticBridge-Signals/0.1 "
                "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
            )
        },
    )
    with urlopen(request, timeout=120) as response:
        raw = response.read()

    item = {"url": url, "bytes": len(raw), "members": []}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in archive.namelist():
            info = archive.getinfo(member)
            member_info = {
                "name": member,
                "uncompressed_bytes": info.file_size,
            }
            if member.lower().endswith(".csv"):
                with archive.open(member) as handle:
                    text = io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace", newline="")
                    sample_text = text.read(512 * 1024)
                reader = csv.reader(io.StringIO(sample_text))
                header = next(reader, [])
                rows = []
                for _ in range(3):
                    row = next(reader, None)
                    if row is None:
                        break
                    rows.append(row)
                member_info["header"] = header
                member_info["column_count"] = len(header)
                member_info["sample_rows"] = rows
            item["members"].append(member_info)
    result[label] = item

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
