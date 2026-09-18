from __future__ import annotations

import json
import sqlite3
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone

from .sources.statcan_trade import (
    ANNUAL_CONFIG,
    ANNUAL_TOTAL_COMMODITY,
    MONTHLY_CONFIG,
    MONTHLY_TOTAL_COMMODITY,
    SCORING_EXCLUDED_COMMODITIES,
    StatCanDownload,
    StatCanTradeRecord,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS statcan_trade_rows (
    record_id TEXT PRIMARY KEY,
    source_pid TEXT NOT NULL,
    cadence TEXT NOT NULL CHECK (cadence IN ('monthly', 'annual')),
    ref_date TEXT NOT NULL,
    geo TEXT NOT NULL,
    dguid TEXT NOT NULL,
    trade TEXT NOT NULL,
    commodity TEXT NOT NULL,
    partner TEXT NOT NULL,
    uom TEXT NOT NULL,
    scalar_factor TEXT NOT NULL,
    vector TEXT NOT NULL,
    coordinate TEXT NOT NULL,
    value TEXT NOT NULL,
    status TEXT NOT NULL,
    symbol TEXT NOT NULL,
    terminated TEXT NOT NULL,
    decimals TEXT NOT NULL,
    raw_json TEXT NOT NULL,
    raw_hash TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_statcan_trade_source_ref
ON statcan_trade_rows(source_pid, ref_date);

CREATE INDEX IF NOT EXISTS idx_statcan_trade_geo_partner
ON statcan_trade_rows(geo, partner);

CREATE INDEX IF NOT EXISTS idx_statcan_trade_commodity
ON statcan_trade_rows(commodity);

CREATE TABLE IF NOT EXISTS statcan_trade_snapshots (
    source_pid TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    cadence TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_bytes INTEGER NOT NULL,
    filtered_record_count INTEGER NOT NULL,
    latest_ref_date TEXT NOT NULL,
    earliest_ref_date TEXT NOT NULL,
    partner_count INTEGER NOT NULL,
    geo_count INTEGER NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (source_pid, source_sha256)
);
"""


def ensure_statcan_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _insert_record(
    conn: sqlite3.Connection,
    record: StatCanTradeRecord,
    *,
    source_sha256: str,
    source_url: str,
    observed_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO statcan_trade_rows (
            record_id,
            source_pid,
            cadence,
            ref_date,
            geo,
            dguid,
            trade,
            commodity,
            partner,
            uom,
            scalar_factor,
            vector,
            coordinate,
            value,
            status,
            symbol,
            terminated,
            decimals,
            raw_json,
            raw_hash,
            source_sha256,
            source_url,
            observed_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            record.record_id,
            record.source_pid,
            record.cadence,
            record.ref_date,
            record.geo,
            record.dguid,
            record.trade,
            record.commodity,
            record.partner,
            record.uom,
            record.scalar_factor,
            record.vector,
            record.coordinate,
            record.value,
            record.status,
            record.symbol,
            record.terminated,
            record.decimals,
            record.raw_json,
            record.raw_hash,
            source_sha256,
            source_url,
            observed_at,
        ),
    )


def ingest_statcan_snapshot(
    conn: sqlite3.Connection,
    download: StatCanDownload,
    records,
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_statcan_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    config = download.config

    record_count = 0
    partners: set[str] = set()
    geos: set[str] = set()
    ref_dates: set[str] = set()

    conn.execute("BEGIN")
    try:
        conn.execute(
            "DELETE FROM statcan_trade_rows WHERE source_pid = ?",
            (config.pid,),
        )

        for record in records:
            if record.source_pid != config.pid:
                raise ValueError(
                    f"Statistics Canada record/source mismatch: "
                    f"{record.source_pid!r} != {config.pid!r}"
                )
            _insert_record(
                conn,
                record,
                source_sha256=download.archive_sha256,
                source_url=download.download_url,
                observed_at=observed_at,
            )
            record_count += 1
            partners.add(record.partner)
            geos.add(record.geo)
            if record.ref_date:
                ref_dates.add(record.ref_date)

        if record_count == 0:
            raise ValueError(
                f"Statistics Canada {config.pid} produced zero filtered records"
            )

        expected_partners = set(config.target_partners)
        if partners != expected_partners:
            missing = sorted(expected_partners - partners)
            unexpected = sorted(partners - expected_partners)
            raise ValueError(
                f"Statistics Canada {config.pid} partner coverage mismatch; "
                f"missing={missing!r}, unexpected={unexpected!r}"
            )

        expected_geos = {"Canada", "Nova Scotia"}
        if geos != expected_geos:
            raise ValueError(
                f"Statistics Canada {config.pid} geography coverage mismatch; "
                f"expected={sorted(expected_geos)!r}, got={sorted(geos)!r}"
            )

        if not ref_dates:
            raise ValueError(
                f"Statistics Canada {config.pid} produced no reference dates"
            )

        latest_ref = max(ref_dates)
        earliest_ref = min(ref_dates)

        conn.execute(
            """
            INSERT INTO statcan_trade_snapshots (
                source_pid,
                source_sha256,
                cadence,
                source_url,
                source_bytes,
                filtered_record_count,
                latest_ref_date,
                earliest_ref_date,
                partner_count,
                geo_count,
                observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_pid, source_sha256) DO UPDATE SET
                source_url = excluded.source_url,
                source_bytes = excluded.source_bytes,
                filtered_record_count = excluded.filtered_record_count,
                latest_ref_date = excluded.latest_ref_date,
                earliest_ref_date = excluded.earliest_ref_date,
                partner_count = excluded.partner_count,
                geo_count = excluded.geo_count,
                observed_at = excluded.observed_at
            """,
            (
                config.pid,
                download.archive_sha256,
                config.cadence,
                download.download_url,
                download.archive_bytes,
                record_count,
                latest_ref,
                earliest_ref,
                len(partners),
                len(geos),
                observed_at,
            ),
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "source_pid": config.pid,
        "cadence": config.cadence,
        "source_sha256": download.archive_sha256,
        "source_bytes": download.archive_bytes,
        "filtered_records": record_count,
        "partner_count": len(partners),
        "geo_count": len(geos),
        "earliest_ref_date": earliest_ref,
        "latest_ref_date": latest_ref,
    }


def _decimal(value: str) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _cad_string(value_thousands: str) -> str | None:
    value = _decimal(value_thousands)
    if value is None:
        return None
    return format(value * Decimal("1000"), "f")


def _pct_change(current: str, previous: str) -> str | None:
    current_value = _decimal(current)
    previous_value = _decimal(previous)
    if current_value is None or previous_value is None or previous_value == 0:
        return None
    pct = ((current_value - previous_value) / previous_value) * Decimal("100")
    return format(pct.quantize(Decimal("0.01")), "f")


def _prior_period(ref_date: str, cadence: str) -> str:
    if cadence == "annual":
        return str(int(ref_date) - 1)
    year_text, month_text = ref_date.split("-", 1)
    return f"{int(year_text) - 1:04d}-{month_text}"


def _latest_snapshot(conn: sqlite3.Connection, pid: str):
    return conn.execute(
        """
        SELECT *
        FROM statcan_trade_snapshots
        WHERE source_pid = ?
        ORDER BY observed_at DESC
        LIMIT 1
        """,
        (pid,),
    ).fetchone()


def _context_rows(
    conn: sqlite3.Connection,
    *,
    pid: str,
    latest_ref: str,
    cadence: str,
    commodity: str,
    geo: str = "Nova Scotia",
) -> list[dict[str, object]]:
    previous_ref = _prior_period(latest_ref, cadence)

    current_rows = conn.execute(
        """
        SELECT partner, trade, value, status, scalar_factor, uom
        FROM statcan_trade_rows
        WHERE source_pid = ?
          AND ref_date = ?
          AND geo = ?
          AND commodity = ?
        ORDER BY partner, trade
        """,
        (pid, latest_ref, geo, commodity),
    ).fetchall()

    previous = {
        (row["partner"], row["trade"]): row
        for row in conn.execute(
            """
            SELECT partner, trade, value, status
            FROM statcan_trade_rows
            WHERE source_pid = ?
              AND ref_date = ?
              AND geo = ?
              AND commodity = ?
            """,
            (pid, previous_ref, geo, commodity),
        )
    }

    output: list[dict[str, object]] = []
    for row in current_rows:
        prior = previous.get((row["partner"], row["trade"]))
        prior_value = prior["value"] if prior else ""
        output.append(
            {
                "partner": row["partner"],
                "trade": row["trade"],
                "current_ref_date": latest_ref,
                "previous_ref_date": previous_ref,
                "current_value_thousand_cad": row["value"] or None,
                "previous_value_thousand_cad": prior_value or None,
                "current_value_cad": _cad_string(row["value"]),
                "previous_value_cad": _cad_string(prior_value),
                "year_over_year_percent": _pct_change(
                    row["value"],
                    prior_value,
                ),
                "current_status": row["status"] or None,
                "previous_status": prior["status"] if prior and prior["status"] else None,
            }
        )
    return output


def statcan_trade_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_statcan_schema(conn)
    monthly = _latest_snapshot(conn, MONTHLY_CONFIG.pid)
    annual = _latest_snapshot(conn, ANNUAL_CONFIG.pid)

    if monthly is None or annual is None:
        return {
            "monthly_snapshot_present": monthly is not None,
            "annual_snapshot_present": annual is not None,
            "context_only": True,
            "monthly_major_markets": [],
            "annual_eu27_markets": [],
        }

    return {
        "context_only": True,
        "monthly": {
            "source_pid": MONTHLY_CONFIG.pid,
            "latest_ref_date": monthly["latest_ref_date"],
            "earliest_ref_date": monthly["earliest_ref_date"],
            "source_sha256": monthly["source_sha256"],
            "source_bytes": monthly["source_bytes"],
            "filtered_records": monthly["filtered_record_count"],
            "partner_count": monthly["partner_count"],
            "markets": _context_rows(
                conn,
                pid=MONTHLY_CONFIG.pid,
                latest_ref=monthly["latest_ref_date"],
                cadence="monthly",
                commodity=MONTHLY_TOTAL_COMMODITY,
            ),
        },
        "annual": {
            "source_pid": ANNUAL_CONFIG.pid,
            "latest_ref_date": annual["latest_ref_date"],
            "earliest_ref_date": annual["earliest_ref_date"],
            "source_sha256": annual["source_sha256"],
            "source_bytes": annual["source_bytes"],
            "filtered_records": annual["filtered_record_count"],
            "partner_count": annual["partner_count"],
            "markets": _context_rows(
                conn,
                pid=ANNUAL_CONFIG.pid,
                latest_ref=annual["latest_ref_date"],
                cadence="annual",
                commodity=ANNUAL_TOTAL_COMMODITY,
            ),
        },
        "scoring_excluded_commodities": sorted(SCORING_EXCLUDED_COMMODITIES),
    }
