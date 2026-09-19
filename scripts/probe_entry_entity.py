from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from atlanticbridge.sources.investment_canada import crawl_investment_canada_history

ACTIVE_URL = "https://d4bf66bykfyaf.cloudfront.net/corporations-active-cbca-en.csv"
INACTIVE_URL = "https://d4bf66bykfyaf.cloudfront.net/corporations-inactive-or-dissolved-cbca-en.csv"
DETAIL_BASE = "https://ised-isde.canada.ca/cc/lgcy/fdrlCrpDtls.html"
UA = (
    "AtlanticBridge-Signals/0.1 "
    "(public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"
)
START = "2019-01"
END = "2025-12"
DETAIL_SAMPLE_LIMIT = 12


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def clean(value: str) -> str:
    return " ".join((value or "").split()).strip()


def business_rows(record):
    try:
        rows = json.loads(record.canadian_businesses_json)
    except json.JSONDecodeError:
        return []
    return [row for row in rows if isinstance(row, dict)]


def fetch_csv(url: str, destination: Path) -> tuple[int, list[str]]:
    req = Request(url, headers={"User-Agent": UA})
    size = 0
    with urlopen(req, timeout=180) as response, destination.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            size += len(chunk)

    with destination.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
    return size, header


def iter_corporations(path: Path, source_state: str):
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            corporation_number = clean(row.get("Corporation number", ""))
            if not corporation_number:
                continue
            yield {
                "corporation_number": corporation_number,
                "business_number": clean(row.get("Business number (BN)", "")),
                "name1": clean(row.get("Corporate name - form 1", "")),
                "name2": clean(row.get("Corporate name - form 2", "")),
                "status": clean(row.get("Status", "")),
                "status_detail": clean(row.get("Status Detail", "")),
                "city": clean(row.get("City/town", "")),
                "province": clean(row.get("Province/territory", "")),
                "country": clean(row.get("Country", "")),
                "anniversary_date": clean(row.get("Anniversary date", "")),
                "source_state": source_state,
            }


def province_matches(source_admin: str, corp_province: str) -> bool:
    source = clean(source_admin).casefold()
    corp = clean(corp_province).casefold()
    if not source or not corp:
        return False
    aliases = {
        "ns": "nova scotia",
        "on": "ontario",
        "qc": "quebec",
        "quebec": "quebec",
        "bc": "british columbia",
        "ab": "alberta",
        "mb": "manitoba",
        "sk": "saskatchewan",
        "nb": "new brunswick",
        "nl": "newfoundland and labrador",
        "pe": "prince edward island",
        "pei": "prince edward island",
        "nt": "northwest territories",
        "nu": "nunavut",
        "yt": "yukon",
    }
    source = aliases.get(source, source)
    corp = aliases.get(corp, corp)
    return source == corp


def detail_url(corporation_number: str) -> str:
    return (
        f"{DETAIL_BASE}?corpId={corporation_number.replace('-', '')}&lang=eng"
    )


def parse_detail(corporation_number: str) -> dict:
    url = detail_url(corporation_number)
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=60) as response:
        html = response.read().decode(
            response.headers.get_content_charset() or "utf-8",
            errors="replace",
        )
    soup = BeautifulSoup(html, "html.parser")
    text = clean(soup.get_text(" ", strip=True))

    corp_name = ""
    label = soup.find(string=re.compile(r"Corporate name:", re.I))
    if label:
        parent = label.parent
        if parent:
            sibling = parent.find_next()
            if sibling:
                corp_name = clean(sibling.get_text(" ", strip=True))

    cert_match = re.search(
        r"Certificate of (?:Incorporation|Amalgamation|Continuance)\s*\|\s*"
        r"(\d{4}-\d{2}-\d{2})",
        text,
        flags=re.I,
    )
    if cert_match is None:
        cert_match = re.search(
            r"(?:Certificate of Incorporation|Certificate of Amalgamation|"
            r"Certificate of Continuance)\s+(\d{4}-\d{2}-\d{2})",
            text,
            flags=re.I,
        )

    return {
        "url": url,
        "html_bytes": len(html.encode("utf-8")),
        "corporate_name": corp_name,
        "certificate_date": cert_match.group(1) if cert_match else "",
        "certificate_found": cert_match is not None,
    }


crawl = crawl_investment_canada_history(workers=4)
cohort = [
    record
    for record in crawl.records
    if record.is_eu27
    and record.is_new_business
    and START <= record.certification_month <= END
]

with tempfile.TemporaryDirectory(prefix="atlanticbridge-entry-entity-") as temp_dir:
    temp = Path(temp_dir)
    active_path = temp / "active.csv"
    inactive_path = temp / "inactive.csv"
    active_bytes, active_header = fetch_csv(ACTIVE_URL, active_path)
    inactive_bytes, inactive_header = fetch_csv(INACTIVE_URL, inactive_path)

    corporations = [
        *iter_corporations(active_path, "ACTIVE"),
        *iter_corporations(inactive_path, "INACTIVE"),
    ]

index = defaultdict(list)
for corp in corporations:
    for name in (corp["name1"], corp["name2"]):
        key = norm(name)
        if key:
            index[key].append(corp)

rows = []
status_counts = Counter()
matched_corp_numbers = Counter()

for record in cohort:
    candidates_by_number = {}
    source_businesses = business_rows(record)

    for business in source_businesses:
        name = clean(business.get("name", ""))
        key = norm(name)
        if not key:
            continue
        for corp in index.get(key, []):
            item = dict(corp)
            item["matched_business_name"] = name
            item["investment_locality"] = clean(business.get("locality", ""))
            item["investment_admin_area"] = clean(
                business.get("administrative_area", "")
            )
            item["province_match"] = province_matches(
                item["investment_admin_area"],
                corp["province"],
            )
            item["city_match"] = (
                bool(item["investment_locality"])
                and bool(corp["city"])
                and norm(item["investment_locality"]) == norm(corp["city"])
            )
            candidates_by_number[corp["corporation_number"]] = item

    candidates = list(candidates_by_number.values())
    strong = [
        item
        for item in candidates
        if item["province_match"] or item["city_match"]
    ]

    if len(candidates) == 0:
        status = "NO_FEDERAL_EXACT_MATCH"
        selected = None
    elif len(candidates) == 1:
        status = (
            "UNIQUE_EXACT_GEO"
            if strong
            else "UNIQUE_EXACT_NAME_ONLY"
        )
        selected = candidates[0]
    elif len(strong) == 1:
        status = "MULTI_EXACT_ONE_GEO"
        selected = strong[0]
    else:
        status = "AMBIGUOUS_EXACT"
        selected = None

    status_counts[status] += 1
    if selected:
        matched_corp_numbers[selected["corporation_number"]] += 1

    rows.append(
        {
            "record_id": record.record_id,
            "certification_month": record.certification_month,
            "country": record.country_of_ultimate_control,
            "investor_name": record.investor_name,
            "investor_locality": record.investor_locality,
            "businesses": source_businesses,
            "match_status": status,
            "candidate_count": len(candidates),
            "strong_candidate_count": len(strong),
            "selected": selected,
        }
    )

reviewable = [
    row for row in rows
    if row["selected"] is not None
]
reviewable.sort(
    key=lambda row: (
        row["certification_month"],
        row["country"],
        row["record_id"],
    ),
    reverse=True,
)

detail_results = []
for row in reviewable[:DETAIL_SAMPLE_LIMIT]:
    selected = row["selected"]
    assert selected is not None
    detail = parse_detail(selected["corporation_number"])
    outcome_date = date.fromisoformat(row["certification_month"] + "-01")
    certificate_date = (
        date.fromisoformat(detail["certificate_date"])
        if detail["certificate_date"]
        else None
    )
    lead_days = (
        (outcome_date - certificate_date).days
        if certificate_date is not None
        else None
    )
    detail_results.append(
        {
            "record_id": row["record_id"],
            "certification_month": row["certification_month"],
            "country": row["country"],
            "investor_name": row["investor_name"],
            "matched_business_name": selected["matched_business_name"],
            "corporation_number": selected["corporation_number"],
            "source_state": selected["source_state"],
            "bulk_city": selected["city"],
            "bulk_province": selected["province"],
            "province_match": selected["province_match"],
            "city_match": selected["city_match"],
            "detail_url": detail["url"],
            "certificate_date": detail["certificate_date"],
            "certificate_found": detail["certificate_found"],
            "lead_days_to_outcome_month_start": lead_days,
        }
    )

gold_candidates = reviewable[:100]

print(
    json.dumps(
        {
            "window": {"start": START, "end": END},
            "cohort_records": len(cohort),
            "active_source_bytes": active_bytes,
            "inactive_source_bytes": inactive_bytes,
            "active_header": active_header,
            "inactive_header": inactive_header,
            "federal_corporation_rows": len(corporations),
            "match_status_counts": dict(sorted(status_counts.items())),
            "reviewable_unique_or_geo_resolved": len(reviewable),
            "reviewable_share_percent": round(
                100 * len(reviewable) / len(cohort),
                2,
            ) if cohort else 0,
            "unique_selected_corporation_numbers": len(matched_corp_numbers),
            "selected_corporation_reuse_count": sum(
                1 for count in matched_corp_numbers.values() if count > 1
            ),
            "gold_candidate_count": len(gold_candidates),
            "gold_candidates": gold_candidates,
            "detail_sample": detail_results,
        },
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )
)
