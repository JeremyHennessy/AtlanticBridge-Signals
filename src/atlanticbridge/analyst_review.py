"""Local-only normalization for analyst review of non-lead evidence context."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from urllib.parse import urlsplit

_PACKET_VERSION = 1
_LIVE_ORIGIN = "LIVE_HTTP_RESPONSE"
_FIXTURE_ORIGIN = "INJECTED_FETCHER_FIXTURE_OR_REPLAY"

SOURCES = {
    "bodacc_commercial_notices": {
        "license": "Etalab Open Licence 2.0",
        "license_url": "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
        "attribution": "Source: BODACC, annonces-commerciales dataset; Etalab Open Licence 2.0.",
        "stage": "French company legal notice context",
        "limit": "Does not establish Canadian activity, an expansion mandate, or site-selection intent.",
        "host": "www.bodacc.fr",
    },
    "canada_federal_grants_contributions": {
        "license": "Open Government Licence - Canada",
        "license_url": "https://open.canada.ca/en/open-government-licence-canada",
        "attribution": "Source: Government of Canada, Proactive Disclosure - Grants and Contributions.",
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
    if source == "bodacc_commercial_notices":
        return (
            "Exact SIREN identifier check",
            "Identifies the French registered entity only; it does not establish a parent, affiliate, or Canadian-entity relationship.",
        )
    if source == "canada_federal_grants_contributions":
        return (
            "Exact recipient legal-name check",
            "A name match does not establish ultimate ownership or affiliation with another similarly named entity.",
        )
    return (
        "Normalized exact vendor-name check",
        "A normalized name match does not establish the vendor's legal entity, ultimate owner, or corporate affiliation.",
    )


def _execution_class(collection: dict) -> str:
    origin = collection.get("collection_execution")
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
    facts = {}
    record_id = ""

    if source == "bodacc_commercial_notices":
        record_id = str(row.get("record_id") or "")
        siren = row.get("siren")
        entity = f"SIREN {siren}" if isinstance(siren, str) and siren else "Unresolved French entity"
        headline = f"{row.get('notice_family_label') or 'Commercial notice'} · {row.get('notice_type') or 'type unknown'}"
        published_date = _date_or_unknown(row.get("publication_date"))
        event_date = published_date
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
        published_date = _date_or_unknown(row.get("amendment_date"))
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
        published_date = _date_or_unknown(row.get("awarded_date"))
        event_date = published_date
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
    source_ref = row.get("official_notice_url") if source == "bodacc_commercial_notices" else collection.get("api_url")
    source_ref_url = _safe_official_url(source_ref, config["host"])
    if source_url is None:
        source_url = source_ref_url

    stable_id = hashlib.sha256(f"{source}\0{record_id}".encode("utf-8")).hexdigest()
    identity_method, identity_limit = _identity_resolution(source)
    return {
        "identity_match_method": identity_method,
        "identity_resolution_limit": identity_limit,
        "finding_id": stable_id,
        "source": source,
        "source_record_id": record_id,
        "entity_label": entity,
        "headline": headline,
        "published_date": published_date,
        "event_date": event_date,
        "date_scope": "SOURCE_DATE_UNKNOWN" if published_date is None else "SOURCE_DATE",
        "retrieved_at": retrieved_at,
        "source_url": source_url,
        "api_query_url": source_ref_url,
        "license": config["license"],
        "license_url": config["license_url"],
        "attribution": config["attribution"],
        "event_stage": config["stage"],
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
        config = SOURCES.get(source)
        if config is None:
            raise ValueError("source is not approved for the local analyst review workflow")
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
