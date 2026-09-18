from __future__ import annotations

import csv
import http.cookiejar
import io
import json
from urllib.request import HTTPCookieProcessor, Request, build_opener

PAGE_URL = "https://canadabuys.canada.ca/en/procurement-and-contracting-data"
CSV_URL = "https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv"

jar = http.cookiejar.CookieJar()
opener = build_opener(HTTPCookieProcessor(jar))
headers = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36 "
        "AtlanticBridge-Signals/0.1"
    ),
    "Accept-Language": "en-CA,en;q=0.9",
}

with opener.open(Request(PAGE_URL, headers=headers), timeout=60) as response:
    page_status = response.status
    response.read(1)

request = Request(
    CSV_URL,
    headers={
        **headers,
        "Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8",
        "Referer": PAGE_URL,
    },
)
with opener.open(request, timeout=120) as response:
    raw = response.read()
    content_type = response.headers.get_content_type()
    charset = response.headers.get_content_charset() or "utf-8"
    csv_status = response.status

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
            "page_status": page_status,
            "csv_status": csv_status,
            "url": CSV_URL,
            "bytes": len(raw),
            "content_type": content_type,
            "cookies": [cookie.name for cookie in jar],
            "column_count": len(header),
            "header": header,
            "sample_rows": rows,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
