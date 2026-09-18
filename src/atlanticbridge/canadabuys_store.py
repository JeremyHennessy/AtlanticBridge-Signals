from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .sources.canadabuys import CanadaBuysAwardRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS canadabuys_awards (
    record_id TEXT PRIMARY KEY,
    reference_number TEXT NOT NULL,
    amendment_number TEXT NOT NULL,
    title TEXT NOT NULL,
    solicitation_number TEXT NOT NULL,
    contract_number TEXT NOT NULL,
    publication_date TEXT NOT NULL,
    contract_award_date TEXT NOT NULL,
    amendment_date TEXT NOT NULL,
    contract_start_date TEXT NOT NULL,
    contract_end_date TEXT NOT NULL,
    contract_amount TEXT NOT NULL,
    total_contract_value TEXT NOT NULL,
    contract_currency TEXT NOT NULL,
    award_status TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    amendment_type TEXT NOT NULL,
    gsin TEXT NOT NULL,
    gsin_description TEXT NOT NULL,
    unspsc TEXT NOT NULL,
    unspsc_description TEXT NOT NULL,
    procurement_category TEXT NOT NULL,
    notice_type TEXT NOT NULL,
    procurement_method TEXT NOT NULL,
    selection_criteria TEXT NOT NULL,
    limited_tendering_reason TEXT NOT NULL,
    trade_agreements TEXT NOT NULL,
    regions_of_delivery TEXT NOT NULL,
    supplier_legal_name TEXT NOT NULL,
    supplier_address_line TEXT NOT NULL,
    supplier_city TEXT NOT NULL,
    supplier_province TEXT NOT NULL,
    supplier_postal_code TEXT NOT NULL,
    supplier_country_raw TEXT NOT NULL,
    supplier_country TEXT NOT NULL,
    is_eu27_supplier INTEGER NOT NULL CHECK (is_eu27_supplier IN (0, 1)),
    contracting_entity_name TEXT NOT NULL,
    contracting_entity_city TEXT NOT NULL,
    contracting_entity_province TEXT NOT NULL,
    award_description TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    UNIQUE(reference_number, amendment_number)
);

CREATE INDEX IF NOT EXISTS idx_canadabuys_supplier
ON canadabuys_awards(supplier_legal_name);

CREATE INDEX IF NOT EXISTS idx_canadabuys_supplier_country
ON canadabuys_awards(supplier_country);

CREATE INDEX IF NOT EXISTS idx_canadabuys_eu
ON canadabuys_awards(is_eu27_supplier);

CREATE INDEX IF NOT EXISTS idx_canadabuys_award_date
ON canadabuys_awards(contract_award_date);

CREATE TABLE IF NOT EXISTS canadabuys_award_snapshots (
    source_sha256 TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_bytes INTEGER NOT NULL,
    record_count INTEGER NOT NULL,
    eu27_record_count INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);
"""


def ensure_canadabuys_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def ingest_awards(
    conn: sqlite3.Connection,
    records: Iterable[CanadaBuysAwardRecord],
    *,
    source_sha256: str,
    source_url: str,
    source_bytes: int,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_canadabuys_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    record_count = 0
    eu27_count = 0

    conn.execute("BEGIN")
    try:
        for record in records:
            record_count += 1
            eu27_count += int(record.is_eu27_supplier)
            conn.execute(
                """
                INSERT INTO canadabuys_awards (
                    record_id,
                    reference_number,
                    amendment_number,
                    title,
                    solicitation_number,
                    contract_number,
                    publication_date,
                    contract_award_date,
                    amendment_date,
                    contract_start_date,
                    contract_end_date,
                    contract_amount,
                    total_contract_value,
                    contract_currency,
                    award_status,
                    instrument_type,
                    amendment_type,
                    gsin,
                    gsin_description,
                    unspsc,
                    unspsc_description,
                    procurement_category,
                    notice_type,
                    procurement_method,
                    selection_criteria,
                    limited_tendering_reason,
                    trade_agreements,
                    regions_of_delivery,
                    supplier_legal_name,
                    supplier_address_line,
                    supplier_city,
                    supplier_province,
                    supplier_postal_code,
                    supplier_country_raw,
                    supplier_country,
                    is_eu27_supplier,
                    contracting_entity_name,
                    contracting_entity_city,
                    contracting_entity_province,
                    award_description,
                    raw_hash,
                    raw_json,
                    source_url,
                    source_sha256,
                    first_observed_at,
                    last_observed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(record_id) DO UPDATE SET
                    title = excluded.title,
                    solicitation_number = excluded.solicitation_number,
                    contract_number = excluded.contract_number,
                    publication_date = excluded.publication_date,
                    contract_award_date = excluded.contract_award_date,
                    amendment_date = excluded.amendment_date,
                    contract_start_date = excluded.contract_start_date,
                    contract_end_date = excluded.contract_end_date,
                    contract_amount = excluded.contract_amount,
                    total_contract_value = excluded.total_contract_value,
                    contract_currency = excluded.contract_currency,
                    award_status = excluded.award_status,
                    instrument_type = excluded.instrument_type,
                    amendment_type = excluded.amendment_type,
                    gsin = excluded.gsin,
                    gsin_description = excluded.gsin_description,
                    unspsc = excluded.unspsc,
                    unspsc_description = excluded.unspsc_description,
                    procurement_category = excluded.procurement_category,
                    notice_type = excluded.notice_type,
                    procurement_method = excluded.procurement_method,
                    selection_criteria = excluded.selection_criteria,
                    limited_tendering_reason = excluded.limited_tendering_reason,
                    trade_agreements = excluded.trade_agreements,
                    regions_of_delivery = excluded.regions_of_delivery,
                    supplier_legal_name = excluded.supplier_legal_name,
                    supplier_address_line = excluded.supplier_address_line,
                    supplier_city = excluded.supplier_city,
                    supplier_province = excluded.supplier_province,
                    supplier_postal_code = excluded.supplier_postal_code,
                    supplier_country_raw = excluded.supplier_country_raw,
                    supplier_country = excluded.supplier_country,
                    is_eu27_supplier = excluded.is_eu27_supplier,
                    contracting_entity_name = excluded.contracting_entity_name,
                    contracting_entity_city = excluded.contracting_entity_city,
                    contracting_entity_province = excluded.contracting_entity_province,
                    award_description = excluded.award_description,
                    raw_hash = excluded.raw_hash,
                    raw_json = excluded.raw_json,
                    source_url = excluded.source_url,
                    source_sha256 = excluded.source_sha256,
                    last_observed_at = excluded.last_observed_at
                """,
                (
                    record.record_id,
                    record.reference_number,
                    record.amendment_number,
                    record.title,
                    record.solicitation_number,
                    record.contract_number,
                    record.publication_date,
                    record.contract_award_date,
                    record.amendment_date,
                    record.contract_start_date,
                    record.contract_end_date,
                    record.contract_amount,
                    record.total_contract_value,
                    record.contract_currency,
                    record.award_status,
                    record.instrument_type,
                    record.amendment_type,
                    record.gsin,
                    record.gsin_description,
                    record.unspsc,
                    record.unspsc_description,
                    record.procurement_category,
                    record.notice_type,
                    record.procurement_method,
                    record.selection_criteria,
                    record.limited_tendering_reason,
                    record.trade_agreements,
                    record.regions_of_delivery,
                    record.supplier_legal_name,
                    record.supplier_address_line,
                    record.supplier_city,
                    record.supplier_province,
                    record.supplier_postal_code,
                    record.supplier_country_raw,
                    record.supplier_country,
                    int(record.is_eu27_supplier),
                    record.contracting_entity_name,
                    record.contracting_entity_city,
                    record.contracting_entity_province,
                    record.award_description,
                    record.raw_hash,
                    record.raw_json,
                    record.source_url,
                    source_sha256,
                    observed_at,
                    observed_at,
                ),
            )

        if record_count == 0:
            raise ValueError("CanadaBuys award snapshot contained zero records")

        conn.execute(
            """
            INSERT INTO canadabuys_award_snapshots (
                source_sha256,
                source_url,
                source_bytes,
                record_count,
                eu27_record_count,
                observed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_sha256) DO UPDATE SET
                source_bytes = excluded.source_bytes,
                record_count = excluded.record_count,
                eu27_record_count = excluded.eu27_record_count,
                observed_at = excluded.observed_at
            """,
            (
                source_sha256,
                source_url,
                source_bytes,
                record_count,
                eu27_count,
                observed_at,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "records": record_count,
        "eu27_supplier_records": eu27_count,
        "source_sha256": source_sha256,
        "source_bytes": source_bytes,
    }


def _decimal_sum(values: list[str]) -> str:
    total = Decimal("0")
    for value in values:
        if not value:
            continue
        try:
            total += Decimal(value)
        except InvalidOperation:
            continue
    return format(total, "f")


def canadabuys_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_canadabuys_schema(conn)
    latest = conn.execute(
        """
        SELECT *
        FROM canadabuys_award_snapshots
        ORDER BY observed_at DESC
        LIMIT 1
        """
    ).fetchone()

    if latest is None:
        return {
            "snapshots": 0,
            "current_records": 0,
            "current_eu27_supplier_records": 0,
            "eu27_by_country": [],
            "eu27_suppliers": [],
        }

    sha = latest["source_sha256"]
    rows = conn.execute(
        """
        SELECT
            supplier_country,
            supplier_legal_name,
            contract_amount,
            contract_currency,
            reference_number,
            contract_award_date,
            title
        FROM canadabuys_awards
        WHERE source_sha256 = ?
          AND is_eu27_supplier = 1
        ORDER BY contract_award_date DESC, supplier_legal_name ASC
        """,
        (sha,),
    ).fetchall()

    country_counts: dict[str, int] = {}
    supplier_counts: dict[tuple[str, str], int] = {}
    cad_amounts: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        country = row["supplier_country"]
        supplier = row["supplier_legal_name"]
        key = (supplier, country)
        country_counts[country] = country_counts.get(country, 0) + 1
        supplier_counts[key] = supplier_counts.get(key, 0) + 1
        if row["contract_currency"] == "CAD":
            cad_amounts.setdefault(key, []).append(row["contract_amount"])

    suppliers = [
        {
            "supplier": supplier,
            "country": country,
            "award_records": count,
            "contract_amount_cad": _decimal_sum(cad_amounts.get((supplier, country), [])),
        }
        for (supplier, country), count in supplier_counts.items()
    ]
    suppliers.sort(
        key=lambda item: (
            -int(item["award_records"]),
            item["supplier"],
            item["country"],
        )
    )

    snapshots = conn.execute(
        "SELECT COUNT(*) FROM canadabuys_award_snapshots"
    ).fetchone()[0]

    return {
        "snapshots": snapshots,
        "latest_source_sha256": sha,
        "latest_observed_at": latest["observed_at"],
        "latest_source_bytes": latest["source_bytes"],
        "current_records": latest["record_count"],
        "current_eu27_supplier_records": latest["eu27_record_count"],
        "eu27_by_country": [
            {"country": country, "award_records": count}
            for country, count in sorted(
                country_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
        "eu27_suppliers": suppliers,
    }
