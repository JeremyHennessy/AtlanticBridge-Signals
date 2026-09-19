from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .foreign_identity import ensure_foreign_identity_schema

SCHEMA = """
CREATE TABLE IF NOT EXISTS curated_identity_queue (
    queue_id TEXT PRIMARY KEY,
    outcome_record_id TEXT NOT NULL,
    task_type TEXT NOT NULL CHECK (
        task_type IN (
            'NAMED_INVESTOR_IDENTITY',
            'CANADIAN_VEHICLE_PARENT',
            'NAMED_INVESTOR_PARENT'
        )
    ),
    source_foreign_run_id TEXT NOT NULL,
    source_resolution_status TEXT NOT NULL,
    certification_month TEXT NOT NULL,
    ultimate_control_country TEXT NOT NULL,
    investor_name TEXT NOT NULL,
    investor_locality TEXT NOT NULL,
    canadian_entry_corporation_number TEXT NOT NULL,
    source_confirmed_lei TEXT NOT NULL,
    source_confirmed_legal_name TEXT NOT NULL,
    source_confirmed_jurisdiction TEXT NOT NULL,
    source_query_url TEXT NOT NULL,
    source_candidate_snapshot_json TEXT NOT NULL,
    priority INTEGER NOT NULL,
    review_status TEXT NOT NULL CHECK (
        review_status IN (
            'OPEN',
            'CONFIRMED',
            'BLOCKED',
            'INSUFFICIENT_EVIDENCE',
            'REJECTED',
            'RESOLVED_UPSTREAM'
        )
    ),
    resolved_subject_type TEXT NOT NULL DEFAULT '' CHECK (
        resolved_subject_type IN ('', 'LEGAL_ENTITY', 'NATURAL_PERSON')
    ),
    resolved_subject_name TEXT NOT NULL DEFAULT '',
    resolved_jurisdiction TEXT NOT NULL DEFAULT '',
    resolved_identifier_type TEXT NOT NULL DEFAULT '',
    resolved_identifier_value TEXT NOT NULL DEFAULT '',
    decision_basis TEXT NOT NULL DEFAULT '',
    decision_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_curated_identity_status
ON curated_identity_queue(review_status, priority);

CREATE INDEX IF NOT EXISTS idx_curated_identity_outcome
ON curated_identity_queue(outcome_record_id);

CREATE TABLE IF NOT EXISTS curated_identity_evidence (
    evidence_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    evidence_type TEXT NOT NULL CHECK (
        evidence_type IN (
            'OFFICIAL_COMPANY_SITE',
            'OFFICIAL_REGISTRY',
            'OFFICIAL_GOVERNMENT_FILING',
            'OFFICIAL_STOCK_EXCHANGE_FILING',
            'OTHER_REFERENCE'
        )
    ),
    is_primary_source INTEGER NOT NULL CHECK (is_primary_source IN (0, 1)),
    source_url TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_publisher TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    subject_type TEXT NOT NULL CHECK (
        subject_type IN ('UNKNOWN', 'LEGAL_ENTITY', 'NATURAL_PERSON')
    ),
    subject_name TEXT NOT NULL,
    jurisdiction TEXT NOT NULL,
    identifier_type TEXT NOT NULL,
    identifier_value TEXT NOT NULL,
    relationship_type TEXT NOT NULL,
    related_subject_type TEXT NOT NULL CHECK (
        related_subject_type IN ('UNKNOWN', 'LEGAL_ENTITY', 'NATURAL_PERSON')
    ),
    related_subject_name TEXT NOT NULL,
    related_identifier_type TEXT NOT NULL,
    related_identifier_value TEXT NOT NULL,
    evidence_note TEXT NOT NULL,
    evidence_hash TEXT NOT NULL,
    FOREIGN KEY (queue_id)
        REFERENCES curated_identity_queue(queue_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_curated_evidence_queue
ON curated_identity_evidence(queue_id);

CREATE TABLE IF NOT EXISTS curated_identity_decisions (
    decision_id TEXT PRIMARY KEY,
    queue_id TEXT NOT NULL,
    decision_state TEXT NOT NULL CHECK (
        decision_state IN (
            'CONFIRMED',
            'BLOCKED',
            'INSUFFICIENT_EVIDENCE',
            'REJECTED'
        )
    ),
    resolved_subject_type TEXT NOT NULL CHECK (
        resolved_subject_type IN ('LEGAL_ENTITY', 'NATURAL_PERSON')
    ),
    resolved_subject_name TEXT NOT NULL,
    resolved_jurisdiction TEXT NOT NULL,
    resolved_identifier_type TEXT NOT NULL,
    resolved_identifier_value TEXT NOT NULL,
    decision_basis TEXT NOT NULL,
    evidence_ids_json TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (queue_id)
        REFERENCES curated_identity_queue(queue_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_curated_decisions_queue
ON curated_identity_decisions(queue_id, decided_at);
"""

PRIMARY_EVIDENCE_TYPES = {
    "OFFICIAL_COMPANY_SITE",
    "OFFICIAL_REGISTRY",
    "OFFICIAL_GOVERNMENT_FILING",
    "OFFICIAL_STOCK_EXCHANGE_FILING",
}

_TASK_MAP = {
    "REVIEW_READY_EXACT_NAME": ("NAMED_INVESTOR_IDENTITY", 10),
    "QUERY_ERROR": ("NAMED_INVESTOR_IDENTITY", 15),
    "CONFIRMED_CANADIAN_NAMED_INVESTOR_PARENT_UNRESOLVED":
        ("NAMED_INVESTOR_PARENT", 20),
    "AMBIGUOUS_EXACT": ("NAMED_INVESTOR_IDENTITY", 25),
    "UNRESOLVED": ("NAMED_INVESTOR_IDENTITY", 30),
    "NO_RESULTS": ("NAMED_INVESTOR_IDENTITY", 35),
    "CANADIAN_VEHICLE_PARENT_UNRESOLVED": ("CANADIAN_VEHICLE_PARENT", 40),
}


def ensure_curated_identity_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _latest_foreign_run(conn: sqlite3.Connection):
    return conn.execute(
        """
        SELECT run_id
        FROM foreign_identity_runs
        ORDER BY observed_at DESC
        LIMIT 1
        """
    ).fetchone()


def _queue_id(outcome_record_id: str, task_type: str) -> str:
    return hashlib.sha256(
        f"{outcome_record_id}\x1f{task_type}".encode("utf-8")
    ).hexdigest()


def _source_rows(conn: sqlite3.Connection, run_id: str):
    return conn.execute(
        """
        SELECT
            outcome_record_id,
            certification_month,
            ultimate_control_country,
            investor_name,
            investor_locality,
            canadian_entry_corporation_number,
            resolution_status,
            query_url,
            confirmed_lei,
            confirmed_legal_name,
            confirmed_jurisdiction,
            candidate_snapshot_json
        FROM foreign_identity_resolutions
        WHERE run_id = ?
        ORDER BY certification_month, investor_name, outcome_record_id
        """,
        (run_id,),
    ).fetchall()


def seed_curated_identity_queue(
    conn: sqlite3.Connection,
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_foreign_identity_schema(conn)
    ensure_curated_identity_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()

    run = _latest_foreign_run(conn)
    if run is None:
        raise ValueError(
            "Curated identity queue requires a completed foreign-identity run"
        )
    foreign_run_id = run["run_id"]
    source_rows = _source_rows(conn, foreign_run_id)

    desired: dict[str, dict[str, object]] = {}
    for row in source_rows:
        mapping = _TASK_MAP.get(row["resolution_status"])
        if mapping is None:
            continue
        task_type, priority = mapping
        queue_id = _queue_id(row["outcome_record_id"], task_type)
        desired[queue_id] = {
            "queue_id": queue_id,
            "outcome_record_id": row["outcome_record_id"],
            "task_type": task_type,
            "source_foreign_run_id": foreign_run_id,
            "source_resolution_status": row["resolution_status"],
            "certification_month": row["certification_month"],
            "ultimate_control_country": row["ultimate_control_country"],
            "investor_name": row["investor_name"],
            "investor_locality": row["investor_locality"],
            "canadian_entry_corporation_number":
                row["canadian_entry_corporation_number"],
            "source_confirmed_lei": row["confirmed_lei"],
            "source_confirmed_legal_name": row["confirmed_legal_name"],
            "source_confirmed_jurisdiction": row["confirmed_jurisdiction"],
            "source_query_url": row["query_url"],
            "source_candidate_snapshot_json": row["candidate_snapshot_json"],
            "priority": priority,
        }

    conn.execute("BEGIN")
    try:
        current_rows = conn.execute(
            """
            SELECT queue_id, review_status
            FROM curated_identity_queue
            """
        ).fetchall()
        current = {row["queue_id"]: row["review_status"] for row in current_rows}

        for queue_id, data in desired.items():
            existing_status = current.get(queue_id)
            if existing_status in {
                "CONFIRMED",
                "BLOCKED",
                "INSUFFICIENT_EVIDENCE",
                "REJECTED",
            }:
                review_status = existing_status
            else:
                review_status = "OPEN"

            conn.execute(
                """
                INSERT INTO curated_identity_queue (
                    queue_id,
                    outcome_record_id,
                    task_type,
                    source_foreign_run_id,
                    source_resolution_status,
                    certification_month,
                    ultimate_control_country,
                    investor_name,
                    investor_locality,
                    canadian_entry_corporation_number,
                    source_confirmed_lei,
                    source_confirmed_legal_name,
                    source_confirmed_jurisdiction,
                    source_query_url,
                    source_candidate_snapshot_json,
                    priority,
                    review_status,
                    created_at,
                    updated_at
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(queue_id) DO UPDATE SET
                    source_foreign_run_id = excluded.source_foreign_run_id,
                    source_resolution_status = excluded.source_resolution_status,
                    certification_month = excluded.certification_month,
                    ultimate_control_country = excluded.ultimate_control_country,
                    investor_name = excluded.investor_name,
                    investor_locality = excluded.investor_locality,
                    canadian_entry_corporation_number =
                        excluded.canadian_entry_corporation_number,
                    source_confirmed_lei = excluded.source_confirmed_lei,
                    source_confirmed_legal_name =
                        excluded.source_confirmed_legal_name,
                    source_confirmed_jurisdiction =
                        excluded.source_confirmed_jurisdiction,
                    source_query_url = excluded.source_query_url,
                    source_candidate_snapshot_json =
                        excluded.source_candidate_snapshot_json,
                    priority = excluded.priority,
                    review_status = CASE
                        WHEN curated_identity_queue.review_status IN (
                            'CONFIRMED',
                            'BLOCKED',
                            'INSUFFICIENT_EVIDENCE',
                            'REJECTED'
                        )
                        THEN curated_identity_queue.review_status
                        ELSE excluded.review_status
                    END,
                    updated_at = excluded.updated_at
                """,
                (
                    data["queue_id"],
                    data["outcome_record_id"],
                    data["task_type"],
                    data["source_foreign_run_id"],
                    data["source_resolution_status"],
                    data["certification_month"],
                    data["ultimate_control_country"],
                    data["investor_name"],
                    data["investor_locality"],
                    data["canadian_entry_corporation_number"],
                    data["source_confirmed_lei"],
                    data["source_confirmed_legal_name"],
                    data["source_confirmed_jurisdiction"],
                    data["source_query_url"],
                    data["source_candidate_snapshot_json"],
                    data["priority"],
                    review_status,
                    observed_at,
                    observed_at,
                ),
            )

        if desired:
            placeholders = ",".join("?" for _ in desired)
            conn.execute(
                f"""
                UPDATE curated_identity_queue
                SET
                    review_status = CASE
                        WHEN review_status IN (
                            'CONFIRMED',
                            'BLOCKED',
                            'INSUFFICIENT_EVIDENCE',
                            'REJECTED'
                        )
                        THEN review_status
                        ELSE 'RESOLVED_UPSTREAM'
                    END,
                    updated_at = ?
                WHERE queue_id NOT IN ({placeholders})
                  AND review_status NOT IN (
                      'CONFIRMED',
                      'BLOCKED',
                      'INSUFFICIENT_EVIDENCE',
                      'REJECTED'
                  )
                """,
                (observed_at, *desired.keys()),
            )
        else:
            conn.execute(
                """
                UPDATE curated_identity_queue
                SET
                    review_status = CASE
                        WHEN review_status IN (
                            'CONFIRMED',
                            'BLOCKED',
                            'INSUFFICIENT_EVIDENCE',
                            'REJECTED'
                        )
                        THEN review_status
                        ELSE 'RESOLVED_UPSTREAM'
                    END,
                    updated_at = ?
                """,
                (observed_at,),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    return curated_identity_summary(conn)


def _evidence_hash(queue_id: str, evidence: dict[str, object]) -> str:
    material = _canonical_json(
        {
            "queue_id": queue_id,
            "evidence_type": _clean(evidence.get("evidence_type")),
            "source_url": _clean(evidence.get("source_url")),
            "subject_type": _clean(evidence.get("subject_type")).upper() or "UNKNOWN",
            "subject_name": _clean(
                evidence.get("subject_name") or evidence.get("legal_name")
            ),
            "jurisdiction": _clean(evidence.get("jurisdiction")),
            "identifier_type": _clean(evidence.get("identifier_type")),
            "identifier_value": _clean(evidence.get("identifier_value")),
            "relationship_type": _clean(evidence.get("relationship_type")),
            "related_subject_type":
                _clean(evidence.get("related_subject_type")).upper() or "UNKNOWN",
            "related_subject_name": _clean(evidence.get("related_subject_name")),
            "related_identifier_type":
                _clean(evidence.get("related_identifier_type")),
            "related_identifier_value":
                _clean(evidence.get("related_identifier_value")),
        }
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _insert_evidence(
    conn: sqlite3.Connection,
    queue_id: str,
    evidence: dict[str, object],
    *,
    default_observed_at: str,
) -> str:
    evidence_type = _clean(evidence.get("evidence_type")).upper()
    allowed = PRIMARY_EVIDENCE_TYPES | {"OTHER_REFERENCE"}
    if evidence_type not in allowed:
        raise ValueError(f"Unsupported curated evidence_type: {evidence_type!r}")

    source_url = _clean(evidence.get("source_url"))
    if not source_url.startswith(("https://", "http://")):
        raise ValueError("Curated identity evidence requires an http(s) source_url")

    evidence_hash = _evidence_hash(queue_id, evidence)
    evidence_id = hashlib.sha256(
        f"{queue_id}\x1f{evidence_hash}".encode("utf-8")
    ).hexdigest()

    conn.execute(
        """
        INSERT INTO curated_identity_evidence (
            evidence_id,
            queue_id,
            evidence_type,
            is_primary_source,
            source_url,
            source_title,
            source_publisher,
            observed_at,
            subject_type,
            subject_name,
            jurisdiction,
            identifier_type,
            identifier_value,
            relationship_type,
            related_subject_type,
            related_subject_name,
            related_identifier_type,
            related_identifier_value,
            evidence_note,
            evidence_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(evidence_id) DO UPDATE SET
            source_title = excluded.source_title,
            source_publisher = excluded.source_publisher,
            observed_at = excluded.observed_at,
            evidence_note = excluded.evidence_note
        """,
        (
            evidence_id,
            queue_id,
            evidence_type,
            int(evidence_type in PRIMARY_EVIDENCE_TYPES),
            source_url,
            _clean(evidence.get("source_title")),
            _clean(evidence.get("source_publisher")),
            _clean(evidence.get("observed_at")) or default_observed_at,
            _clean(evidence.get("subject_type")).upper() or "UNKNOWN",
            _clean(evidence.get("subject_name") or evidence.get("legal_name")),
            _clean(evidence.get("jurisdiction")),
            _clean(evidence.get("identifier_type")),
            _clean(evidence.get("identifier_value")),
            _clean(evidence.get("relationship_type")),
            _clean(evidence.get("related_subject_type")).upper() or "UNKNOWN",
            _clean(evidence.get("related_subject_name")),
            _clean(evidence.get("related_identifier_type")),
            _clean(evidence.get("related_identifier_value")),
            _clean(evidence.get("evidence_note")),
            evidence_hash,
        ),
    )
    return evidence_id


def _primary_evidence_count(conn: sqlite3.Connection, queue_id: str) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM curated_identity_evidence
            WHERE queue_id = ?
              AND is_primary_source = 1
            """,
            (queue_id,),
        ).fetchone()[0]
    )


def _apply_decision(
    conn: sqlite3.Connection,
    queue_id: str,
    decision: dict[str, object],
    *,
    evidence_ids: list[str],
    decided_at: str,
) -> str:
    state = _clean(decision.get("state")).upper()
    if state not in {
        "CONFIRMED",
        "BLOCKED",
        "INSUFFICIENT_EVIDENCE",
        "REJECTED",
    }:
        raise ValueError(f"Unsupported curated identity decision state: {state!r}")

    queue = conn.execute(
        """
        SELECT task_type
        FROM curated_identity_queue
        WHERE queue_id = ?
        """,
        (queue_id,),
    ).fetchone()
    if queue is None:
        raise ValueError(f"Unknown curated identity queue_id: {queue_id}")

    subject_type = _clean(decision.get("resolved_subject_type")).upper()
    subject_name = _clean(
        decision.get("resolved_subject_name")
        or decision.get("resolved_legal_name")
    )
    jurisdiction = _clean(decision.get("resolved_jurisdiction"))
    identifier_type = _clean(decision.get("resolved_identifier_type"))
    identifier_value = _clean(decision.get("resolved_identifier_value"))
    basis = _clean(decision.get("basis"))

    if state == "CONFIRMED":
        if _primary_evidence_count(conn, queue_id) < 1:
            raise ValueError(
                "CONFIRMED curated identity decisions require primary-source evidence"
            )
        if subject_type not in {"LEGAL_ENTITY", "NATURAL_PERSON"}:
            raise ValueError(
                "CONFIRMED curated identity decisions require "
                "resolved_subject_type LEGAL_ENTITY or NATURAL_PERSON"
            )
        if not subject_name:
            raise ValueError(
                "CONFIRMED curated identity decisions require resolved_subject_name"
            )
        if subject_type == "LEGAL_ENTITY" and not jurisdiction:
            raise ValueError(
                "CONFIRMED LEGAL_ENTITY decisions require resolved_jurisdiction"
            )
    elif not basis:
        raise ValueError(
            f"{state} curated identity decisions require a non-empty basis"
        )

    decision_payload = {
        "queue_id": queue_id,
        "state": state,
        "resolved_subject_type": subject_type,
        "resolved_subject_name": subject_name,
        "resolved_jurisdiction": jurisdiction,
        "resolved_identifier_type": identifier_type,
        "resolved_identifier_value": identifier_value,
        "basis": basis,
        "evidence_ids": sorted(evidence_ids),
    }
    decision_id = hashlib.sha256(
        _canonical_json(decision_payload).encode("utf-8")
    ).hexdigest()

    conn.execute(
        """
        INSERT OR IGNORE INTO curated_identity_decisions (
            decision_id,
            queue_id,
            decision_state,
            resolved_subject_type,
            resolved_subject_name,
            resolved_jurisdiction,
            resolved_identifier_type,
            resolved_identifier_value,
            decision_basis,
            evidence_ids_json,
            decided_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            queue_id,
            state,
            subject_type,
            subject_name,
            jurisdiction,
            identifier_type,
            identifier_value,
            basis,
            _canonical_json(sorted(evidence_ids)),
            decided_at,
        ),
    )

    conn.execute(
        """
        UPDATE curated_identity_queue
        SET
            review_status = ?,
            resolved_subject_type = ?,
            resolved_subject_name = ?,
            resolved_jurisdiction = ?,
            resolved_identifier_type = ?,
            resolved_identifier_value = ?,
            decision_basis = ?,
            decision_at = ?,
            updated_at = ?
        WHERE queue_id = ?
        """,
        (
            state,
            subject_type,
            subject_name,
            jurisdiction,
            identifier_type,
            identifier_value,
            basis,
            decided_at,
            decided_at,
            queue_id,
        ),
    )
    return decision_id


def apply_curated_identity_review(
    conn: sqlite3.Connection,
    payload: dict[str, object] | list[dict[str, object]],
    *,
    observed_at: str | None = None,
) -> dict[str, object]:
    ensure_curated_identity_schema(conn)
    observed_at = observed_at or datetime.now(timezone.utc).isoformat()
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        raise ValueError("Curated identity review file contained no items")

    evidence_count = 0
    decision_count = 0

    conn.execute("BEGIN")
    try:
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Curated identity review items must be objects")
            queue_id = _clean(item.get("queue_id"))
            if not queue_id:
                raise ValueError("Curated identity review item requires queue_id")
            if conn.execute(
                "SELECT 1 FROM curated_identity_queue WHERE queue_id = ?",
                (queue_id,),
            ).fetchone() is None:
                raise ValueError(f"Unknown curated identity queue_id: {queue_id}")

            inserted_ids: list[str] = []
            evidence_rows = item.get("evidence") or []
            if not isinstance(evidence_rows, list):
                raise ValueError("Curated identity evidence must be a list")
            for evidence in evidence_rows:
                if not isinstance(evidence, dict):
                    raise ValueError("Curated identity evidence rows must be objects")
                evidence_id = _insert_evidence(
                    conn,
                    queue_id,
                    evidence,
                    default_observed_at=observed_at,
                )
                inserted_ids.append(evidence_id)
                evidence_count += 1

            decision = item.get("decision")
            if decision is not None:
                if not isinstance(decision, dict):
                    raise ValueError("Curated identity decision must be an object")
                _apply_decision(
                    conn,
                    queue_id,
                    decision,
                    evidence_ids=inserted_ids,
                    decided_at=observed_at,
                )
                decision_count += 1

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    summary = curated_identity_summary(conn)
    return {
        "items_processed": len(items),
        "evidence_rows_processed": evidence_count,
        "decisions_processed": decision_count,
        "summary": summary,
    }


def apply_curated_identity_review_file(
    conn: sqlite3.Connection,
    path: str | Path,
) -> dict[str, object]:
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return apply_curated_identity_review(conn, payload)


def curated_identity_summary(conn: sqlite3.Connection) -> dict[str, object]:
    ensure_curated_identity_schema(conn)

    counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT review_status, COUNT(*) AS records
            FROM curated_identity_queue
            GROUP BY review_status
            ORDER BY review_status
            """
        )
    ]
    task_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT task_type, COUNT(*) AS records
            FROM curated_identity_queue
            WHERE review_status <> 'RESOLVED_UPSTREAM'
            GROUP BY task_type
            ORDER BY task_type
            """
        )
    ]
    evidence_counts = [
        dict(row)
        for row in conn.execute(
            """
            SELECT evidence_type, COUNT(*) AS records
            FROM curated_identity_evidence
            GROUP BY evidence_type
            ORDER BY evidence_type
            """
        )
    ]
    queue = [
        dict(row)
        for row in conn.execute(
            """
            SELECT
                queue_id,
                priority,
                task_type,
                review_status,
                source_resolution_status,
                certification_month,
                ultimate_control_country,
                investor_name,
                investor_locality,
                canadian_entry_corporation_number,
                source_confirmed_legal_name,
                source_confirmed_jurisdiction,
                resolved_subject_type,
                resolved_subject_name,
                resolved_jurisdiction,
                resolved_identifier_type,
                resolved_identifier_value,
                decision_basis,
                (
                    SELECT COUNT(*)
                    FROM curated_identity_evidence e
                    WHERE e.queue_id = curated_identity_queue.queue_id
                ) AS evidence_count,
                (
                    SELECT COUNT(*)
                    FROM curated_identity_evidence e
                    WHERE e.queue_id = curated_identity_queue.queue_id
                      AND e.is_primary_source = 1
                ) AS primary_evidence_count
            FROM curated_identity_queue
            WHERE review_status <> 'RESOLVED_UPSTREAM'
            ORDER BY
                CASE review_status
                    WHEN 'OPEN' THEN 0
                    WHEN 'INSUFFICIENT_EVIDENCE' THEN 1
                    WHEN 'BLOCKED' THEN 2
                    WHEN 'CONFIRMED' THEN 3
                    WHEN 'REJECTED' THEN 4
                    ELSE 5
                END,
                priority,
                certification_month DESC,
                investor_name,
                queue_id
            """
        )
    ]

    total = sum(int(row["records"]) for row in counts)
    confirmed = next(
        (
            int(row["records"])
            for row in counts
            if row["review_status"] == "CONFIRMED"
        ),
        0,
    )
    confirmed_legal_entities = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM curated_identity_queue
            WHERE review_status = 'CONFIRMED'
              AND resolved_subject_type = 'LEGAL_ENTITY'
            """
        ).fetchone()[0]
    )
    confirmed_natural_persons = int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM curated_identity_queue
            WHERE review_status = 'CONFIRMED'
              AND resolved_subject_type = 'NATURAL_PERSON'
            """
        ).fetchone()[0]
    )
    open_records = next(
        (
            int(row["records"])
            for row in counts
            if row["review_status"] == "OPEN"
        ),
        0,
    )

    return {
        "total_queue_records": total,
        "active_queue_records": len(queue),
        "confirmed_reviews": confirmed,
        "confirmed_legal_entities": confirmed_legal_entities,
        "confirmed_natural_persons": confirmed_natural_persons,
        "open_reviews": open_records,
        "status_counts": counts,
        "task_counts": task_counts,
        "evidence_type_counts": evidence_counts,
        "modeling_ready_curated_records": confirmed_legal_entities,
        "queue": queue,
    }
