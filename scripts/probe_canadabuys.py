from __future__ import annotations

import csv
import io
import json
from urllib.request import Request, urlopen

URL = "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv"

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
    content_type = response.headers.get_content_type()
    charset = response.headers.get_content_charset() or "utf-8"

text = raw.decode(charset, errors="replace")
reader = csv.reader(io.StringIO(text))
header = next(reader, [])
rows = []
for _ in range(5):
    row = next(reader, None)
    if row is None:
        break
    rows.append(row)

print(
    json.dumps(
        {
            "url": URL,
            "bytes": len(raw),
            "content_type": content_type,
            "column_count": len(header),
            "header": header,
            "sample_rows": rows,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
