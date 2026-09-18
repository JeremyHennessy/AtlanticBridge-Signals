from __future__ import annotations

import collections
import json
import re
from bs4 import BeautifulSoup

from atlanticbridge.sources.investment_canada import fetch_bucket, parse_index_html

url, html = fetch_bucket("all")
records = parse_index_html(
    html,
    source_url_value=url,
    source_bucket="all",
)

eu_new = [r for r in records if r.is_eu27 and r.is_new_business]

by_year = collections.Counter(r.certification_month[:4] for r in eu_new)
by_country = collections.Counter(r.country_of_ultimate_control for r in eu_new)
by_type = collections.Counter(r.notification_type for r in records)

soup = BeautifulSoup(html, "html.parser")
structural_samples = []
for table in soup.find_all("table"):
    header_text = " ".join(th.get_text(" ", strip=True) for th in table.find_all("th"))
    if "Date Certification" not in header_text or "Notification Type" not in header_text:
        continue
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        month = " ".join(cells[0].get_text(" ", strip=True).split())
        notification_type = " ".join(cells[1].get_text(" ", strip=True).split())
        country = " ".join(cells[3].get_text(" ", strip=True).split())
        if (
            re.fullmatch(r"\d{4}-\d{2}", month)
            and "new business" in notification_type.casefold()
            and country in {
                "Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark",
                "Estonia","Finland","France","Germany","Greece","Hungary","Ireland","Italy",
                "Latvia","Lithuania","Luxembourg","Malta","Netherlands","Poland","Portugal",
                "Romania","Slovakia","Slovenia","Spain","Sweden"
            }
        ):
            structural_samples.append(
                {
                    "month": month,
                    "notification_type": notification_type,
                    "country": country,
                    "investor_text": " ".join(cells[2].get_text(" ", strip=True).split()),
                    "investor_html": str(cells[2])[:2500],
                    "canadian_business_text": " ".join(cells[4].get_text(" ", strip=True).split()),
                    "canadian_business_html": str(cells[4])[:3000],
                }
            )
        if len(structural_samples) >= 20:
            break
    if len(structural_samples) >= 20:
        break

result = {
    "url": url,
    "total_records": len(records),
    "earliest_month": min((r.certification_month for r in records), default=None),
    "latest_month": max((r.certification_month for r in records), default=None),
    "all_records_by_type": dict(sorted(by_type.items())),
    "eu_new_business_records": len(eu_new),
    "eu_new_business_by_year": dict(sorted(by_year.items())),
    "eu_new_business_by_country": dict(sorted(by_country.items())),
    "structural_samples": structural_samples,
}
print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
