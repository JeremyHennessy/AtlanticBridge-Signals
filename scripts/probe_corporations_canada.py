from __future__ import annotations

import csv
import io
import json
from urllib.request import Request, urlopen

URL = "https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv"

request = Request(
    URL,
    headers={
        "User-Agent": (
            "AtlanticBridge-Signals/0.1 "
            "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
        )
    },
)

with urlopen(request, timeout=60) as response:
    raw = response.read()

text = raw.decode("utf-8-sig", errors="replace")
reader = csv.reader(io.StringIO(text))
header = next(reader)
sample = next(reader, [])

print(
    json.dumps(
        {
            "url": URL,
            "bytes": len(raw),
            "column_count": len(header),
            "header": header,
            "sample_nonempty_columns": [
                header[index]
                for index, value in enumerate(sample)
                if index < len(header) and value.strip()
            ],
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
