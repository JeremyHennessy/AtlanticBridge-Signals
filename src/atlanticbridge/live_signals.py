from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from .canadabuys_store import ensure_canadabuys_schema

SCHEMA_VERSION = 1
SOURCE_FAMILY = "CANADABUYS_AWARD"
SOURCE_LABEL = "CanadaBuys federal award notice"
SIGNAL_STAGE = "ACTIVE_CANADIAN_COMMERCIAL_EVIDENCE"
_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


def _date_value(value: object) -> date | None:
    text = str(value or "").strip()
    match = _DATE_RE.match(text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _effective_public_date(row: sqlite3.Row) -> date | None:
    publication = _date_value(row["publication_date"])
    amendment = _date_value(row["amendment_date"])
    values = [value for value in (publication, amendment) if value is not None]
    return max(values) if values else None


def _normalize_company(value: str) -> str:
    return "".join(char.casefold() for char in value if char.isalnum())


def _company_id(name: str, country: str) -> str:
    material = "\x1f".join([_normalize_company(name), country.strip().casefold()])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _signal_id(record_id: str) -> str:
    material = f"{SOURCE_FAMILY}\x1f{record_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _decimal(value: object) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", ".", "-."}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def unavailable_payload(*, reason: str, generated_at: str | None = None) -> dict[str, object]:
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "UNAVAILABLE",
        "generated_at": generated_at,
        "source": {
            "family": SOURCE_FAMILY,
            "label": SOURCE_LABEL,
            "observed_at": None,
            "source_url": None,
        },
        "summary": {
            "signal_count": 0,
            "company_count": 0,
            "country_count": 0,
            "latest_public_date": None,
            "earliest_public_date": None,
            "cad_contract_amount": "0",
            "lookback_days": None,
        },
        "reason": reason,
        "signals": [],
    }


def build_canadabuys_live_signals(
    conn: sqlite3.Connection,
    *,
    as_of_date: date | None = None,
    lookback_days: int = 365,
) -> dict[str, object]:
    if lookback_days < 1:
        raise ValueError("lookback_days must be at least 1")

    ensure_canadabuys_schema(conn)
    as_of_date = as_of_date or datetime.now(timezone.utc).date()
    generated_at = datetime.now(timezone.utc).isoformat()

    latest = conn.execute(
        """
        SELECT source_sha256, source_url, source_bytes, record_count,
               eu27_record_count, observed_at
        FROM canadabuys_award_snapshots
        ORDER BY observed_at DESC, source_sha256 DESC
        LIMIT 1
        """
    ).fetchone()
    if latest is None:
        return unavailable_payload(
            reason="No CanadaBuys snapshot has been ingested.",
            generated_at=generated_at,
        )

    start_date = as_of_date - timedelta(days=lookback_days)
    rows = conn.execute(
        """
        SELECT *
        FROM canadabuys_awards
        WHERE source_sha256 = ?
          AND is_eu27_supplier = 1
        ORDER BY publication_date DESC, amendment_date DESC,
                 supplier_legal_name ASC, record_id ASC
        """,
        (latest["source_sha256"],),
    ).fetchall()

    signals: list[dict[str, object]] = []
    cad_total = Decimal("0")
    for row in rows:
        public_date = _effective_public_date(row)
        if public_date is None or public_date < start_date or public_date > as_of_date:
            continue

        company_name = str(row["supplier_legal_name"] or "").strip()
        country = str(row["supplier_country"] or "").strip()
        if not company_name or not country:
            continue

        event_date = _date_value(row["contract_award_date"]) or public_date
        amount = str(row["contract_amount"] or "").strip()
        currency = str(row["contract_currency"] or "").strip()
        parsed_amount = _decimal(amount)
        if currency == "CAD" and parsed_amount is not None:
            cad_total += parsed_amount

        amendment_number = str(row["amendment_number"] or "").strip()
        amendment_date = _date_value(row["amendment_date"])
        amendment_number_is_nonzero = (
            bool(amendment_number) and bool(amendment_number.strip("0"))
        )
        signal_kind = (
            "FEDERAL_AWARD_AMENDED"
            if amendment_number_is_nonzero or amendment_date is not None
            else "FEDERAL_AWARD_PUBLISHED"
        )

        contracting_entity = str(row["contracting_entity_name"] or "").strip()
        title = str(row["title"] or "").strip()
        reference_number = str(row["reference_number"] or "").strip()
        why = (
            f"Official CanadaBuys data names {company_name} ({country}) as a supplier"
            + (f" to {contracting_entity}" if contracting_entity else "")
            + f"; the record became publicly available on {public_date.isoformat()}."
            + " This is direct Canadian federal commercial activity, not proof of first market entry."
        )

        signals.append(
            {
                "id": _signal_id(str(row["record_id"])),
                "record_id": str(row["record_id"]),
                "company_id": _company_id(company_name, country),
                "company_name": company_name,
                "country": country,
                "signal_family": SOURCE_FAMILY,
                "signal_kind": signal_kind,
                "signal_stage": SIGNAL_STAGE,
                "source_confidence": "SOURCE_CONFIRMED",
                "identity_scope": "SUPPLIER_LEGAL_NAME_AS_PUBLISHED",
                "event_date": event_date.isoformat(),
                "publicly_available_date": public_date.isoformat(),
                "first_observed_at": str(row["first_observed_at"] or ""),
                "last_observed_at": str(row["last_observed_at"] or ""),
                "recency_days": (as_of_date - public_date).days,
                "title": title,
                "reference_number": reference_number,
                "amendment_number": amendment_number,
                "contract_amount": amount,
                "contract_currency": currency,
                "total_contract_value": str(row["total_contract_value"] or "").strip(),
                "contract_start_date": str(row["contract_start_date"] or "").strip(),
                "contract_end_date": str(row["contract_end_date"] or "").strip(),
                "contracting_entity": contracting_entity,
                "contracting_entity_province": str(
                    row["contracting_entity_province"] or ""
                ).strip(),
                "regions_of_delivery": str(row["regions_of_delivery"] or "").strip(),
                "procurement_category": str(row["procurement_category"] or "").strip(),
                "award_description": str(row["award_description"] or "").strip(),
                "why_surfaced": why,
                "source_url": str(row["source_url"] or latest["source_url"] or "").strip(),
                "source_label": SOURCE_LABEL,
            }
        )

    signals.sort(
        key=lambda item: (
            str(item["publicly_available_date"]),
            str(item["company_name"]),
            str(item["id"]),
        ),
        reverse=True,
    )
    company_ids = {str(item["company_id"]) for item in signals}
    countries = {str(item["country"]) for item in signals}
    public_dates = [str(item["publicly_available_date"]) for item in signals]

    return {
        "schema_version": SCHEMA_VERSION,
        "status": "ACTIVE",
        "generated_at": generated_at,
        "as_of_date": as_of_date.isoformat(),
        "source": {
            "family": SOURCE_FAMILY,
            "label": SOURCE_LABEL,
            "observed_at": latest["observed_at"],
            "source_url": latest["source_url"],
            "source_sha256": latest["source_sha256"],
            "source_bytes": latest["source_bytes"],
            "source_record_count": latest["record_count"],
            "source_eu27_record_count": latest["eu27_record_count"],
        },
        "summary": {
            "signal_count": len(signals),
            "company_count": len(company_ids),
            "country_count": len(countries),
            "latest_public_date": max(public_dates) if public_dates else None,
            "earliest_public_date": min(public_dates) if public_dates else None,
            "cad_contract_amount": format(cad_total, "f"),
            "lookback_days": lookback_days,
        },
        "interpretation": (
            "Current source-backed Canada-directed commercial activity. "
            "Signals are not expansion probabilities and do not establish first Canadian entry."
        ),
        "signals": signals,
    }


def write_live_signals(
    conn: sqlite3.Connection,
    output: str | Path,
    *,
    as_of_date: date | None = None,
    lookback_days: int = 365,
) -> dict[str, object]:
    payload = build_canadabuys_live_signals(
        conn,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
    )
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload
