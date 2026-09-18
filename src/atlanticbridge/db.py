from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .sources.corporations_canada import CorporationCanadaRecord
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

CREATE TABLE IF NOT EXISTS corporations_canada_active (
    corporation_number TEXT PRIMARY KEY,
    business_number TEXT NOT NULL,
    corporate_name_form_1 TEXT NOT NULL,
    corporate_name_form_2 TEXT NOT NULL,
    governing_legislation TEXT NOT NULL,
    status TEXT NOT NULL,
    status_detail TEXT NOT NULL,
    anniversary_date TEXT NOT NULL,
    year_last_annual_filing TEXT NOT NULL,
    date_last_annual_meeting TEXT NOT NULL,
    street TEXT NOT NULL,
    street_2 TEXT NOT NULL,
    city_town TEXT NOT NULL,
    province_territory TEXT NOT NULL,
    country TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    minimum_number_of_directors TEXT NOT NULL,
    maximum_number_of_directors TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    record_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_corp_name
ON corporations_canada_active(corporate_name_form_1);

CREATE INDEX IF NOT EXISTS idx_corp_province
ON corporations_canada_active(province_territory);

CREATE TABLE IF NOT EXISTS corporations_canada_events (
    event_id TEXT PRIMARY KEY,
    corporation_number TEXT NOT NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('CORPORATION_APPEARED', 'CORPORATION_CHANGED')),
    observed_at TEXT NOT NULL,
    old_record_hash TEXT NOT NULL,
    new_record_hash TEXT NOT NULL,
    changed_fields_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    FOREIGN KEY (corporation_number)
        REFERENCES corporations_canada_active(corporation_number)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_corp_events_observed
ON corporations_canada_events(observed_at);

CREATE INDEX IF NOT EXISTS idx_corp_events_type
ON corporations_canada_events(event_type);
"""


_CORP_COLUMNS = [
    "corporation_number",
    "business_number",
    "corporate_name_form_1",
    "corporate_name_form_2",
    "governing_legislation",
    "status",
    "status_detail",
    "anniversary_date",
    "year_last_annual_filing",
    "date_last_annual_meeting",
    "street",
    "street_2",
    "city_town",
    "province_territory",
    "country",
    "postal_code",
    "minimum_number_of_directors",
    "maximum_number_of_directors",
    "record_hash",
    "record_json",
    "source_url",
]


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


def _create_corporation_stage(conn: sqlite3.Connection) -> None:
    conn.execute("DROP TABLE IF EXISTS temp.corporations_canada_stage")
    conn.execute(
        """
        CREATE TEMP TABLE corporations_canada_stage (
            corporation_number TEXT PRIMARY KEY,
            business_number TEXT NOT NULL,
            corporate_name_form_1 TEXT NOT NULL,
            corporate_name_form_2 TEXT NOT NULL,
            governing_legislation TEXT NOT NULL,
            status TEXT NOT NULL,
            status_detail TEXT NOT NULL,
            anniversary_date TEXT NOT NULL,
            year_last_annual_filing TEXT NOT NULL,
            date_last_annual_meeting TEXT NOT NULL,
            street TEXT NOT NULL,
            street_2 TEXT NOT NULL,
            city_town TEXT NOT NULL,
            province_territory TEXT NOT NULL,
            country TEXT NOT NULL,
            postal_code TEXT NOT NULL,
            minimum_number_of_directors TEXT NOT NULL,
            maximum_number_of_directors TEXT NOT NULL,
            record_hash TEXT NOT NULL,
            record_json TEXT NOT NULL,
            source_url TEXT NOT NULL
        )
        """
    )


def _stage_corporation_records(
    conn: sqlite3.Connection,
    records: Iterable[CorporationCanadaRecord],
    *,
    batch_size: int = 5000,
) -> int:
    sql = f"""
        INSERT OR REPLACE INTO corporations_canada_stage (
            {", ".join(_CORP_COLUMNS)}
        ) VALUES ({", ".join("?" for _ in _CORP_COLUMNS)})
    """
    batch: list[tuple[str, ...]] = []
    count = 0

    for record in records:
        batch.append(record.stage_tuple())
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            count += len(batch)
            batch.clear()

    if batch:
        conn.executemany(sql, batch)
        count += len(batch)

    return count


def _changed_fields(old_json: str, new_json: str) -> list[str]:
    old = json.loads(old_json)
    new = json.loads(new_json)
    return sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))


def _event_id(
    corporation_number: str,
    event_type: str,
    old_hash: str,
    new_hash: str,
) -> str:
    material = "\x1f".join([corporation_number, event_type, old_hash, new_hash])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def ingest_corporations_canada_snapshot(
    conn: sqlite3.Connection,
    records: Iterable[CorporationCanadaRecord],
    *,
    observed_at: str | None = None,
    mode: str,
) -> dict[str, int]:
    if mode not in {"baseline", "diff"}:
        raise ValueError("mode must be 'baseline' or 'diff'")

    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    current_count = conn.execute(
        "SELECT COUNT(*) FROM corporations_canada_active"
    ).fetchone()[0]

    if mode == "diff" and current_count == 0:
        raise ValueError("Corporations Canada diff requires an existing baseline")

    conn.execute("BEGIN")
    try:
        _create_corporation_stage(conn)
        staged_count = _stage_corporation_records(conn, records)

        appeared_rows = []
        changed_rows = []

        if mode == "diff":
            appeared_rows = conn.execute(
                """
                SELECT
                    s.corporation_number,
                    s.record_hash,
                    s.source_url
                FROM corporations_canada_stage s
                LEFT JOIN corporations_canada_active c
                    ON c.corporation_number = s.corporation_number
                WHERE c.corporation_number IS NULL
                """
            ).fetchall()

            changed_rows = conn.execute(
                """
                SELECT
                    s.corporation_number,
                    c.record_hash AS old_hash,
                    s.record_hash AS new_hash,
                    c.record_json AS old_json,
                    s.record_json AS new_json,
                    s.source_url
                FROM corporations_canada_stage s
                JOIN corporations_canada_active c
                    ON c.corporation_number = s.corporation_number
                WHERE c.record_hash <> s.record_hash
                """
            ).fetchall()

        placeholders = ", ".join(_CORP_COLUMNS)
        conn.execute(
            f"""
            INSERT INTO corporations_canada_active (
                {placeholders},
                first_observed_at,
                last_observed_at
            )
            SELECT
                {placeholders},
                ?,
                ?
            FROM corporations_canada_stage
            WHERE 1
            ON CONFLICT(corporation_number) DO UPDATE SET
                business_number = excluded.business_number,
                corporate_name_form_1 = excluded.corporate_name_form_1,
                corporate_name_form_2 = excluded.corporate_name_form_2,
                governing_legislation = excluded.governing_legislation,
                status = excluded.status,
                status_detail = excluded.status_detail,
                anniversary_date = excluded.anniversary_date,
                year_last_annual_filing = excluded.year_last_annual_filing,
                date_last_annual_meeting = excluded.date_last_annual_meeting,
                street = excluded.street,
                street_2 = excluded.street_2,
                city_town = excluded.city_town,
                province_territory = excluded.province_territory,
                country = excluded.country,
                postal_code = excluded.postal_code,
                minimum_number_of_directors = excluded.minimum_number_of_directors,
                maximum_number_of_directors = excluded.maximum_number_of_directors,
                record_hash = excluded.record_hash,
                record_json = excluded.record_json,
                source_url = excluded.source_url,
                last_observed_at = excluded.last_observed_at
            """,
            (observed_at, observed_at),
        )

        for row in appeared_rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO corporations_canada_events (
                    event_id,
                    corporation_number,
                    event_type,
                    observed_at,
                    old_record_hash,
                    new_record_hash,
                    changed_fields_json,
                    source_url
                ) VALUES (?, ?, 'CORPORATION_APPEARED', ?, '', ?, '[]', ?)
                """,
                (
                    _event_id(
                        row["corporation_number"],
                        "CORPORATION_APPEARED",
                        "",
                        row["record_hash"],
                    ),
                    row["corporation_number"],
                    observed_at,
                    row["record_hash"],
                    row["source_url"],
                ),
            )

        for row in changed_rows:
            conn.execute(
                """
                INSERT OR IGNORE INTO corporations_canada_events (
                    event_id,
                    corporation_number,
                    event_type,
                    observed_at,
                    old_record_hash,
                    new_record_hash,
                    changed_fields_json,
                    source_url
                ) VALUES (?, ?, 'CORPORATION_CHANGED', ?, ?, ?, ?, ?)
                """,
                (
                    _event_id(
                        row["corporation_number"],
                        "CORPORATION_CHANGED",
                        row["old_hash"],
                        row["new_hash"],
                    ),
                    row["corporation_number"],
                    observed_at,
                    row["old_hash"],
                    row["new_hash"],
                    json.dumps(
                        _changed_fields(row["old_json"], row["new_json"]),
                        separators=(",", ":"),
                    ),
                    row["source_url"],
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "records_staged": staged_count,
        "appeared": len(appeared_rows),
        "changed": len(changed_rows),
    }


def corporations_canada_summary(conn: sqlite3.Connection) -> dict[str, object]:
    current = conn.execute(
        """
        SELECT
            COUNT(*) AS active_records,
            MIN(first_observed_at) AS first_observed_at,
            MAX(last_observed_at) AS last_observed_at
        FROM corporations_canada_active
        """
    ).fetchone()

    events = [
        dict(row)
        for row in conn.execute(
            """
            SELECT event_type, COUNT(*) AS records
            FROM corporations_canada_events
            GROUP BY event_type
            ORDER BY event_type
            """
        )
    ]

    provinces = [
        dict(row)
        for row in conn.execute(
            """
            SELECT province_territory AS province, COUNT(*) AS records
            FROM corporations_canada_active
            GROUP BY province_territory
            ORDER BY records DESC, province ASC
            LIMIT 20
            """
        )
    ]

    return {
        "active_records": current["active_records"] or 0,
        "first_observed_at": current["first_observed_at"],
        "last_observed_at": current["last_observed_at"],
        "events": events,
        "top_provinces": provinces,
    }
