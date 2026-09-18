from __future__ import annotations

import collections
import hashlib
import json
import re
import time
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from atlanticbridge.constants import EU27

BASE = (
    "https://ised-isde.canada.ca/site/investment-canada-act/en/"
    "search/decisions-and-notification-index"
)
BUCKETS = [str(x) for x in range(10)] + [chr(code) for code in range(ord("a"), ord("z") + 1)]
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as response:
        return response.read().decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )


def clean(value: str) -> str:
    return " ".join(value.split()).strip()


def max_page_index(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    indexes = [0]
    for link in soup.find_all("a", href=True):
        query = parse_qs(urlparse(link["href"]).query)
        for raw in query.get("page", []):
            try:
                indexes.append(int(raw))
            except ValueError:
                pass
    return max(indexes)


def row_records(html: str, *, bucket: str, page: int):
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.find_all("table"):
        header = clean(" ".join(th.get_text(" ", strip=True) for th in table.find_all("th")))
        if "Date Certification" not in header or "Notification Type" not in header:
            continue

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 5:
                continue

            month = clean(cells[0].get_text(" ", strip=True))
            if not re.fullmatch(r"\d{4}-\d{2}", month):
                continue

            notification_type = clean(cells[1].get_text(" ", strip=True))
            investor_text = clean(cells[2].get_text(" ", strip=True))
            country = clean(cells[3].get_text(" ", strip=True))
            business_text = clean(cells[4].get_text(" ", strip=True))

            investor_article = cells[2].find("article", attrs={"data-history-node-id": True})
            investor_node_id = (
                str(investor_article.get("data-history-node-id"))
                if investor_article is not None
                else ""
            )
            business_node_ids = tuple(
                str(article.get("data-history-node-id"))
                for article in cells[4].find_all(
                    "article",
                    attrs={"data-history-node-id": True},
                )
            )
            investor_name_node = cells[2].select_one(".field--name-title .field--item, .field--name-title")
            investor_name = clean(investor_name_node.get_text(" ", strip=True)) if investor_name_node else ""
            business_names = tuple(
                clean(node.get_text(" ", strip=True))
                for node in cells[4].select(".field--name-title")
            )

            raw_material = "\x1f".join(
                [month, notification_type, investor_text, country, business_text]
            )
            raw_hash = hashlib.sha256(raw_material.encode("utf-8")).hexdigest()

            structural_material = "\x1f".join(
                [
                    month,
                    notification_type,
                    investor_node_id,
                    country,
                    ",".join(business_node_ids),
                ]
            )
            structural_key = hashlib.sha256(
                structural_material.encode("utf-8")
            ).hexdigest()

            yield {
                "bucket": bucket,
                "page": page,
                "month": month,
                "notification_type": notification_type,
                "investor_text": investor_text,
                "investor_name": investor_name,
                "investor_node_id": investor_node_id,
                "country": country,
                "business_text": business_text,
                "business_names": business_names,
                "business_node_ids": business_node_ids,
                "raw_hash": raw_hash,
                "structural_key": structural_key,
            }


bucket_summary = {}
all_records = []

for index, bucket in enumerate(BUCKETS):
    first_url = f"{BASE}/{bucket}"
    first_html = fetch(first_url)
    last_page = max_page_index(first_html)

    bucket_records = []
    for page in range(last_page + 1):
        html = first_html if page == 0 else fetch(f"{first_url}?page={page}")
        rows = list(row_records(html, bucket=bucket, page=page))
        bucket_records.extend(rows)
        if page < last_page:
            time.sleep(0.05)

    all_records.extend(bucket_records)
    bucket_summary[bucket] = {
        "last_page_index": last_page,
        "pages": last_page + 1,
        "records": len(bucket_records),
        "earliest_month": min((r["month"] for r in bucket_records), default=None),
        "latest_month": max((r["month"] for r in bucket_records), default=None),
    }
    if index < len(BUCKETS) - 1:
        time.sleep(0.05)

raw_counts = collections.Counter(r["raw_hash"] for r in all_records)
structural_counts = collections.Counter(r["structural_key"] for r in all_records)
node_missing = [r for r in all_records if not r["investor_node_id"]]

eu_new = [
    r
    for r in all_records
    if r["country"] in EU27 and "new business" in r["notification_type"].casefold()
]
eu_new_by_year = collections.Counter(r["month"][:4] for r in eu_new)
eu_new_by_country = collections.Counter(r["country"] for r in eu_new)

duplicate_raw = [key for key, count in raw_counts.items() if count > 1]
duplicate_structural = [key for key, count in structural_counts.items() if count > 1]

duplicate_examples = []
for key in duplicate_raw[:20]:
    matches = [r for r in all_records if r["raw_hash"] == key]
    duplicate_examples.append(
        {
            "count": len(matches),
            "months": sorted({r["month"] for r in matches}),
            "buckets_pages": [(r["bucket"], r["page"]) for r in matches],
            "investor_name": matches[0]["investor_name"],
            "investor_node_ids": sorted({r["investor_node_id"] for r in matches}),
            "business_node_ids": sorted({x for r in matches for x in r["business_node_ids"]}),
            "notification_type": matches[0]["notification_type"],
            "country": matches[0]["country"],
        }
    )

print(
    json.dumps(
        {
            "bucket_summary": bucket_summary,
            "total_records": len(all_records),
            "earliest_month": min((r["month"] for r in all_records), default=None),
            "latest_month": max((r["month"] for r in all_records), default=None),
            "unique_raw_records": len(raw_counts),
            "duplicate_raw_hashes": len(duplicate_raw),
            "unique_structural_keys": len(structural_counts),
            "duplicate_structural_keys": len(duplicate_structural),
            "records_missing_investor_node_id": len(node_missing),
            "eu_new_business_records": len(eu_new),
            "eu_new_business_by_year": dict(sorted(eu_new_by_year.items())),
            "eu_new_business_by_country": dict(sorted(eu_new_by_country.items())),
            "duplicate_examples": duplicate_examples,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
