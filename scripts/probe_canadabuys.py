from __future__ import annotations

import collections
import csv
import hashlib
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
    csv_status = response.status

text = raw.decode("utf-8-sig", errors="replace")
reader = csv.DictReader(io.StringIO(text))
header = reader.fieldnames or []

row_count = 0
key_counts = collections.Counter()
supplier_countries = collections.Counter()
non_canada_samples = []

for row in reader:
    row_count += 1
    reference = (row.get("referenceNumber-numeroReference") or "").strip()
    amendment = (row.get("amendmentNumber-numeroModification") or "").strip()
    supplier = (row.get("supplierLegalName-nomLegalFournisseur-eng") or "").strip()
    country = (row.get("supplierAddressCountry-fournisseurAdressePays-eng") or "").strip()
    key_counts[(reference, amendment)] += 1
    if country:
        supplier_countries[country] += 1
    if country and country.casefold() != "canada" and len(non_canada_samples) < 10:
        non_canada_samples.append(
            {
                "reference": reference,
                "amendment": amendment,
                "supplier": supplier,
                "country": country,
                "award_date": (row.get("contractAwardDate-dateAttributionContrat") or "").strip(),
                "amount": (row.get("contractAmount-montantContrat") or "").strip(),
                "currency": (row.get("contractCurrency-contratMonnaie") or "").strip(),
            }
        )

duplicate_keys = [
    {"reference": key[0], "amendment": key[1], "count": count}
    for key, count in key_counts.items()
    if count > 1
]

print(
    json.dumps(
        {
            "page_status": page_status,
            "csv_status": csv_status,
            "url": CSV_URL,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content_type": content_type,
            "cookies": [cookie.name for cookie in jar],
            "column_count": len(header),
            "header": header,
            "row_count": row_count,
            "unique_reference_amendment_keys": len(key_counts),
            "duplicate_reference_amendment_key_count": len(duplicate_keys),
            "duplicate_reference_amendment_examples": duplicate_keys[:10],
            "top_supplier_countries": supplier_countries.most_common(20),
            "non_canada_samples": non_canada_samples,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
