from __future__ import annotations

from calendar import monthrange
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re


SNAPSHOT_STATES = {
    "PRESENT",
    "ABSENT_WITH_PROVEN_COVERAGE",
    "UNKNOWN_UNVERIFIED_COVERAGE",
}
OFFSETS_MONTHS = (24, 12, 6, 3)
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})$")


def month_start(value: str) -> date:
    match = _MONTH_RE.fullmatch(value)
    if not match:
        raise ValueError(f"invalid month: {value}")
    return date(int(match.group(1)), int(match.group(2)), 1)


def subtract_months(value: date, months: int) -> date:
    total = value.year * 12 + value.month - 1 - months
    return date(total // 12, total % 12 + 1, 1)


def cutoff_exclusive(anchor_month: str, offset_months: int) -> date:
    if offset_months <= 0:
        raise ValueError("offset_months must be positive")
    return subtract_months(month_start(anchor_month), offset_months)


def publication_interval(value: str, precision: str) -> tuple[date, date]:
    precision = precision.upper()
    if precision == "DAY":
        parsed = date.fromisoformat(value)
        return parsed, parsed
    if precision == "MONTH":
        year, month = map(int, value.split("-"))
        return (
            date(year, month, 1),
            date(year, month, monthrange(year, month)[1]),
        )
    if precision == "YEAR":
        year = int(value)
        return date(year, 1, 1), date(year, 12, 31)
    raise ValueError("precision must be DAY, MONTH, or YEAR")


def evidence_available_before(
    evidence: dict[str, object],
    cutoff: date,
) -> bool:
    available = str(evidence.get("publicly_available_date") or "").strip()
    precision = str(
        evidence.get("publicly_available_date_precision") or ""
    ).strip()
    if not available or not precision:
        return False
    _, interval_end = publication_interval(available, precision)
    return interval_end < cutoff


def _coverage_index(
    evidence_payload: dict[str, object],
) -> dict[tuple[str, str], dict[str, object]]:
    rows = evidence_payload.get("coverage")
    if not isinstance(rows, list):
        raise ValueError("signal evidence payload requires coverage list")
    index: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("coverage rows must be objects")
        key = (str(row.get("entity_id") or ""), str(row.get("signal_family") or ""))
        if not all(key):
            raise ValueError("coverage row requires entity_id and signal_family")
        if key in index:
            raise ValueError(f"duplicate coverage row: {key}")
        index[key] = row
    return index


def _evidence_index(
    evidence_payload: dict[str, object],
) -> dict[tuple[str, str], list[dict[str, object]]]:
    rows = evidence_payload.get("records")
    if not isinstance(rows, list):
        raise ValueError("signal evidence payload requires records list")
    index: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("signal evidence rows must be objects")
        key = (str(row.get("entity_id") or ""), str(row.get("signal_family") or ""))
        if not all(key):
            raise ValueError("signal evidence row requires entity_id and signal_family")
        if not row.get("publicly_available_date") or not row.get(
            "publicly_available_date_precision"
        ):
            raise ValueError(f"signal evidence lacks public availability: {key}")
        index.setdefault(key, []).append(row)
    for rows_for_key in index.values():
        rows_for_key.sort(
            key=lambda item: (
                str(item["publicly_available_date"]),
                str(item.get("evidence_id") or ""),
            )
        )
    return index


def build_event_time_snapshots(
    *,
    entities_payload: dict[str, object],
    semantics_payload: dict[str, object],
    evidence_payload: dict[str, object],
) -> dict[str, object]:
    entities = entities_payload.get("entities")
    source_rows = semantics_payload.get("sources")
    if not isinstance(entities, list) or not isinstance(source_rows, list):
        raise ValueError("entities and source semantics must be lists")

    signal_families = [str(row["signal_family"]) for row in source_rows]
    if len(set(signal_families)) != len(signal_families):
        raise ValueError("duplicate signal family in source semantics")

    semantics_by_family = {
        str(row["signal_family"]): row for row in source_rows
    }
    coverage = _coverage_index(evidence_payload)
    evidence = _evidence_index(evidence_payload)

    snapshots: list[dict[str, object]] = []
    state_counts: Counter[str] = Counter()
    evaluable_counts: Counter[str] = Counter()

    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity row must be object")
        entity_id = str(entity["entity_id"])
        anchor_month = str(entity["anchor_month"])
        identity_eligible = bool(entity.get("foreign_signal_identity_eligible"))

        for offset in OFFSETS_MONTHS:
            cutoff = cutoff_exclusive(anchor_month, offset)
            for family in signal_families:
                semantics = semantics_by_family[family]
                key = (entity_id, family)
                family_evidence = evidence.get(key, [])
                available = [
                    row
                    for row in family_evidence
                    if evidence_available_before(row, cutoff)
                ]
                coverage_row = coverage.get(key)
                coverage_status = (
                    str(coverage_row.get("coverage_status"))
                    if coverage_row
                    else "UNVERIFIED"
                )

                if not identity_eligible:
                    state = "UNKNOWN_UNVERIFIED_COVERAGE"
                    reason = "FOREIGN_IDENTITY_NOT_ELIGIBLE"
                elif available:
                    state = "PRESENT"
                    reason = "EXPLICIT_PUBLIC_EVIDENCE_BEFORE_CUTOFF"
                elif coverage_status == "COMPLETE_EXACT_ALIAS_HISTORY":
                    state = "ABSENT_WITH_PROVEN_COVERAGE"
                    reason = "COMPLETE_EXACT_ALIAS_HISTORY_NO_PRE_CUTOFF_EVIDENCE"
                else:
                    state = "UNKNOWN_UNVERIFIED_COVERAGE"
                    reason = str(
                        semantics.get("status")
                        or coverage_status
                        or "UNVERIFIED"
                    )

                if state not in SNAPSHOT_STATES:
                    raise AssertionError(state)
                state_counts[state] += 1
                if state != "UNKNOWN_UNVERIFIED_COVERAGE":
                    evaluable_counts[family] += 1

                snapshots.append(
                    {
                        "entity_id": entity_id,
                        "role": entity["role"],
                        "candidate_outcome_id": entity["candidate_outcome_id"],
                        "anchor_month": anchor_month,
                        "offset_months": offset,
                        "cutoff_exclusive": cutoff.isoformat(),
                        "signal_family": family,
                        "state": state,
                        "reason": reason,
                        "identity_confidence": entity["identity_confidence"],
                        "coverage_status": coverage_status,
                        "evidence_count": len(available),
                        "evidence_ids": [
                            str(row.get("evidence_id") or "") for row in available
                        ],
                        "earliest_public_date": (
                            str(available[0]["publicly_available_date"])
                            if available
                            else None
                        ),
                    }
                )

    snapshots.sort(
        key=lambda row: (
            str(row["entity_id"]),
            -int(row["offset_months"]),
            str(row["signal_family"]),
        )
    )
    return {
        "schema_version": 1,
        "design": "BACKTEST_001_EVENT_TIME_SIGNAL_SNAPSHOTS",
        "offsets_months": list(OFFSETS_MONTHS),
        "cutoff_rule": entities_payload.get("cutoff_rule"),
        "summary": {
            "entity_count": len(entities),
            "signal_family_count": len(signal_families),
            "snapshot_row_count": len(snapshots),
            "state_counts": dict(sorted(state_counts.items())),
            "evaluable_rows_by_signal": dict(sorted(evaluable_counts.items())),
        },
        "snapshots": snapshots,
    }


def load_json(path: str | Path) -> dict[str, object]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
