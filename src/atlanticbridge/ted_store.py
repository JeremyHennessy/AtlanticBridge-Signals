from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone

from .sources.ted import SOURCE_NAME, TEDSearchResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS ted_search_runs (
    search_run_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    scope TEXT NOT NULL,
    page_size INTEGER NOT NULL,
    only_latest_versions INTEGER NOT NULL CHECK (only_latest_versions IN (0, 1)),
    query_text TEXT NOT NULL,
    query_body_json TEXT NOT NULL,
    query_hash TEXT NOT NULL,
    response_hash TEXT NOT NULL,
    total_notice_count INTEGER NOT NULL,
    returned_notice_count INTEGER NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ted_search_window
ON ted_search_runs(start_date, end_date);

CREATE TABLE IF NOT EXISTS ted_award_notices (
    publication_number TEXT PRIMARY KEY,
    publication_date TEXT NOT NULL,
    notice_type TEXT NOT NULL,
    notice_title_json TEXT NOT NULL,
    procedure_title_json TEXT NOT NULL,
    cpv_json TEXT NOT NULL,
    winner_names_json TEXT NOT NULL,
    winner_countries_json TEXT NOT NULL,
    winner_identifiers_json TEXT NOT NULL,
    winner_decision_dates_json TEXT NOT NULL,
    tender_value_json TEXT NOT NULL,
    tender_value_currency_json TEXT NOT NULL,
    total_value_json TEXT NOT NULL,
    total_value_currency_json TEXT NOT NULL,
    links_json TEXT NOT NULL,
    english_url TEXT NOT NULL,
    raw_record_hash TEXT NOT NULL,
    raw_record_json TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ted_notice_date
ON ted_award_notices(publication_date);

CREATE INDEX IF NOT EXISTS idx_ted_notice_type
ON ted_award_notices(notice_type);

CREATE TABLE IF NOT EXISTS ted_winner_mentions (
    publication_number TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    winner_name TEXT NOT NULL,
    languages_json TEXT NOT NULL,
    alignment_status TEXT NOT NULL CHECK (
        alignment_status IN ('SINGLE_WINNER_ALIGNED', 'NAME_ONLY_UNALIGNED')
    ),
    winner_country TEXT NOT NULL,
    winner_identifier TEXT NOT NULL,
    winner_decision_date TEXT NOT NULL,
    first_observed_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    PRIMARY KEY (publication_number, normalized_name),
    FOREIGN KEY (publication_number)
        REFERENCES ted_award_notices(publication_number)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ted_winner_name
ON ted_winner_mentions(normalized_name);

CREATE INDEX IF NOT EXISTS idx_ted_winner_country
ON ted_winner_mentions(winner_country);

CREATE TABLE IF NOT EXISTS ted_search_run_notices (
    search_run_id TEXT NOT NULL,
    publication_number TEXT NOT NULL,
    PRIMARY KEY (search_run_id, publication_number),
    FOREIGN KEY (search_run_id)
        REFERENCES ted_search_runs(search_run_id)
        ON DELETE CASCADE,
    FOREIGN KEY (publication_number)
        REFERENCES ted_award_notices(publication_number)
        ON DELETE CASCADE
);
"""


def ensure_ted_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _field_json(payload: dict[str, object], field: str) -> str:
    return json.dumps(
        payload.get(field),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _search_run_id(result: TEDSearchResult) -> str:
    material = "\x1f".join([result.query_hash, result.response_hash])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def ingest_ted_search_result(
    conn: sqlite3.Connection,
    result: TEDSearchResult,
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_ted_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    search_run_id = _search_run_id(result)

    conn.execute("BEGIN")
    try:
        conn.execute(
            """
            INSERT INTO ted_search_runs (
                search_run_id,
                source_name,
                start_date,
                end_date,
                scope,
                page_size,
                only_latest_versions,
                query_text,
                query_body_json,
                query_hash,
                response_hash,
                total_notice_count,
                returned_notice_count,
                first_observed_at,
                last_observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(search_run_id) DO UPDATE SET
                total_notice_count = excluded.total_notice_count,
                returned_notice_count = excluded.returned_notice_count,
                last_observed_at = excluded.last_observed_at
            """,
            (
                search_run_id,
                SOURCE_NAME,
                result.start_date,
                result.end_date,
                result.scope,
                result.page_size,
                int(result.only_latest_versions),
                result.query,
                result.query_body_json,
                result.query_hash,
                result.response_hash,
                result.total_notice_count,
                len(result.notices),
                observed_at,
                observed_at,
            ),
        )

        aligned_mentions = 0
        unaligned_mentions = 0
        winner_mentions = 0

        for notice in result.notices:
            payload = notice.payload
            conn.execute(
                """
                INSERT INTO ted_award_notices (
                    publication_number,
                    publication_date,
                    notice_type,
                    notice_title_json,
                    procedure_title_json,
                    cpv_json,
                    winner_names_json,
                    winner_countries_json,
                    winner_identifiers_json,
                    winner_decision_dates_json,
                    tender_value_json,
                    tender_value_currency_json,
                    total_value_json,
                    total_value_currency_json,
                    links_json,
                    english_url,
                    raw_record_hash,
                    raw_record_json,
                    first_observed_at,
                    last_observed_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(publication_number) DO UPDATE SET
                    publication_date = excluded.publication_date,
                    notice_type = excluded.notice_type,
                    notice_title_json = excluded.notice_title_json,
                    procedure_title_json = excluded.procedure_title_json,
                    cpv_json = excluded.cpv_json,
                    winner_names_json = excluded.winner_names_json,
                    winner_countries_json = excluded.winner_countries_json,
                    winner_identifiers_json = excluded.winner_identifiers_json,
                    winner_decision_dates_json = excluded.winner_decision_dates_json,
                    tender_value_json = excluded.tender_value_json,
                    tender_value_currency_json = excluded.tender_value_currency_json,
                    total_value_json = excluded.total_value_json,
                    total_value_currency_json = excluded.total_value_currency_json,
                    links_json = excluded.links_json,
                    english_url = excluded.english_url,
                    raw_record_hash = excluded.raw_record_hash,
                    raw_record_json = excluded.raw_record_json,
                    last_observed_at = excluded.last_observed_at
                """,
                (
                    notice.publication_number,
                    notice.publication_date,
                    notice.notice_type,
                    _field_json(payload, "notice-title"),
                    _field_json(payload, "title-proc"),
                    _field_json(payload, "classification-cpv"),
                    _field_json(payload, "winner-name"),
                    _field_json(payload, "winner-country"),
                    _field_json(payload, "winner-identifier"),
                    _field_json(payload, "winner-decision-date"),
                    _field_json(payload, "tender-value"),
                    _field_json(payload, "tender-value-cur"),
                    _field_json(payload, "total-value"),
                    _field_json(payload, "total-value-cur"),
                    _field_json(payload, "links"),
                    notice.english_url,
                    notice.raw_record_hash,
                    notice.raw_record_json,
                    observed_at,
                    observed_at,
                ),
            )

            conn.execute(
                "DELETE FROM ted_winner_mentions WHERE publication_number = ?",
                (notice.publication_number,),
            )

            for mention in notice.winner_mentions():
                winner_mentions += 1
                if mention.alignment_status == "SINGLE_WINNER_ALIGNED":
                    aligned_mentions += 1
                else:
                    unaligned_mentions += 1

                conn.execute(
                    """
                    INSERT INTO ted_winner_mentions (
                        publication_number,
                        normalized_name,
                        winner_name,
                        languages_json,
                        alignment_status,
                        winner_country,
                        winner_identifier,
                        winner_decision_date,
                        first_observed_at,
                        last_observed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        notice.publication_number,
                        mention.normalized_name,
                        mention.winner_name,
                        json.dumps(
                            list(mention.languages),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        mention.alignment_status,
                        mention.winner_country,
                        mention.winner_identifier,
                        mention.winner_decision_date,
                        observed_at,
                        observed_at,
                    ),
                )

            conn.execute(
                """
                INSERT OR IGNORE INTO ted_search_run_notices (
                    search_run_id,
                    publication_number
                ) VALUES (?, ?)
                """,
                (search_run_id, notice.publication_number),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return {
        "search_run_id": search_run_id,
        "total_notice_count": result.total_notice_count,
        "returned_notice_count": len(result.notices),
        "winner_mentions": winner_mentions,
        "aligned_winner_mentions": aligned_mentions,
        "unaligned_winner_mentions": unaligned_mentions,
        "query_hash": result.query_hash,
        "response_hash": result.response_hash,
    }


def ted_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_ted_schema(conn)

    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM ted_search_runs) AS search_runs,
            (SELECT COUNT(*) FROM ted_award_notices) AS notices,
            (SELECT COUNT(*) FROM ted_winner_mentions) AS winner_mentions,
            (
                SELECT COUNT(*)
                FROM ted_winner_mentions
                WHERE alignment_status = 'SINGLE_WINNER_ALIGNED'
            ) AS aligned_winner_mentions,
            (
                SELECT COUNT(*)
                FROM ted_winner_mentions
                WHERE alignment_status = 'NAME_ONLY_UNALIGNED'
            ) AS unaligned_winner_mentions,
            (
                SELECT COUNT(DISTINCT normalized_name)
                FROM ted_winner_mentions
            ) AS unique_winner_names,
            (SELECT MIN(publication_date) FROM ted_award_notices) AS earliest_publication_date,
            (SELECT MAX(publication_date) FROM ted_award_notices) AS latest_publication_date
        """
    ).fetchone()

    by_type = [
        dict(row)
        for row in conn.execute(
            """
            SELECT notice_type, COUNT(*) AS notices
            FROM ted_award_notices
            GROUP BY notice_type
            ORDER BY notices DESC, notice_type ASC
            """
        )
    ]

    aligned_countries = [
        dict(row)
        for row in conn.execute(
            """
            SELECT winner_country, COUNT(*) AS winner_mentions
            FROM ted_winner_mentions
            WHERE alignment_status = 'SINGLE_WINNER_ALIGNED'
              AND winner_country <> ''
            GROUP BY winner_country
            ORDER BY winner_mentions DESC, winner_country ASC
            LIMIT 40
            """
        )
    ]

    return {
        "search_runs": totals["search_runs"] or 0,
        "notices": totals["notices"] or 0,
        "winner_mentions": totals["winner_mentions"] or 0,
        "aligned_winner_mentions": totals["aligned_winner_mentions"] or 0,
        "unaligned_winner_mentions": totals["unaligned_winner_mentions"] or 0,
        "unique_winner_names": totals["unique_winner_names"] or 0,
        "earliest_publication_date": totals["earliest_publication_date"],
        "latest_publication_date": totals["latest_publication_date"],
        "notices_by_type": by_type,
        "aligned_winner_countries": aligned_countries,
    }
