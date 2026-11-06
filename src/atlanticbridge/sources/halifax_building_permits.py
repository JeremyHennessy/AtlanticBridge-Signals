"""Privacy-minimized offline Halifax permit pilot. No HTTP or source activation.

ArcGIS parsing is a fixture-tested interpretation, not transport verification.
Only bundled, hash-pinned records may enter analyst review packets.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
from datetime import datetime, timezone

SOURCE = "halifax_pplc_building_permits"
DATASET_URL = "https://data-hrm.hub.arcgis.com/datasets/6cef25e4172e4466a1eb8d3fd794f571_0/explore"
LICENSE_URL = "https://data-hrm.hub.arcgis.com/pages/open-data-licence"
ATTRIBUTION = "Contains information licenced under the Open Government Licence—Halifax."
LICENSE = "Open Government Licence–Halifax v1.0"
RIGHTS_STATUS = "OGL_HALIFAX_NONPERSONAL_PINNED_PILOT_ONLY"
RIGHTS_NOTE = "Commercial reuse of covered non-personal government information under OGL–Halifax v1.0; use signifies acceptance. Personal information, third-party rights and official marks excluded; no endorsement. Supplied as-is."
LIMIT = "Permit status does not prove construction, expansion, actual investment, completion or operating activity. Company and ownership unresolved. Estimates are not realised spending, must not be summed across rows or status transitions, and currency is unknown. No live transport, pagination, comprehensive coverage or absence proof."
COMMERCIAL_LABEL = "Mixed Use & Commercial Building Permit"
PINNED_SHA256 = "7931f81b9a0a0e541888977b3bc2a48b4403bc61139787756cd45b50a27983ff"
MAX_BYTES = 2_000_000
FIELDS = {"Permit_Number":"esriFieldTypeString", "Permit_Name":"esriFieldTypeString", "Permit_Status":"esriFieldTypeString", "Type_of_Structure":"esriFieldTypeString", "Date_of_Submission":"esriFieldTypeDate", "Date_of_Permit_Issuance":"esriFieldTypeDate", "Completed_Date":"esriFieldTypeDate", "Expiration_Date":"esriFieldTypeDate", "Estimated_Project_Value":"esriFieldTypeDouble"}
DATE_FIELDS = {"Date_of_Submission":"submission", "Date_of_Permit_Issuance":"issuance", "Completed_Date":"completion", "Expiration_Date":"expiration"}

def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result

def _decode(raw):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise ValueError("Expected bounded JSON bytes")
    try:
        return json.loads(raw, object_pairs_hook=_no_duplicates, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonfinite JSON value")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON response") from exc

def _epoch_instant(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Unexpected ArcGIS date value")
    try:
        return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        raise ValueError("Unsupported ArcGIS date range") from None

def parse_arcgis_response(raw: bytes) -> dict:
    """Allowlisted projection; unknown fields discarded, schema errors fail closed.

    Numeric date milliseconds are a fixture interpretation, not a verified
    live encoding. Civil dates remain unknown, independently for each field.
    """
    obj = _decode(raw)
    if not isinstance(obj, dict) or "error" in obj or not isinstance(obj.get("features"), list):
        raise ValueError("ArcGIS error or invalid feature response")
    if len(obj["features"]) > 2000:
        raise ValueError("Response exceeds offline page bound")
    fields = obj.get("fields")
    if not isinstance(fields, list) or any(not isinstance(f, dict) or not isinstance(f.get("name"),str) for f in fields):
        raise ValueError("Missing field schema")
    names = [f["name"] for f in fields]
    if len(set(names)) != len(names):
        raise ValueError("Duplicate schema field")
    types = {f["name"]: f.get("type") for f in fields}
    if any(types.get(k) != v for k,v in FIELDS.items()):
        raise ValueError("ArcGIS schema drift")
    more = obj.get("exceededTransferLimit")
    if more is not None and type(more) is not bool:
        raise ValueError("Invalid transfer-limit flag")
    records, seen, quarantined = [], set(), 0
    for feature in obj["features"]:
        if not isinstance(feature, dict) or not isinstance(feature.get("attributes"), dict):
            raise ValueError("Invalid feature attributes")
        a = feature["attributes"]
        if any(k not in a for k in FIELDS):
            raise ValueError("Required field missing")
        ident = a["Permit_Number"]
        if not isinstance(ident, str) or not re.fullmatch(r"[A-Z]{2,8}-[0-9]{4}-[0-9]{1,16}",ident) or ident in seen:
            raise ValueError("Missing or ambiguous duplicate permit identity")
        seen.add(ident)
        for field in ("Permit_Name", "Permit_Status", "Type_of_Structure"):
            if a[field] is not None and (not isinstance(a[field],str) or len(a[field]) > (32 if field == "Permit_Status" else 64)):
                raise ValueError("Unexpected string field")
        amount = a["Estimated_Project_Value"]
        if amount is not None and (type(amount) not in (int,float) or not math.isfinite(amount) or amount < 0):
            raise ValueError("Invalid estimate")
        instants = {name + "_utc_instant": _epoch_instant(a[field]) for field,name in DATE_FIELDS.items()}
        if a["Permit_Name"] != COMMERCIAL_LABEL or a["Type_of_Structure"] != "Commercial" or a["Permit_Status"] != "Issued" or not re.fullmatch(r"BPCOM-[0-9]{4}-[0-9]{1,16}", ident):
            quarantined += 1
            continue
        records.append({"permit_number":ident,"permit_label":COMMERCIAL_LABEL,"status_as_observed":"Issued", "estimated_project_value":amount,"currency":None,"company_name":None,"company_match_status":"unresolved","ownership_status":"unresolved","is_new_signal_on_retrieval":False,"date_interpretation":"FIXTURE_ARCGIS_MILLISECONDS_ASSUMPTION_NOT_LIVE_VERIFIED",**{name+"_date":None for name in DATE_FIELDS.values()},**instants})
    return {"source":SOURCE,"records":records,"quarantined_count":quarantined,"page_may_be_truncated":more,"coverage":"UNKNOWN_INCOMPLETE_NO_ABSENCE_PROOF","transport_verified":False,"pagination_verified":False,"response_sha256":hashlib.sha256(raw).hexdigest()}

def _pinned_records():
    raw = Path(__file__).with_name("halifax_permit_pinned_records.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != PINNED_SHA256:
        raise ValueError("Pinned Halifax records changed; review required")
    return _decode(raw)

def build_pinned_collection(kind: str = "ui_observed") -> dict:
    if kind not in ("ui_observed","invented"):
        raise ValueError("Only bundled pinned Halifax pilot records enabled")
    observed = kind == "ui_observed"
    return {"schema_version":1,"source":SOURCE,"dataset_url":DATASET_URL,"pilot_kind":kind,"collection_execution":"UI_OBSERVED_RESEARCH_SAMPLE" if observed else "INJECTED_FETCHER_FIXTURE_OR_REPLAY","fixture_only":not observed,"rights_status":RIGHTS_STATUS,"rights_note":RIGHTS_NOTE,"retrieved_at":None,"observed_on":"2026-11-06" if observed else None,"response_sha256":None,"pinned_records_sha256":PINNED_SHA256,"requested_limit":None,"records_returned_by_api":None,"page_may_be_truncated":None,"source_update_frequency":None,"freshness_note":"Historical UI-observed research sample from 2026-11-06; not raw API, current event or live collection." if observed else "Invented demonstration, not live data.","coverage":"PINNED_SAMPLE_ONLY_UNKNOWN_INCOMPLETE_NO_ABSENCE_PROOF","source_license":LICENSE,"source_license_url":LICENSE_URL,"source_attribution":ATTRIBUTION,"records":_pinned_records()[kind]}

def validate_pinned_collection(collection: dict) -> None:
    actual = json.dumps(collection, sort_keys=True, separators=(",", ":"), allow_nan=False)
    expected = json.dumps(build_pinned_collection(collection.get("pilot_kind")), sort_keys=True, separators=(",", ":"), allow_nan=False)
    if actual != expected:
        raise ValueError("Halifax collection differs from pinned records, origin, rights or coverage")

def has_halifax_provenance(value) -> bool:
    if isinstance(value,dict):
        return any(has_halifax_provenance(k) or has_halifax_provenance(v) for k,v in value.items())
    if isinstance(value,list):
        return any(has_halifax_provenance(v) for v in value)
    if isinstance(value,str):
        return any(token in value.lower() for token in ("data-hrm.hub.arcgis.com", "11xbiabya9ep0ynj", "6cef25e4172e4466a1eb8d3fd794f571", "bpcom-", "halifax_pplc", "open government licence—halifax", PINNED_SHA256))
    return False
