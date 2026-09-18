from __future__ import annotations

import collections
import csv
import io
import json
import zipfile
from urllib.request import Request, urlopen

URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip"

EU27 = {
    "AT","BE","BG","HR","CY","CZ","DK","EE","FI","FR","DE","GR","HU","IE","IT",
    "LV","LT","LU","MT","NL","PL","PT","RO","SK","SI","ES","SE",
}

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

    with archive.open("organization.csv") as handle:
        text_handle = io.TextIOWrapper(handle, encoding="utf-8-sig", errors="replace", newline="")
        reader = csv.DictReader(text_handle, delimiter=";")
        rows = list(reader)

    ca_rows = [row for row in rows if row["country"].strip() == "CA"]
    ca_projects = {row["projectID"].strip() for row in ca_rows if row["projectID"].strip()}
    ca_orgs = {row["organisationID"].strip() for row in ca_rows if row["organisationID"].strip()}

    rows_by_project = collections.defaultdict(list)
    for row in rows:
        project_id = row["projectID"].strip()
        if project_id:
            rows_by_project[project_id].append(row)

    shared_eu_rows = [
        row
        for project_id in ca_projects
        for row in rows_by_project[project_id]
        if row["country"].strip() in EU27
    ]
    shared_eu_orgs = {
        row["organisationID"].strip()
        for row in shared_eu_rows
        if row["organisationID"].strip()
    }
    shared_eu_prc_orgs = {
        row["organisationID"].strip()
        for row in shared_eu_rows
        if row["organisationID"].strip() and row["activityType"].strip() == "PRC"
    }

    result["relationship_probe"] = {
        "organization_rows": len(rows),
        "canada_participation_rows": len(ca_rows),
        "canada_unique_projects": len(ca_projects),
        "canada_unique_organizations": len(ca_orgs),
        "canada_activity_types": dict(collections.Counter(row["activityType"].strip() for row in ca_rows)),
        "eu_participation_rows_on_canada_projects": len(shared_eu_rows),
        "eu_unique_organizations_on_canada_projects": len(shared_eu_orgs),
        "eu_prc_unique_organizations_on_canada_projects": len(shared_eu_prc_orgs),
        "eu_activity_types_on_canada_projects": dict(
            collections.Counter(row["activityType"].strip() for row in shared_eu_rows)
        ),
        "eu_countries_on_canada_projects": dict(
            collections.Counter(row["country"].strip() for row in shared_eu_rows)
        ),
    }

print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
