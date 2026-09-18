from __future__ import annotations

import csv
import io
import json
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

WDS_URL = "https://www150.statcan.gc.ca/t1/wds/rest/getFullTableDownloadCSV/12100173/en"
EU27 = {
    "Austria","Belgium","Bulgaria","Croatia","Cyprus","Czechia","Denmark","Estonia",
    "Finland","France","Germany","Greece","Hungary","Ireland","Italy","Latvia",
    "Lithuania","Luxembourg","Malta","Netherlands","Poland","Portugal","Romania",
    "Slovakia","Slovenia","Spain","Sweden",
}
UA = "AtlanticBridge-Signals/0.1 (public-data research; https://github.com/JeremyHennessy/AtlanticBridge-Signals)"

with urlopen(Request(WDS_URL, headers={"User-Agent": UA}), timeout=60) as response:
    meta = json.load(response)
if meta.get("status") != "SUCCESS" or not meta.get("object"):
    raise RuntimeError(f"StatsCan WDS did not return a download URL: {meta!r}")

download_url = meta["object"]
with tempfile.TemporaryDirectory(prefix="atlanticbridge-statcan-annual-") as temp_dir:
    archive_path = Path(temp_dir) / "statcan-annual.zip"
    with urlopen(Request(download_url, headers={"User-Agent": UA}), timeout=180) as response, archive_path.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)

    archive_bytes = archive_path.stat().st_size
    with zipfile.ZipFile(archive_path) as zf:
        members = zf.namelist()
        csv_members = [m for m in members if m.lower().endswith(".csv")]
        data_member = next((m for m in csv_members if "meta" not in m.lower()), None)
        if not data_member:
            raise RuntimeError(f"No data CSV found in archive: {members!r}")

        with zf.open(data_member) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline="")
            reader = csv.DictReader(text)
            header = reader.fieldnames or []

            total_rows = 0
            latest_ref = ""
            country_field = "Trading partner"
            if country_field not in header:
                raise RuntimeError(
                    f"Expected StatsCan Trading partner field; received {header!r}"
                )

            provinces = Counter()
            countries = Counter()
            trade_types = Counter()
            commodities = Counter()
            ref_dates = Counter()
            ns_eu_rows = []

            for row in reader:
                total_rows += 1
                ref = (row.get("REF_DATE") or "").strip()
                province = (row.get("GEO") or "").strip()
                country = (row.get(country_field) or "").strip()
                trade = (row.get("Trade") or "").strip()
                commodity_field = next(
                    (
                        field for field in header
                        if "North American Product Classification System" in field
                    ),
                    None,
                )
                commodity = (row.get(commodity_field) or "").strip() if commodity_field else ""

                if ref:
                    ref_dates[ref] += 1
                    latest_ref = max(latest_ref, ref)
                if province:
                    provinces[province] += 1
                if country:
                    countries[country] += 1
                if trade:
                    trade_types[trade] += 1
                if commodity:
                    commodities[commodity] += 1

                if province == "Nova Scotia" and country in EU27:
                    ns_eu_rows.append({
                        "REF_DATE": ref,
                        "GEO": province,
                        "Country": country,
                        "Trade": trade,
                        "NAPCS": commodity,
                        "VALUE": (row.get("VALUE") or "").strip(),
                        "UOM": (row.get("UOM") or "").strip(),
                        "SCALAR_FACTOR": (row.get("SCALAR_FACTOR") or "").strip(),
                    })

    latest_ns_eu = [row for row in ns_eu_rows if row["REF_DATE"] == latest_ref]
    result = {
        "wds_url": WDS_URL,
        "download_url": download_url,
        "archive_bytes": archive_bytes,
        "members": members,
        "data_member": data_member,
        "column_count": len(header),
        "header": header,
        "country_field": country_field,
        "total_rows": total_rows,
        "earliest_ref_date": min(ref_dates) if ref_dates else None,
        "latest_ref_date": latest_ref or None,
        "province_values": sorted(provinces),
        "eu27_countries_present": sorted(EU27.intersection(countries)),
        "missing_eu27_countries": sorted(EU27.difference(countries)),
        "trade_values": sorted(trade_types),
        "commodity_values": sorted(commodities),
        "latest_ns_eu_row_count": len(latest_ns_eu),
        "latest_ns_eu_by_country": dict(Counter(row["Country"] for row in latest_ns_eu)),
        "latest_ns_eu_by_trade": dict(Counter(row["Trade"] for row in latest_ns_eu)),
        "latest_ns_eu_sample": latest_ns_eu[:25],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
