from __future__ import annotations

import csv
import io
import json
import zipfile
from urllib.request import Request, urlopen

URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"

request = Request(
    URL,
    headers={
        "User-Agent": (
            "AtlanticBridge-Signals/0.1 "
            "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
        )
    },
)

with urlopen(request, timeout=120) as response:
    raw = response.read()

result = {
    "url": URL,
    "bytes": len(raw),
    "members": [],
}

with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    for member in archive.namelist():
        info = archive.getinfo(member)
        entry = {
            "name": member,
            "uncompressed_bytes": info.file_size,
        }
        if member.lower().endswith(".csv"):
            with archive.open(member) as handle:
                text_handle = io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace", newline="")
                reader = csv.reader(text_handle, delimiter=";")
                header = next(reader, [])
                sample = next(reader, [])
                entry["column_count"] = len(header)
                entry["header"] = header
                entry["sample_nonempty_columns"] = [
                    header[index]
                    for index, value in enumerate(sample)
                    if index < len(header) and value.strip()
                ]
        result["members"].append(entry)

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
