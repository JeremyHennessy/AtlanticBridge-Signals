from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from .sources.corporations_canada import CorporationCanadaRecord
from .sources.cordis import CordisParticipationRecord, CordisProjectRecord, EU27_ISO2
from .sources.investment_canada import (
    SOURCE_NAME as INVESTMENT_CANADA_SOURCE_NAME,
    InvestmentCanadaPageSnapshot,
    InvestmentCanadaRecord,
)

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
    investor_name TEXT NOT NULL DEFAULT '',
    investor_locality TEXT NOT NULL DEFAULT '',
    investor_node_id TEXT NOT NULL DEFAULT '',
    country_of_ultimate_control TEXT NOT NULL,
    canadian_business_text TEXT NOT NULL,
    canadian_businesses_json TEXT NOT NULL DEFAULT '[]',
    canadian_business_node_ids_json TEXT NOT NULL DEFAULT '[]',
    is_new_business INTEGER NOT NULL CHECK (is_new_business IN (0, 1)),
    is_eu27 INTEGER NOT NULL CHECK (is_eu27 IN (0, 1)),
    source_url TEXT NOT NULL,
    source_bucket TEXT NOT NULL,
    source_page INTEGER NOT NULL DEFAULT 0,
    raw_record_hash TEXT NOT NULL,
    record_json TEXT NOT NULL DEFAULT '{}',
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL DEFAULT ''
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

CREATE TABLE IF NOT EXISTS cordis_projects (
    project_id TEXT PRIMARY KEY,
    acronym TEXT NOT NULL,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    total_cost TEXT NOT NULL,
    ec_max_contribution TEXT NOT NULL,
    topics TEXT NOT NULL,
    ec_signature_date TEXT NOT NULL,
    framework_programme TEXT NOT NULL,
    master_call TEXT NOT NULL,
    sub_call TEXT NOT NULL,
    funding_scheme TEXT NOT NULL,
    nature TEXT NOT NULL,
    objective TEXT NOT NULL,
    content_update_date TEXT NOT NULL,
    rcn TEXT NOT NULL,
    grant_doi TEXT NOT NULL,
    keywords TEXT NOT NULL,
    human_validated TEXT NOT NULL,
    legal_basis TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cordis_participations (
    participation_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    project_acronym TEXT NOT NULL,
    organisation_id TEXT NOT NULL,
    vat_number TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT NOT NULL,
    sme TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    street TEXT NOT NULL,
    post_code TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    nuts_code TEXT NOT NULL,
    geolocation TEXT NOT NULL,
    organization_url TEXT NOT NULL,
    contact_form TEXT NOT NULL,
    content_update_date TEXT NOT NULL,
    rcn TEXT NOT NULL,
    source_order TEXT NOT NULL,
    role TEXT NOT NULL,
    ec_contribution TEXT NOT NULL,
    net_ec_contribution TEXT NOT NULL,
    total_cost TEXT NOT NULL,
    end_of_participation TEXT NOT NULL,
    active TEXT NOT NULL,
    record_hash TEXT NOT NULL,
    record_json TEXT NOT NULL,
    source_url TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY (project_id) REFERENCES cordis_projects(project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_cordis_part_project
ON cordis_participations(project_id);

CREATE INDEX IF NOT EXISTS idx_cordis_part_org
ON cordis_participations(organisation_id);

CREATE INDEX IF NOT EXISTS idx_cordis_part_country
ON cordis_participations(country);

CREATE INDEX IF NOT EXISTS idx_cordis_part_activity
ON cordis_participations(activity_type);

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


_ICA_MIGRATION_COLUMNS = {
    "investor_name": "TEXT NOT NULL DEFAULT ''",
    "investor_locality": "TEXT NOT NULL DEFAULT ''",
    "investor_node_id": "TEXT NOT NULL DEFAULT ''",
    "canadian_businesses_json": "TEXT NOT NULL DEFAULT '[]'",
    "canadian_business_node_ids_json": "TEXT NOT NULL DEFAULT '[]'",
    "source_page": "INTEGER NOT NULL DEFAULT 0",
    "record_json": "TEXT NOT NULL DEFAULT '{}'",
    "last_observed_at": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_investment_canada_columns(conn: sqlite3.Connection) -> None:
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(investment_canada_notifications)")
    }
    for column, declaration in _ICA_MIGRATION_COLUMNS.items():
        if column not in existing:
            conn.execute(
                f"ALTER TABLE investment_canada_notifications "
                f"ADD COLUMN {column} {declaration}"
            )
    conn.commit()


def connect(path: str | Path) -> sqlite3.Connection:
    if str(path) != ":memory:":
        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _ensure_investment_canada_columns(conn)
    return conn


_ICA_INSERT_COLUMNS = (
    "record_id",
    "certification_month",
    "notification_type",
    "investor_text",
    "investor_name",
    "investor_locality",
    "investor_node_id",
    "country_of_ultimate_control",
    "canadian_business_text",
    "canadian_businesses_json",
    "canadian_business_node_ids_json",
    "is_new_business",
    "is_eu27",
    "source_url",
    "source_bucket",
    "source_page",
    "raw_record_hash",
    "record_json",
    "first_observed_at",
    "last_observed_at",
)


def _investment_canada_values(
    record: InvestmentCanadaRecord,
    observed_at: str,
) -> tuple[object, ...]:
    return (
        record.record_id,
        record.certification_month,
        record.notification_type,
        record.investor_text,
        record.investor_name,
        record.investor_locality,
        record.investor_node_id,
        record.country_of_ultimate_control,
        record.canadian_business_text,
        record.canadian_businesses_json,
        json.dumps(
            list(record.canadian_business_node_ids),
            separators=(",", ":"),
        ),
        int(record.is_new_business),
        int(record.is_eu27),
        record.source_url,
        record.source_bucket,
        record.source_page,
        record.raw_record_hash,
        record.record_json,
        observed_at,
        observed_at,
    )


def insert_investment_canada_records(
    conn: sqlite3.Connection,
    records: Iterable[InvestmentCanadaRecord],
    observed_at: str | None = None,
) -> int:
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    before = conn.total_changes
    placeholders = ", ".join("?" for _ in _ICA_INSERT_COLUMNS)
    conn.executemany(
        f"""
        INSERT OR IGNORE INTO investment_canada_notifications (
            {", ".join(_ICA_INSERT_COLUMNS)}
        ) VALUES ({placeholders})
        """,
        [
            _investment_canada_values(record, observed_at)
            for record in records
        ],
    )
    conn.commit()
    return conn.total_changes - before


def replace_investment_canada_history(
    conn: sqlite3.Connection,
    records: Iterable[InvestmentCanadaRecord],
    page_snapshots: Iterable[InvestmentCanadaPageSnapshot],
    *,
    observed_at: str | None = None,
) -> dict[str, int]:
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    records = list(records)
    page_snapshots = list(page_snapshots)

    if not records:
        raise ValueError("Investment Canada historical snapshot contained zero records")
    if not page_snapshots:
        raise ValueError("Investment Canada historical snapshot contained zero pages")

    record_ids = [record.record_id for record in records]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("Investment Canada historical snapshot contains duplicate record IDs")

    conn.execute("BEGIN")
    try:
        conn.execute("DROP TABLE IF EXISTS temp.investment_canada_history_keys")
        conn.execute(
            """
            CREATE TEMP TABLE investment_canada_history_keys (
                record_id TEXT PRIMARY KEY
            )
            """
        )
        conn.executemany(
            "INSERT INTO investment_canada_history_keys (record_id) VALUES (?)",
            [(record_id,) for record_id in record_ids],
        )

        placeholders = ", ".join("?" for _ in _ICA_INSERT_COLUMNS)
        update_columns = [
            column
            for column in _ICA_INSERT_COLUMNS
            if column not in {"record_id", "first_observed_at"}
        ]
        updates = ",\n                    ".join(
            f"{column} = excluded.{column}"
            for column in update_columns
        )
        conn.executemany(
            f"""
            INSERT INTO investment_canada_notifications (
                {", ".join(_ICA_INSERT_COLUMNS)}
            ) VALUES ({placeholders})
            ON CONFLICT(record_id) DO UPDATE SET
                {updates}
            """,
            [
                _investment_canada_values(record, observed_at)
                for record in records
            ],
        )

        conn.execute(
            """
            DELETE FROM investment_canada_notifications
            WHERE record_id NOT IN (
                SELECT record_id
                FROM investment_canada_history_keys
            )
            """
        )

        conn.executemany(
            """
            INSERT OR IGNORE INTO source_snapshots (
                source_name,
                source_url,
                source_bucket,
                retrieved_at,
                sha256,
                record_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    INVESTMENT_CANADA_SOURCE_NAME,
                    snapshot.source_url,
                    f"{snapshot.source_bucket}:page={snapshot.source_page}",
                    observed_at,
                    snapshot.sha256,
                    snapshot.record_count,
                )
                for snapshot in page_snapshots
            ],
        )

        current_records = conn.execute(
            "SELECT COUNT(*) FROM investment_canada_notifications"
        ).fetchone()[0]
        if current_records != len(records):
            raise ValueError(
                "Investment Canada historical replacement count mismatch: "
                f"expected={len(records)} stored={current_records}"
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "records_stored": len(records),
        "page_snapshots": len(page_snapshots),
    }

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
            COUNT(DISTINCT CASE
                WHEN is_eu27 = 1 AND is_new_business = 1
                THEN NULLIF(investor_node_id, '')
            END) AS eu27_new_business_unique_investor_nodes,
            SUM(CASE WHEN investor_node_id <> '' THEN 1 ELSE 0 END)
                AS records_with_investor_node_id,
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

    new_business_by_year = [
        dict(item)
        for item in conn.execute(
            """
            SELECT
                SUBSTR(certification_month, 1, 4) AS year,
                COUNT(*) AS records
            FROM investment_canada_notifications
            WHERE is_eu27 = 1
              AND is_new_business = 1
            GROUP BY SUBSTR(certification_month, 1, 4)
            ORDER BY year
            """
        )
    ]

    return {
        "total_records": row["total_records"] or 0,
        "eu27_records": row["eu27_records"] or 0,
        "eu27_new_business_records": row["eu27_new_business_records"] or 0,
        "eu27_new_business_unique_investor_nodes":
            row["eu27_new_business_unique_investor_nodes"] or 0,
        "records_with_investor_node_id": row["records_with_investor_node_id"] or 0,
        "earliest_month": row["earliest_month"],
        "latest_month": row["latest_month"],
        "eu27_by_country": by_country,
        "eu27_new_business_by_year": new_business_by_year,
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


_PROJECT_INSERT = """
INSERT INTO cordis_projects (
    project_id, acronym, status, title, start_date, end_date, total_cost,
    ec_max_contribution, topics, ec_signature_date, framework_programme,
    master_call, sub_call, funding_scheme, nature, objective,
    content_update_date, rcn, grant_doi, keywords, human_validated,
    legal_basis, source_url, observed_at
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
)
"""

_PARTICIPATION_INSERT = """
INSERT INTO cordis_participations (
    participation_id, project_id, project_acronym, organisation_id, vat_number,
    name, short_name, sme, activity_type, street, post_code, city, country,
    nuts_code, geolocation, organization_url, contact_form, content_update_date,
    rcn, source_order, role, ec_contribution, net_ec_contribution, total_cost,
    end_of_participation, active, record_hash, record_json, source_url, observed_at
) VALUES (
    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?
)
"""


def _batched_insert(
    conn: sqlite3.Connection,
    sql: str,
    records,
    *,
    observed_at: str,
    batch_size: int = 5000,
) -> int:
    batch = []
    count = 0
    for record in records:
        batch.append((*record.db_tuple(), observed_at))
        if len(batch) >= batch_size:
            conn.executemany(sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        conn.executemany(sql, batch)
        count += len(batch)
    return count


def ingest_cordis_snapshot(
    conn: sqlite3.Connection,
    projects: Iterable[CordisProjectRecord],
    participations: Iterable[CordisParticipationRecord],
    *,
    observed_at: str | None = None,
) -> dict[str, int]:
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()

    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM cordis_participations")
        conn.execute("DELETE FROM cordis_projects")

        project_count = _batched_insert(
            conn,
            _PROJECT_INSERT,
            projects,
            observed_at=observed_at,
        )
        if project_count == 0:
            raise ValueError("CORDIS snapshot contained zero projects")

        participation_count = _batched_insert(
            conn,
            _PARTICIPATION_INSERT,
            participations,
            observed_at=observed_at,
        )
        if participation_count == 0:
            raise ValueError("CORDIS snapshot contained zero participations")

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "projects": project_count,
        "participations": participation_count,
    }


def cordis_summary(conn: sqlite3.Connection) -> dict[str, object]:
    placeholders = ",".join("?" for _ in EU27_ISO2)
    eu_codes = tuple(sorted(EU27_ISO2))

    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM cordis_projects) AS projects,
            (SELECT COUNT(*) FROM cordis_participations) AS participations,
            COUNT(*) AS canada_participation_rows,
            COUNT(DISTINCT NULLIF(organisation_id, '')) AS canada_unique_organizations,
            COUNT(DISTINCT project_id) AS canada_unique_projects
        FROM cordis_participations
        WHERE country = 'CA'
        """
    ).fetchone()

    eu_on_canada = conn.execute(
        f"""
        WITH canada_projects AS (
            SELECT DISTINCT project_id
            FROM cordis_participations
            WHERE country = 'CA'
        )
        SELECT
            COUNT(*) AS eu_participation_rows,
            COUNT(DISTINCT NULLIF(p.organisation_id, '')) AS eu_unique_organizations,
            COUNT(DISTINCT CASE
                WHEN p.activity_type = 'PRC' THEN NULLIF(p.organisation_id, '')
            END) AS eu_prc_activity_code_unique_organizations,
            COUNT(DISTINCT p.project_id) AS shared_projects
        FROM cordis_participations p
        JOIN canada_projects c ON c.project_id = p.project_id
        WHERE p.country IN ({placeholders})
        """,
        eu_codes,
    ).fetchone()

    eu_countries = [
        dict(row)
        for row in conn.execute(
            f"""
            WITH canada_projects AS (
                SELECT DISTINCT project_id
                FROM cordis_participations
                WHERE country = 'CA'
            )
            SELECT p.country, COUNT(*) AS participation_rows
            FROM cordis_participations p
            JOIN canada_projects c ON c.project_id = p.project_id
            WHERE p.country IN ({placeholders})
            GROUP BY p.country
            ORDER BY participation_rows DESC, p.country ASC
            """,
            eu_codes,
        )
    ]

    eu_activity_types = [
        dict(row)
        for row in conn.execute(
            f"""
            WITH canada_projects AS (
                SELECT DISTINCT project_id
                FROM cordis_participations
                WHERE country = 'CA'
            )
            SELECT p.activity_type, COUNT(*) AS participation_rows
            FROM cordis_participations p
            JOIN canada_projects c ON c.project_id = p.project_id
            WHERE p.country IN ({placeholders})
            GROUP BY p.activity_type
            ORDER BY participation_rows DESC, p.activity_type ASC
            """,
            eu_codes,
        )
    ]

    return {
        "projects": totals["projects"] or 0,
        "participations": totals["participations"] or 0,
        "canada_participation_rows": totals["canada_participation_rows"] or 0,
        "canada_unique_organizations": totals["canada_unique_organizations"] or 0,
        "canada_unique_projects": totals["canada_unique_projects"] or 0,
        "eu_participation_rows_on_canada_projects": eu_on_canada["eu_participation_rows"] or 0,
        "eu_unique_organizations_on_canada_projects": eu_on_canada["eu_unique_organizations"] or 0,
        "eu_prc_activity_code_unique_organizations_on_canada_projects":
            eu_on_canada["eu_prc_activity_code_unique_organizations"] or 0,
        "canada_eu_shared_projects": eu_on_canada["shared_projects"] or 0,
        "eu_countries_on_canada_projects": eu_countries,
        "eu_activity_types_on_canada_projects": eu_activity_types,
    }
