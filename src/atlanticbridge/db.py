from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .sources.investment_canada import InvestmentCanadaRecord

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_bucket TEXT NOT NULL,
    retrieved_at TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    record_count INTEGER NOT NULL,
    UNIQUE(source_name, source_url, sha256)
);

CREATE TABLE IF NOT EXISTS investment_canada_notifications (
    record_id TEXT PRIMARY KEY,
    certification_month TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    investor_text TEXT NOT NULL,
    country_of_ultimate_control TEXT NOT NULL,
    canadian_business_text TEXT NOT NULL,
    is_new_business INTEGER NOT NULL CHECK (is_new_business IN (0, 1)),
    is_eu27 INTEGER NOT NULL CHECK (is_eu27 IN (0, 1)),
    source_url TEXT NOT NULL,
    source_bucket TEXT NOT NULL,
    raw_record_hash TEXT NOT NULL,
    first_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ica_country
ON investment_canada_notifications(country_of_ultimate_control);

CREATE INDEX IF NOT EXISTS idx_ica_month
ON investment_canada_notifications(certification_month);

CREATE INDEX IF NOT EXISTS idx_ica_eu_new
ON investment_canada_notifications(is_eu27, is_new_business);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def insert_investment_canada_records(
    conn: sqlite3.Connection,
    records: Iterable[InvestmentCanadaRecord],
    observed_at: str | None = None,
) -> int:
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    before = conn.total_changes
    conn.executemany(
        """
        INSERT OR IGNORE INTO investment_canada_notifications (
            record_id,
            certification_month,
            notification_type,
            investor_text,
            country_of_ultimate_control,
            canadian_business_text,
            is_new_business,
            is_eu27,
            source_url,
            source_bucket,
            raw_record_hash,
            first_observed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                record.record_id,
                record.certification_month,
                record.notification_type,
                record.investor_text,
                record.country_of_ultimate_control,
                record.canadian_business_text,
                int(record.is_new_business),
                int(record.is_eu27),
                record.source_url,
                record.source_bucket,
                record.raw_record_hash,
                observed_at,
            )
            for record in records
        ],
    )
    conn.commit()
    return conn.total_changes - before


def insert_source_snapshot(
    conn: sqlite3.Connection,
    *,
    source_name: str,
    source_url: str,
    source_bucket: str,
    retrieved_at: str,
    sha256: str,
    record_count: int,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO source_snapshots (
            source_name, source_url, source_bucket, retrieved_at, sha256, record_count
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (source_name, source_url, source_bucket, retrieved_at, sha256, record_count),
    )
    conn.commit()


def investment_canada_summary(conn: sqlite3.Connection) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS total_records,
            SUM(is_eu27) AS eu27_records,
            SUM(CASE WHEN is_eu27 = 1 AND is_new_business = 1 THEN 1 ELSE 0 END)
                AS eu27_new_business_records,
            MIN(certification_month) AS earliest_month,
            MAX(certification_month) AS latest_month
        FROM investment_canada_notifications
        """
    ).fetchone()

    by_country = [
        dict(item)
        for item in conn.execute(
            """
            SELECT
                country_of_ultimate_control AS country,
                COUNT(*) AS records,
                SUM(is_new_business) AS new_business_records
            FROM investment_canada_notifications
            WHERE is_eu27 = 1
            GROUP BY country_of_ultimate_control
            ORDER BY records DESC, country ASC
            """
        )
    ]

    return {
        "total_records": row["total_records"] or 0,
        "eu27_records": row["eu27_records"] or 0,
        "eu27_new_business_records": row["eu27_new_business_records"] or 0,
        "earliest_month": row["earliest_month"],
        "latest_month": row["latest_month"],
        "eu27_by_country": by_country,
    }
