from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import unicodedata

from atlanticbridge.sources.canadabuys import (
    download_awards_csv,
    iter_awards_csv,
)


LEGACY_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "2012-2022-awardNoticeHistorical-avisAttributionHistorique.csv"
)
CURRENT_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "awardNoticeComplete-avisAttributionComplet.csv"
)
BRIDGE_2022_2023_URL = (
    "https://canadabuys.canada.ca/opendata/pub/"
    "2022-2023-awardNotice-avisAttribution.csv"
)
SIGNAL_FAMILY = "CANADABUYS_AWARD"
CSV_FIELD_SIZE_LIMIT = 16 * 1024 * 1024
COVERAGE_START_DATE = date(2012, 2, 3)
MAX_BACKTEST_CUTOFF_EXCLUSIVE = date(2023, 6, 1)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).date()
        except ValueError:
            pass
    raise ValueError(f"unsupported CanadaBuys date format: {value!r}")


def public_availability_date(record) -> date:
    publication = parse_date(record.publication_date)
    amendment = parse_date(record.amendment_date)
    if publication is None and amendment is None:
        raise ValueError(
            f"award row lacks publication/amendment date: {record.reference_number}"
        )
    candidates = [value for value in (publication, amendment) if value is not None]
    return max(candidates)


def build_alias_index(entities_payload: dict[str, object]):
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entities payload requires entities list")
    alias_to_entities: dict[str, set[str]] = {}
    normalized_aliases: dict[str, list[str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity rows must be objects")
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks aliases: {entity_id}")
        entity_aliases: list[str] = []
        for alias in aliases:
            normalized = normalize_name(str(alias))
            if not normalized:
                continue
            if normalized not in entity_aliases:
                entity_aliases.append(normalized)
            alias_to_entities.setdefault(normalized, set()).add(entity_id)
        normalized_aliases[entity_id] = sorted(entity_aliases)
    return alias_to_entities, normalized_aliases


def scan_file(
    path: Path,
    *,
    source_url: str,
    source_label: str,
    alias_to_entities: dict[str, set[str]],
):
    row_count = 0
    min_publication: date | None = None
    max_publication: date | None = None
    exact_matches: list[dict[str, object]] = []
    semantic_window_keys: set[tuple[str, str]] = set()
    semantic_window_rows = 0
    key_hash = hashlib.sha256()

    for record in iter_awards_csv(path, source_url=source_url):
        row_count += 1
        publication = parse_date(record.publication_date)
        if publication is not None:
            min_publication = (
                publication
                if min_publication is None
                else min(min_publication, publication)
            )
            max_publication = (
                publication
                if max_publication is None
                else max(max_publication, publication)
            )

        key_hash.update(
            (
                record.reference_number
                + "\x1f"
                + record.amendment_number
                + "\n"
            ).encode("utf-8")
        )

        available = public_availability_date(record)
        if COVERAGE_START_DATE <= available < MAX_BACKTEST_CUTOFF_EXCLUSIVE:
            semantic_window_rows += 1
            semantic_window_keys.add(
                (record.reference_number, record.amendment_number)
            )

        normalized_supplier = normalize_name(record.supplier_legal_name)
        entity_ids = alias_to_entities.get(normalized_supplier)
        if not entity_ids:
            continue

        for entity_id in sorted(entity_ids):
            exact_matches.append(
                {
                    "entity_id": entity_id,
                    "signal_family": SIGNAL_FAMILY,
                    "supplier_legal_name": record.supplier_legal_name,
                    "supplier_country": record.supplier_country,
                    "reference_number": record.reference_number,
                    "amendment_number": record.amendment_number,
                    "publication_date": record.publication_date,
                    "amendment_date": record.amendment_date,
                    "contract_award_date": record.contract_award_date,
                    "publicly_available_date": available.isoformat(),
                    "publicly_available_date_precision": "DAY",
                    "publicly_available_date_basis": (
                        "CanadaBuys amendment date when present, otherwise award "
                        "notice publication date. This avoids backdating amended "
                        "row content to the original publication."
                    ),
                    "source_dataset": source_label,
                    "source_url": source_url,
                }
            )

    return {
        "source_label": source_label,
        "source_url": source_url,
        "row_count": row_count,
        "semantic_window_row_count": semantic_window_rows,
        "_semantic_window_keys": semantic_window_keys,
        "min_publication_date": (
            min_publication.isoformat() if min_publication else None
        ),
        "max_publication_date": (
            max_publication.isoformat() if max_publication else None
        ),
        "record_key_sequence_sha256": key_hash.hexdigest(),
        "exact_match_count": len(exact_matches),
        "matches": exact_matches,
    }


def collect(
    *,
    entities_payload: dict[str, object],
    cache_dir: Path,
) -> dict[str, object]:
    alias_to_entities, normalized_aliases = build_alias_index(entities_payload)

    previous_limit = csv.field_size_limit()
    if previous_limit < CSV_FIELD_SIZE_LIMIT:
        csv.field_size_limit(CSV_FIELD_SIZE_LIMIT)

    source_specs = [
        ("LEGACY_2012_TO_2022_08", LEGACY_URL, "legacy.csv"),
        ("FISCAL_2022_2023_BRIDGE", BRIDGE_2022_2023_URL, "2022-2023.csv"),
        ("COMPLETE_2022_08_ONWARD", CURRENT_URL, "complete.csv"),
    ]

    downloads: list[dict[str, object]] = []
    scans: list[dict[str, object]] = []
    semantic_window_keys: set[tuple[str, str]] = set()
    try:
        for label, url, filename in source_specs:
            path = cache_dir / filename
            download_meta = download_awards_csv(path, source_url=url)
            downloads.append(
                {
                    "source_label": label,
                    "url": download_meta.source_url,
                    "sha256": download_meta.sha256,
                    "bytes": download_meta.byte_count,
                }
            )
            scan = scan_file(
                path,
                source_url=url,
                source_label=label,
                alias_to_entities=alias_to_entities,
            )
            scan_keys = scan.pop("_semantic_window_keys")
            assert isinstance(scan_keys, set)
            semantic_window_keys.update(scan_keys)
            scans.append(scan)
    finally:
        if previous_limit < CSV_FIELD_SIZE_LIMIT:
            csv.field_size_limit(previous_limit)

    by_evidence_key: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for scan in scans:
        for match in scan.pop("matches"):
            key = (
                str(match["entity_id"]),
                str(match["reference_number"]),
                str(match["amendment_number"]),
                str(match["publicly_available_date"]),
            )
            existing = by_evidence_key.get(key)
            if existing is None:
                match["source_datasets"] = [match.pop("source_dataset")]
                by_evidence_key[key] = match
            else:
                dataset = str(match["source_dataset"])
                datasets = existing["source_datasets"]
                assert isinstance(datasets, list)
                if dataset not in datasets:
                    datasets.append(dataset)
                    datasets.sort()

    records = sorted(
        by_evidence_key.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["reference_number"]),
            str(row["amendment_number"]),
        ),
    )

    semantic_material = "\n".join(
        f"{reference}\x1f{amendment}"
        for reference, amendment in sorted(semantic_window_keys)
    )
    semantic_window = {
        "coverage_start_date": COVERAGE_START_DATE.isoformat(),
        "max_backtest_cutoff_exclusive":
            MAX_BACKTEST_CUTOFF_EXCLUSIVE.isoformat(),
        "unique_reference_amendment_keys": len(semantic_window_keys),
        "canonical_key_sha256": hashlib.sha256(
            semantic_material.encode("utf-8")
        ).hexdigest(),
        "exact_reviewed_alias_matches": sum(
            1
            for row in records
            if COVERAGE_START_DATE
            <= date.fromisoformat(str(row["publicly_available_date"]))
            < MAX_BACKTEST_CUTOFF_EXCLUSIVE
        ),
    }

    coverage_end_dates = [
        date.fromisoformat(str(scan["max_publication_date"]))
        for scan in scans
        if scan.get("max_publication_date")
    ]
    if not coverage_end_dates:
        raise ValueError("CanadaBuys source scans produced no publication dates")
    coverage_end_exclusive = (
        max(coverage_end_dates) + timedelta(days=1)
    ).isoformat()

    coverage = []
    for entity in entities_payload["entities"]:
        entity_id = str(entity["entity_id"])
        coverage.append(
            {
                "entity_id": entity_id,
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_OFFICIAL_FEDERAL_AWARD_NOTICE_EXACT_ALIAS_"
                    "HISTORY_2012_ONWARD"
                ),
                "absence_coverage_proven": True,
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "aliases_normalized": normalized_aliases[entity_id],
                "coverage_start_date": "2012-02-03",
                "coverage_end_exclusive": coverage_end_exclusive,
                "coverage_sources": [
                    "LEGACY_2012_TO_2022_08",
                    "FISCAL_2022_2023_BRIDGE",
                    "COMPLETE_2022_08_ONWARD",
                ],
            }
        )

    return {
        "schema_version": 1,
        "source_family": SIGNAL_FAMILY,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "source_definition": (
            "Exact reviewed foreign legal-entity alias appears as supplierLegalName "
            "in the authoritative federal CanadaBuys award-notice corpus on or after "
            "2012-02-03 and before the event-time cutoff."
        ),
        "coverage_definition": (
            "Union of the official legacy 2012-to-2022-08 file, overlapping "
            "2022-2023 fiscal bridge file, and all-awards 2022-08-08-onward file. "
            "Non-hits are absence only for the narrow exact-alias signal, not proof "
            "that the corporate group had no federal procurement relationship."
        ),
        "downloads": downloads,
        "source_scans": scans,
        "semantic_window": semantic_window,
        "summary": {
            "entity_count": len(entities_payload["entities"]),
            "source_file_count": len(scans),
            "rows_scanned": sum(int(scan["row_count"]) for scan in scans),
            "deduplicated_exact_match_records": len(records),
            "entities_with_exact_match": len(
                {str(row["entity_id"]) for row in records}
            ),
        },
        "coverage": coverage,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--entities",
        default="reviews/backtests/2026-09-21-backtest-entities.json",
    )
    parser.add_argument(
        "--cache-dir",
        default="control-output/canadabuys-cache",
    )
    parser.add_argument(
        "--output",
        default="control-output/canadabuys-signal-evidence.json",
    )
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    payload = collect(
        entities_payload=entities,
        cache_dir=Path(args.cache_dir),
    )
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["source_scans"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
