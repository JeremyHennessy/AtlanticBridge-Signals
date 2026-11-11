"""Local-only normalization for analyst review of non-lead evidence context."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit

from .sources import nl_environmental_assessments as nl_ea
from .sources import halifax_building_permits as halifax

from .source_metadata import (
    BODACC_ATTRIBUTION,
    BODACC_LICENSE_URL,
    FEDERAL_GRANTS_ATTRIBUTION,
    FEDERAL_GRANTS_LICENSE_URL,
)

_PACKET_VERSION = 1
_LIVE_ORIGIN = "LIVE_HTTP_RESPONSE"
_FIXTURE_ORIGIN = "INJECTED_FETCHER_FIXTURE_OR_REPLAY"

SOURCES = {
    halifax.SOURCE: {"license": halifax.LICENSE, "license_url": halifax.LICENSE_URL, "attribution": halifax.ATTRIBUTION, "stage": "Issued permit context; completion unknown", "limit": halifax.LIMIT + " " + halifax.RIGHTS_NOTE, "host": "data-hrm.hub.arcgis.com"},
    nl_ea.SOURCE: {
        "license": "NL conditional copyright permission; real-data reuse not authorized",
        "license_url": nl_ea.TERMS_URL,
        "attribution": nl_ea.ATTRIBUTION,
        "stage": "Environmental assessment context",
        "limit": nl_ea.LIMIT + " " + nl_ea.RIGHTS_NOTE,
        "host": "www.gov.nl.ca",
    },
    "bodacc_commercial_notices": {
        "license": "Etalab Open Licence 2.0",
        "license_url": BODACC_LICENSE_URL,
        "attribution": BODACC_ATTRIBUTION,
        "stage": "French company legal notice context",
        "limit": "Does not establish Canadian activity, an expansion mandate, or site-selection intent.",
        "host": "www.bodacc.fr",
        "api_host": "bodacc-datadila.opendatasoft.com",
        "api_path": "/api/explore/v2.0/catalog/datasets/annonces-commerciales/records",
    },
    "canada_federal_grants_contributions": {
        "license": "Open Government Licence - Canada",
        "license_url": FEDERAL_GRANTS_LICENSE_URL,
        "attribution": FEDERAL_GRANTS_ATTRIBUTION,
        "stage": "Federal transfer-payment agreement context",
        "limit": "Agreement value is not necessarily cash disbursed; an award is not expansion intent or site selection.",
        "host": "open.canada.ca",
    },
    "nova_scotia_awarded_public_tenders": {
        "license": "Open Government Licence - Nova Scotia",
        "license_url": "https://novascotia.ca/opendata/licence.asp",
        "attribution": "Contains information licensed under the Open Government Licence – Nova Scotia",
        "stage": "Nova Scotia public procurement award context",
        "limit": "A tender award is prior supplier activity, not investment, expansion, or site selection.",
        "host": "data.novascotia.ca",
    },
}


def _safe_official_url(value: object, allowed_host: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.hostname != allowed_host
            or parsed.username or parsed.password or port not in (None, 443)
            or parsed.fragment):
        return None
    return value


def _date_or_unknown(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        if "T" in value or " " in value:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.year < 1900:
                return None
            return parsed.isoformat()
        parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
        if parsed_date.year < 1900:
            return None
        return parsed_date.isoformat()
    except ValueError:
        return None


def _api_query_url(config: dict, collection: dict) -> str | None:
    value = _safe_official_url(collection.get("api_url"), config.get("api_host", config["host"]))
    if value is not None and config.get("api_path") and urlsplit(value).path != config["api_path"]:
        return None
    return value


def _timestamp_or_unknown(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.year < 1900 or parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat()


def _nonnegative_int(value: object) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def _boolean(value: object) -> bool | None:
    return value if type(value) is bool else None


_COVERAGE_KEYS = {
    halifax.SOURCE: {"total": None, "matched": None, "excluded": None, "more": None, "truncated": "page_may_be_truncated"},
    nl_ea.SOURCE: {
        "total": None, "matched": "records_matching_exact_registration",
        "excluded": None, "more": None, "truncated": "page_may_be_truncated",
    },
    "bodacc_commercial_notices": {
        "total": "total_count_for_query",
        "matched": "records_matching_exact_siren",
        "excluded": "records_excluded_by_exact_siren_check",
        "more": "api_query_has_more_results",
        "truncated": None,
    },
    "canada_federal_grants_contributions": {
        "total": "total_count_for_exact_query",
        "matched": "records_matching_exact_recipient",
        "excluded": "records_excluded_by_exact_recipient_check",
        "more": "api_query_has_more_results",
        "truncated": None,
    },
    "nova_scotia_awarded_public_tenders": {
        "total": None,
        "matched": "records_matching_exact_vendor",
        "excluded": "records_excluded_by_exact_vendor_check",
        "more": None,
        "truncated": "page_may_be_truncated",
    },
}


def _coverage_signals(source: str, collection: dict) -> dict:
    keys = _COVERAGE_KEYS[source]
    return {
        "requested_limit": _nonnegative_int(collection.get("requested_limit")),
        "records_returned_by_api": _nonnegative_int(collection.get("records_returned_by_api")),
        "total_count_for_query": (
            _nonnegative_int(collection.get(keys["total"])) if keys["total"] else None
        ),
        "records_matching_exact_query": (
            _nonnegative_int(collection.get(keys["matched"])) if keys["matched"] else None
        ),
        "records_excluded_by_identity_check": (
            _nonnegative_int(collection.get(keys["excluded"])) if keys["excluded"] else None
        ),
        "api_query_has_more_results": (
            _boolean(collection.get(keys["more"])) if keys["more"] else None
        ),
        "page_may_be_truncated": (
            _boolean(collection.get(keys["truncated"])) if keys["truncated"] else None
        ),
        "source_update_frequency": (
            collection.get("source_update_frequency")
            if isinstance(collection.get("source_update_frequency"), str)
            else None
        ),
        "freshness_note": (
            collection.get("freshness_note")
            if isinstance(collection.get("freshness_note"), str)
            else None
        ),
    }


def _identity_resolution(source: str) -> tuple[str, str]:
    if source == halifax.SOURCE:
        return ("Pinned permit-number selection; uniqueness not verified beyond sample", "Permit identity does not establish company, ownership or corporate affiliation.")
    if source == nl_ea.SOURCE:
        return (
            "Exact registration-number selection; record identity is the observed project URL",
            "Registration numbers can collide. Published proponent text is not a verified legal entity, European owner, corporate group or operating site.",
        )
    if source == "bodacc_commercial_notices":
        return (
            "Expected collector filter: exact SIREN query",
            "A SIREN identifies a French registered entity only; it does not establish a parent, affiliate, or Canadian-entity relationship.",
        )
    if source == "canada_federal_grants_contributions":
        return (
            "Expected collector filter: exact recipient legal name",
            "A name filter does not establish ultimate ownership or affiliation with another similarly named entity.",
        )
    return (
        "Expected collector filter: normalized exact vendor name",
        "A normalized name filter does not establish the vendor's legal entity, ultimate owner, or corporate affiliation.",
    )


def _requested_identity_criterion(source: str, collection: dict) -> str | None:
    if source == halifax.SOURCE:
        return "Bundled pinned commercial permit sample only"
    if source == nl_ea.SOURCE:
        ids = collection.get("requested_registration_numbers")
        if isinstance(ids, list) and 1 <= len(ids) <= 20 and all(isinstance(x, str) and x.isascii() and x.isdigit() and 1 <= len(x) <= 8 for x in ids):
            return "Registration numbers: " + ", ".join(ids) + "; inspect observed URLs where numbers collide"
        return None
    if source == "bodacc_commercial_notices":
        value = collection.get("requested_siren")
        if isinstance(value, str) and len(value) == 9 and all("0" <= char <= "9" for char in value):
            return f"SIREN: {value}"
        return None
    if source == "canada_federal_grants_contributions":
        value = collection.get("requested_recipient_legal_name")
        if isinstance(value, str) and value.strip() and len(value) <= 256:
            recipient_type = collection.get("requested_recipient_type_code")
            type_text = f" (recipient type {recipient_type})" if isinstance(recipient_type, str) and len(recipient_type) <= 32 else ""
            return f"Recipient legal name{type_text}: {value.strip()}"
        return None
    value = collection.get("requested_vendor_legal_name")
    if isinstance(value, str) and value.strip() and len(value) <= 256:
        return f"Vendor name: {value.strip()}"
    return None


def _execution_class(collection: dict) -> str:
    origin = collection.get("collection_execution")
    if origin == "UI_OBSERVED_RESEARCH_SAMPLE":
        return "UI_OBSERVED_NOT_API_VERIFIED"
    if origin == _LIVE_ORIGIN:
        return "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED"
    if origin == _FIXTURE_ORIGIN:
        return "FIXTURE_DEMONSTRATION_NOT_LIVE"
    return "LEGACY_ORIGIN_UNVERIFIED"


def _record_view(source: str, config: dict, collection: dict, row: dict) -> dict:
    retrieved_at = _timestamp_or_unknown(collection.get("retrieved_at"))
    source_url = None
    headline = ""
    entity = ""
    event_date = None
    published_date = None
    source_record_date = None
    source_record_date_kind = None
    facts = {}
    stage = config["stage"]
    record_id = ""

    if source == halifax.SOURCE:
        record_id = row["permit_number"]
        source_url = halifax.DATASET_URL
        entity = "Unresolved company and ownership"
        headline = "Halifax commercial permit · " + record_id
        source_record_date = row["issuance_date"]
        source_record_date_kind = "PERMIT_ISSUANCE_DATE"
        event_date = source_record_date
        facts = {
            "permit number": record_id, "permit label": row["permit_label"],
            "status as observed": row["status_as_observed"],
            "submission date": row["submission_date"], "issuance date": row["issuance_date"],
            "completion date": row["completion_date"], "expiration date": row["expiration_date"],
            "estimated project value": row["estimated_project_value"], "currency": None,
            "amount semantics": "Estimated_Project_Value, not realised investment; do not sum rows or status transitions",
            "observation date": row["observed_on"], "date interpretation": row["date_interpretation"],
            "company match status": "unresolved", "ownership status": "unresolved",
            "new signal on retrieval": False,
        }
    elif source == nl_ea.SOURCE:
        source_url = nl_ea.approved_project_url(row.get("project_url"))
        registration = row.get("registration_number")
        if (source_url is None or not isinstance(registration, str) or not registration.isascii()
                or not registration.isdigit() or not 1 <= len(registration) <= 8):
            raise ValueError("NL record needs its exact registration and observed official URL")
        record_id = source_url
        if row.get("record_id") != record_id:
            raise ValueError("NL record identity must preserve the observed project URL")
        proponent = row.get("proponent_as_published")
        entity = proponent if isinstance(proponent, str) and proponent else "Proponent not stated"
        title = row.get("title")
        status = row.get("status_as_published")
        if not isinstance(title, str) or not title.strip() or not isinstance(status, str) or not status.strip():
            raise ValueError("NL record title and published status are required")
        headline = "NL assessment · " + title
        source_record_date = nl_ea.parse_source_date(row.get("registration_date"))
        source_record_date_kind = "PROJECT_REGISTRATION_DATE"
        event_date = source_record_date
        _, stage = nl_ea.STAGES.get(status, ("UNRECOGNIZED_ASSESSMENT_STATUS", "Unrecognized assessment status; review required"))
        issues = row.get("issues")
        facts = {
            "registration number": registration, "project title": title,
            "proponent as published": proponent,
            "status as published": status,
            "registration date": source_record_date,
            "release date": nl_ea.parse_source_date(row.get("release_date")),
            "normalized source-fields SHA-256": row.get("normalized_record_sha256"),
            "source quality flags": "; ".join(issues) if isinstance(issues, list) and all(isinstance(x, str) for x in issues) else "Unknown",
            "replacement relationship": "Not inferred from the project table",
            "official registry": nl_ea.INDEX_URL,
            "reuse gate": nl_ea.RIGHTS_NOTE,
        }
    elif source == "bodacc_commercial_notices":
        record_id = str(row.get("record_id") or "")
        siren = row.get("siren")
        entity = f"SIREN {siren}" if isinstance(siren, str) and siren else "Unresolved French entity"
        headline = f"{row.get('notice_family_label') or 'Commercial notice'} · {row.get('notice_type') or 'type unknown'}"
        published_date = _date_or_unknown(row.get("publication_date"))
        source_record_date = published_date
        source_record_date_kind = "NOTICE_PUBLICATION_DATE"
        # A notice's publication is not the date of its underlying company event.
        event_date = None
        source_url = _safe_official_url(row.get("official_notice_url"), config["host"])
        facts = {
            "SIREN": siren if isinstance(siren, str) else None,
            "notice family": row.get("notice_family_label"),
            "notice type": row.get("notice_type"),
            "bulletin edition": row.get("bulletin_edition"),
        }
    elif source == "canada_federal_grants_contributions":
        # CKAN _id identifies the amendment row; ref_number can repeat across amendments.
        record_id = str(row.get("_id") or row.get("ref_number") or "")
        legal_name = row.get("recipient_legal_name")
        entity = legal_name if isinstance(legal_name, str) else "Unresolved legal recipient"
        headline = row.get("agreement_type") if isinstance(row.get("agreement_type"), str) else "Federal transfer payment"
        source_record_date = _date_or_unknown(row.get("amendment_date"))
        source_record_date_kind = "AGREEMENT_AMENDMENT_DATE"
        # The amendment date does not establish when the disclosure became public.
        event_date = _date_or_unknown(row.get("agreement_start_date"))
        source_url = _safe_official_url(collection.get("dataset_url"), config["host"])
        facts = {
            "agreement reference": row.get("ref_number"),
            "agreement type": row.get("agreement_type"),
            "program": row.get("prog_name_en"),
            "agency": row.get("owner_org_title"),
            "reported amount": row.get("agreement_value"),
            "agreement start": event_date,
            "agreement end": _date_or_unknown(row.get("agreement_end_date")),
            "province": row.get("recipient_province"),
        }
    else:
        record_id = str(row.get("tender_id") or "")
        vendor = row.get("vendor")
        entity = vendor if isinstance(vendor, str) else "Unresolved vendor identity"
        buyer = row.get("entity")
        headline = f"Awarded public tender · {buyer}" if isinstance(buyer, str) else "Awarded public tender"
        source_record_date = _date_or_unknown(row.get("awarded_date"))
        source_record_date_kind = "TENDER_AWARD_DATE"
        # An award date is not a verified publication date for the dataset row.
        event_date = source_record_date
        source_url = _safe_official_url(collection.get("dataset_url"), config["host"])
        facts = {
            "tender ID": row.get("tender_id"),
            "buyer": buyer if isinstance(buyer, str) else None,
            "reported amount": row.get("awarded_amount"),
            "goods flag": row.get("goods"),
            "service flag": row.get("service"),
            "construction flag": row.get("construction"),
        }

    safe_facts = {
        str(key): value for key, value in facts.items()
        if value is None or isinstance(value, (str, int, float, bool))
    }
    if not record_id:
        raise ValueError(f"{source} record has no stable source identifier")
    source_ref_url = _api_query_url(config, collection)
    if source_url is None:
        source_url = source_ref_url

    stable_id = hashlib.sha256(f"{source}\0{record_id}".encode("utf-8")).hexdigest()
    identity_method, identity_limit = _identity_resolution(source)
    return {
        "expected_identity_filter": identity_method,
        "requested_identity_criterion": _requested_identity_criterion(source, collection),
        "identity_match_verification": "NOT_VALIDATED_BY_PACKET",
        "identity_verification_note": (
            "This packet does not compare the collector's requested identifier or name "
            "with this record. Check the original query and official source before relying on the match."
        ),
        "identity_resolution_limit": identity_limit,
        "finding_id": stable_id,
        "source": source,
        "source_record_id": record_id,
        "entity_label": entity,
        "headline": headline,
        "date_semantics_version": 2,
        "source_record_date": source_record_date,
        "source_record_date_kind": source_record_date_kind,
        "published_date": published_date,
        "event_date": event_date,
        "date_scope": "SOURCE_DATE_UNKNOWN" if source_record_date is None else "SOURCE_SPECIFIC_DATE",
        "retrieved_at": retrieved_at,
        "source_url": source_url,
        "api_query_url": source_ref_url,
        "license": config["license"],
        "license_url": config["license_url"],
        "attribution": config["attribution"],
        "event_stage": stage,
        "interpretation_limit": config["limit"],
        "source_facts": safe_facts,
        "evidence_class": _execution_class(collection),
        "independent_verification": "NOT_INDEPENDENTLY_VERIFIED",
        "review_disposition": "UNREVIEWED_CONTEXT_ONLY",
        "lead_eligible": False,
        "lead_promotion_allowed": False,
    }


def build_review_packet(collections: list[dict], *, generated_at: str | None = None) -> dict:
    if not isinstance(collections, list):
        raise ValueError("collections must be a list")
    findings = []
    finding_ids: set[str] = set()
    collection_summaries = []
    for collection in collections:
        if not isinstance(collection, dict):
            raise ValueError("collection envelope must be an object")
        source = collection.get("source")
        if source != halifax.SOURCE and halifax.has_halifax_provenance(collection):
            raise ValueError("Halifax provenance cannot be relabelled as another source family")
        if source == halifax.SOURCE:
            halifax.validate_pinned_collection(collection)
        if source != nl_ea.SOURCE and nl_ea.has_nl_provenance(collection):
            raise ValueError("NL provenance cannot be relabelled as another source family")
        config = SOURCES.get(source)
        if config is None:
            raise ValueError("source is not approved for the local analyst review workflow")
        if source == nl_ea.SOURCE and (
                collection.get("collection_execution") != _FIXTURE_ORIGIN
                or collection.get("fixture_only") is not True
                or collection.get("response_sha256") != nl_ea.SYNTHETIC_FIXTURE_SHA256
                or collection.get("rights_status") != nl_ea.RIGHTS_STATUS):
            raise ValueError("NL integration accepts invented fixtures only; real-data reuse remains gated")
        if source == nl_ea.SOURCE:
            nl_ea.validate_fixture_collection(collection)
        rows = collection.get("records")
        if not isinstance(rows, list):
            raise ValueError("collection records must be an array")
        summary = {
            "source": source,
            "evidence_class": _execution_class(collection),
            "independent_verification": "NOT_INDEPENDENTLY_VERIFIED",
            "retrieved_at": _timestamp_or_unknown(collection.get("retrieved_at")),
            "records_returned": len(rows),
            "coverage": collection.get("coverage") if isinstance(collection.get("coverage"), str) else "Unknown",
            "coverage_signals": _coverage_signals(source, collection),
            "source_license": config["license"],
            "source_license_url": config["license_url"],
            "api_query_url": _api_query_url(config, collection),
            "attribution": config["attribution"],
            "response_sha256": (
                collection.get("response_sha256")
                if isinstance(collection.get("response_sha256"), str)
                and len(collection.get("response_sha256")) == 64
                and all(
                    char in "0123456789abcdef"
                    for char in collection.get("response_sha256").lower()
                )
                else None
            ),
        }
        if source == halifax.SOURCE:
            summary.update({k: collection[k] for k in ("pilot_kind", "observed_on", "rights_status", "rights_note", "pinned_records_sha256", "fixture_only")})
        if source == nl_ea.SOURCE:
            summary["requested_registration_numbers"] = list(collection["requested_registration_numbers"])
            summary["fixture_only"] = True
            summary["rights_status"] = nl_ea.RIGHTS_STATUS
        collection_summaries.append(summary)
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("source record must be an object")
            finding = _record_view(source, config, collection, row)
            if finding["finding_id"] in finding_ids:
                raise ValueError(
                    "duplicate finding identifier across overlapping collector inputs; "
                    "remove duplicate rows or separate the source runs before building a packet"
                )
            finding_ids.add(finding["finding_id"])
            findings.append(finding)
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    if _timestamp_or_unknown(generated) is None:
        raise ValueError("generated_at must be a valid timezone-aware timestamp")
    return {
        "packet_version": _PACKET_VERSION,
        "workflow_mode": "LOCAL_ANALYST_REVIEW_ONLY",
        "generated_at": generated,
        "lead_promotion_allowed": False,
        "independent_verification": "NOT_INDEPENDENTLY_VERIFIED",
        "collections": collection_summaries,
        "findings": findings,
    }
