"""Offline, source-local CORDIS research co-participation, never expansion leads."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import zipfile

from .sources.cordis import EU27_ISO2

HORIZON_ARCHIVE_URL = "https://cordis.europa.eu/data/cordis-HORIZONprojects-json.zip"

LICENCE_URL = "https://eur-lex.europa.eu/eli/dec/2011/833/oj"
CATALOGUE_URL = "https://data.europa.eu/data/datasets/cordis-eu-research-projects-under-horizon-europe-2021-2027"
MAX_ARCHIVE_BYTES = 192 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ROWS = 1000000
NOTICE = (
    "CORDIS lists these organisations on the same EU-funded research project. "
    "Co-participation does not establish a direct bilateral partnership, Canadian expansion, "
    "first entry, current hiring, an open commercial requirement or a qualified lead. "
    "EU-27 location is not ultimate ownership. Dates are project/update clocks, not first publication."
)
MILITARY = re.compile(r"\b(?:military|armaments?|weapons?|armed forces|army|navy|air force|defen[cs]e)\b", re.I)
AMBIGUOUS = re.compile(r"\b(?:dual[- ]use|cbrn)\b", re.I)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _instant(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("Invalid observation timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Observation timestamp requires a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _day(value):
    try:
        return date.fromisoformat(value) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None
    except (ValueError, TypeError):
        return None


def _text(value, limit=16000):
    if not isinstance(value, str) or len(value) > limit or "\x00" in value:
        raise ValueError("Invalid or oversized source field")
    return value.strip()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("Non-finite JSON constant")


def _project_rows(archive):
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)) or (len(names) - int("documentation.zip" in names)) > MAX_ROWS:
        raise ValueError("Duplicate or excessive CORDIS archive members")
    if sum(info.file_size for info in infos) > MAX_EXPANDED_BYTES:
        raise ValueError("CORDIS expanded archive is too large")
    for info in infos:
        if info.file_size > MAX_MEMBER_BYTES or info.flag_bits & 1:
            raise ValueError("Unsupported CORDIS member size or encryption")
        if info.filename == "documentation.zip":
            continue
        match = re.fullmatch(r"project-rcn-([0-9]+)_en\.json", info.filename)
        if not match:
            raise ValueError("Unexpected CORDIS JSON archive member")
        row = json.loads(archive.read(info).decode("utf-8-sig"), object_pairs_hook=_object, parse_constant=_reject_constant)
        if not isinstance(row, dict) or row.get("contenttype") != "project" or row.get("language") != "en" or row.get("rcn") != match[1]:
            raise ValueError("CORDIS JSON project schema or member identity changed")
        yield row


def _list(value, name):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Invalid CORDIS " + name)
    return value


def _organisation(row):
    attrs = row.get("attributes")
    address = row.get("address")
    relations = row.get("relations")
    if not all(isinstance(value, dict) for value in (attrs, address, relations)):
        raise ValueError("Invalid CORDIS organisation structure")
    categories = _list(relations.get("categories", []), "organisation categories")
    codes = set()
    for cat in categories:
        ca = cat.get("attributes", {})
        if not isinstance(ca, dict):
            raise ValueError("Invalid category attributes")
        if ca.get("classification") == "organizationActivityType":
            if ca.get("type") != "relatedOrganizationActivityType":
                raise ValueError("Organisation activity relation changed")
            code = _text(cat.get("code"), 30)
            if code not in {"/PRC", "/HES", "/REC", "/PUB", "/OTH"}:
                raise ValueError("Invalid organisation activity code")
            codes.add(code[1:])
    if len(codes) != 1:
        raise ValueError("Missing or conflicting organisation activity codes")
    country_raw = _text(address.get("country", ""), 2)
    country = "GR" if country_raw == "EL" else country_raw
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("Invalid country code")
    if attrs.get("type") not in {"participant", "coordinator", "associatedPartner", "thirdParty"}:
        raise ValueError("Unknown CORDIS organisation role")
    if attrs.get("terminated") not in {"true", "false"}:
        raise ValueError("Missing or invalid participation-termination flag")
    # PIC is source-local identity, not verified corporate or parent identity.
    return {
        "source_record_sha256": _sha(row),
        "source_organisation_id": _text(row.get("id", ""), 80) or None,
        "name": _text(row.get("legalName", ""), 1000),
        "country": country,
        "country_raw": country_raw,
        "activity_type_raw": next(iter(codes), ""),
        "role_raw": _text(attrs.get("type", ""), 100),
        "end_of_participation_raw": _text(attrs.get("terminated", ""), 30),
        "active_fpa_raw": _text(attrs.get("active", ""), 30),
        "source_content_update_raw": _text(row.get("contentUpdateDate", ""), 80),
    }


def build_research_payload(archive_path, receipt, *, as_of_date=None):
    """Read an already acquired official archive; performs no network or DB writes.

    The receipt is an acquisition record, not authentication or source attestation.
    Only its exact allowlisted source, hash, size and observation clock are accepted.
    """
    if not isinstance(receipt, dict) or receipt.get("source_url") != HORIZON_ARCHIVE_URL or receipt.get("final_url") != HORIZON_ARCHIVE_URL:
        raise ValueError("Receipt must identify the exact reviewed CORDIS source")
    if type(receipt.get("http_status")) is not int or receipt["http_status"] != 200:
        raise ValueError("A complete successful source acquisition is required")
    sha = receipt.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid source SHA-256")
    observed = _instant(receipt.get("retrieved_at"))
    day = as_of_date or datetime.now(timezone.utc).date()
    if type(day) is not date:
        raise ValueError("as_of_date must be a date")
    archive_path = Path(archive_path)
    size = archive_path.stat().st_size
    if size > MAX_ARCHIVE_BYTES or type(receipt.get("bytes")) is not int or receipt["bytes"] != size:
        raise ValueError("Source size does not match its receipt or limit")
    digest = hashlib.sha256()
    with archive_path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != sha:
        raise ValueError("Source bytes do not match their receipt")

    if datetime.fromisoformat(observed).date() > day:
        raise ValueError("Snapshot was not observed by the requested as-of date")
    records, held, all_project_ids = [], [], set()
    input_organisations = canada_project_count = eu_canada_project_count = candidate_count = 0
    with zipfile.ZipFile(archive_path) as archive:
        for p in _project_rows(archive):
            identifier = _text(p.get("id"), 12)
            if not re.fullmatch(r"[0-9]{1,12}", identifier) or identifier in all_project_ids:
                raise ValueError("Invalid or duplicate CORDIS project ID")
            all_project_ids.add(identifier)
            relations = p.get("relations")
            if not isinstance(relations, dict):
                raise ValueError("Missing CORDIS project relations")
            people, seen_orgs = [], set()
            for row in _list(relations.get("associations"), "project associations"):
                if row.get("contenttype") not in {"organization", "article", "call", "programme", "result", "webLink", "webItem"}:
                    raise ValueError("Unknown CORDIS association type")
                if row["contenttype"] != "organization":
                    continue
                input_organisations += 1
                item = _organisation(row)
                if item["source_record_sha256"] in seen_orgs:
                    raise ValueError("Duplicate CORDIS organisation row")
                seen_orgs.add(item["source_record_sha256"])
                if item["country"] == "CA" or item["country"] in EU27_ISO2:
                    if not item["name"]:
                        raise ValueError("Relevant organisation has no name")
                    people.append(item)
            ca = [o for o in people if o["country"] == "CA"]
            eu = [o for o in people if o["country"] in EU27_ISO2]
            prc = [o for o in eu if o["activity_type_raw"] == "PRC"]
            canada_project_count += bool(ca)
            eu_canada_project_count += bool(ca and eu)
            if not ca or not prc:
                continue
            candidate_count += 1
            scope_text = " ".join(_text(p.get(k, ""), 100000) for k in ("title", "objective", "keywords"))
            reason = "EXPLICIT_MILITARY_MARKER" if MILITARY.search(scope_text) else "AMBIGUOUS_CIVILIAN_SCOPE" if AMBIGUOUS.search(scope_text) else None
            if reason:
                held.append({"project_id": identifier, "reason": reason})
                continue
            unended = lambda orgs: any(o["end_of_participation_raw"].casefold() == "false" for o in orgs)
            end = _day(p.get("endDate", ""))
            records.append({
                "id": "cordis-project:" + identifier,
                "project_id": identifier,
                "source_url": "https://cordis.europa.eu/project/id/" + identifier,
                "source_record_sha256": _sha(p),
                "acronym": _text(p.get("acronym", ""), 500),
                "title": _text(p.get("title"), 4000),
                "project_status_raw": _text(p.get("status", ""), 100),
                "project_start_date_raw": _text(p.get("startDate", ""), 80),
                "project_end_date_raw": _text(p.get("endDate", ""), 80),
                "source_content_update_raw": _text(p.get("contentUpdateDate", ""), 80),
                "project_end_date_is_past": end < day if end else None,
                "unended_canada_and_eu_prc_participants_listed": unended(ca) and unended(prc),
                "eu_prc_participants": sorted(prc, key=lambda o: (o["country"], o["name"], o["source_record_sha256"])),
                "canada_participants": sorted(ca, key=lambda o: (o["name"], o["source_record_sha256"])),
                "civilian_scope": "NO_EXPLICIT_MARKER_NOT_VERIFIED",
                "qualification_status": "RESEARCH_ONLY_NOT_QUALIFIED",
                "model_eligible": False,
                "expansion_inferred": False,
            })
    if not all_project_ids or not input_organisations:
        raise ValueError("CORDIS archive is empty")
    records.sort(key=lambda record: int(record["project_id"]))
    held.sort(key=lambda record: int(record["project_id"]))
    eu_rows = [o for p in records for o in p["eu_prc_participants"]]
    ca_rows = [o for p in records for o in p["canada_participants"]]
    return {
        "schema_version": 1,
        "status": "AVAILABLE",
        "mode": "RESEARCH_CO_PARTICIPATION_ONLY",
        "as_of_date": day.isoformat(),
        "interpretation": NOTICE,
        "source": {
            "name": "CORDIS Horizon Europe project and organisation open data (hierarchical JSON)",
            "source_url": HORIZON_ARCHIVE_URL,
            "catalogue_url": CATALOGUE_URL,
            "sha256": sha, "bytes": size, "retrieved_at": observed,
            "file_last_modified": _text(receipt.get("last_modified", ""), 100) or None,
            "catalogue_modified": _text(receipt.get("catalogue_modified", ""), 100) or None,
            "licence_url": LICENCE_URL,
            "attribution": "Source: CORDIS, Publications Office of the European Union, CORDIS – EU research projects under Horizon Europe (2021–2027), reused under Commission Decision 2011/833/EU. Selected, filtered and reformatted by Atlantic Signal. No EU endorsement implied.",
            "clock_scope": "CURRENT_DOWNLOADED_SNAPSHOT_NOT_FIRST_PUBLICATION_OR_FIRST_DISCOVERY",
        },
        "scope": {
            "eu_country_scope": "EU27_PARTICIPANT_LOCATION_NOT_PARENT_OWNERSHIP",
            "country_normalization": "SOURCE_EL_NORMALIZED_TO_ISO_GR_WITH_RAW_CODE_PRESERVED",
            "commercial_activity_code": "PRC",
            "commercial_activity_meaning": "Private for-profit entities, excluding Higher or Secondary Education Establishments",
            "organisation_identity": "COMMISSION_PARTICIPANT_IDENTIFIER_CODE_NOT_VERIFIED_LEGAL_IDENTITY",
            "active_field_meaning": "FRAMEWORK_PARTNERSHIP_AGREEMENT_ACTIVITY_NOT_UNIVERSAL_PARTICIPATION_STATUS",
            "end_of_participation_meaning": "SOURCE_BOOLEAN_NOT_A_DATE",
            "date_meaning": "PROJECT_PERIOD_AND_CONTENT_UPDATE_NOT_PUBLICATION_OR_MARKET_ENTRY",
            "privacy": "CONTACTS_ADDRESSES_VAT_GEOLOCATION_AND_OBJECTIVES_NOT_EXPORTED",
            "json_mapping": "organisation.id=PIC; address.country=country; organizationActivityType code=activity; attributes.type=role; attributes.terminated=endOfParticipation; missing fields remain empty",
        },
        "summary": {
            "project_count": len(records),
            "eu_prc_participation_rows": len(eu_rows),
            "eu_prc_source_organisation_ids": len({o["source_organisation_id"] for o in eu_rows if o["source_organisation_id"]}),
            "canada_participation_rows": len(ca_rows),
            "canada_source_organisation_ids": len({o["source_organisation_id"] for o in ca_rows if o["source_organisation_id"]}),
            "missing_organisation_id_rows": sum(o["source_organisation_id"] is None for o in eu_rows + ca_rows),
            "unended_partner_projects": sum(p["unended_canada_and_eu_prc_participants_listed"] for p in records),
            "project_status_counts": dict(sorted(Counter(p["project_status_raw"] for p in records).items())),
            "qualified_lead_count": 0,
        },
        "audit": {
            "archive_project_rows": len(all_project_ids), "archive_organisation_rows": input_organisations,
            "valid_project_rows": len(all_project_ids),
            "quarantined_project_rows": [],
            "quarantined_canada_projects": [],
            "quarantined_canada_eu_prc_projects": [],
            "coverage": "ALL_ROWS_PARSED",
            "canada_projects": canada_project_count, "canada_eu_any_activity_projects": eu_canada_project_count,
            "canada_eu_prc_projects_before_scope": candidate_count,
            "scope_held_projects": held,
            "boundary": "Conservative text screening is not an authoritative civilian-use classification; all displayed records remain unqualified.",
        },
        "projects": records,
    }


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--as-of-date", type=date.fromisoformat)
    args = parser.parse_args(argv)
    payload = build_research_payload(args.archive, json.loads(Path(args.receipt).read_text()), as_of_date=args.as_of_date)
    target = Path(args.output)
    if target.resolve() in {Path(args.archive).resolve(), Path(args.receipt).resolve()}:
        raise ValueError("Output must not overwrite source evidence")
    target.parent.mkdir(parents=True, exist_ok=True)
    # No source fetch, schedule, database mutation or evidence promotion occurs.
    import os
    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
        try:
            output.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
            output.close()
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"status": payload["status"], "summary": payload["summary"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
