from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
from pathlib import Path
import unicodedata

from atlanticbridge.event_time_signals import OFFSETS_MONTHS, cutoff_exclusive, load_json
from atlanticbridge.sources.canadabuys import download_awards_csv, iter_awards_csv


SIGNAL_FAMILY = "CANADABUYS_AWARD"
CSV_FIELD_LIMIT = 16 * 1024 * 1024
SOURCES = (
    {
        "source_id": "legacy-2012-2022-08",
        "url": (
            "https://canadabuys.canada.ca/opendata/pub/"
            "2012-2022-awardNoticeHistorical-avisAttributionHistorique.csv"
        ),
        "coverage_start": "2012-02-03",
        "coverage_end": "2022-08-06",
    },
    {
        "source_id": "fy-2022-2023",
        "url": (
            "https://canadabuys.canada.ca/opendata/pub/"
            "2022-2023-awardNotice-avisAttribution.csv"
        ),
        "coverage_start": "2022-04-01",
        "coverage_end": "2023-03-31",
    },
    {
        "source_id": "fy-2023-2024",
        "url": (
            "https://canadabuys.canada.ca/opendata/pub/"
            "2023-2024-awardNotice-avisAttribution.csv"
        ),
        "coverage_start": "2023-04-01",
        "coverage_end": "2024-03-31",
    },
)


def normalize_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized.casefold() if char.isalnum())


def file_sha256(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def ensure_source(cache_dir: Path, spec: dict[str, str]) -> dict[str, object]:
    path = cache_dir / f"{spec['source_id']}.csv"
    if not path.exists():
        download_awards_csv(path, source_url=spec["url"])
    sha256, byte_count = file_sha256(path)
    return {**spec, "path": path, "sha256": sha256, "bytes": byte_count}


def build_alias_index(entities: list[dict[str, object]]) -> dict[str, str]:
    alias_to_entity: dict[str, str] = {}
    for entity in entities:
        entity_id = str(entity["entity_id"])
        aliases = entity.get("exact_aliases")
        if not isinstance(aliases, list) or not aliases:
            raise ValueError(f"entity lacks exact_aliases: {entity_id}")
        for raw in aliases:
            alias = normalize_name(str(raw))
            if not alias:
                continue
            existing = alias_to_entity.get(alias)
            if existing and existing != entity_id:
                raise ValueError(
                    f"exact alias collision {raw!r}: {existing} vs {entity_id}"
                )
            alias_to_entity[alias] = entity_id
    return alias_to_entity


def build_payload(
    *,
    entities_payload: dict[str, object],
    source_files: list[dict[str, object]],
) -> dict[str, object]:
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entities payload requires entities list")
    alias_to_entity = build_alias_index(entities)
    entity_by_id = {str(row["entity_id"]): row for row in entities}

    cutoff_dates = [
        cutoff_exclusive(str(entity["anchor_month"]), offset)
        for entity in entities
        for offset in OFFSETS_MONTHS
    ]
    source_start = date.fromisoformat("2012-02-03")
    source_end = date.fromisoformat("2024-03-31")
    if min(cutoff_dates) <= source_start or max(cutoff_dates) > source_end:
        raise ValueError(
            "CanadaBuys source window does not cover every requested cutoff: "
            f"{min(cutoff_dates)}..{max(cutoff_dates)}"
        )

    csv.field_size_limit(max(csv.field_size_limit(), CSV_FIELD_LIMIT))
    rows_scanned = 0
    matched_rows = 0
    invalid_publication_rows = 0
    undated_matches: dict[str, int] = {}
    source_proof: list[dict[str, object]] = []
    evidence_by_id: dict[str, dict[str, object]] = {}

    for source in source_files:
        source_rows = 0
        source_dates: list[date] = []
        declared_start = date.fromisoformat(str(source["coverage_start"]))
        declared_end = date.fromisoformat(str(source["coverage_end"]))

        for record in iter_awards_csv(
            source["path"],
            source_url=str(source["url"]),
        ):
            rows_scanned += 1
            source_rows += 1
            published: date | None = None
            if record.publication_date:
                try:
                    published = date.fromisoformat(record.publication_date)
                except ValueError:
                    invalid_publication_rows += 1
                else:
                    source_dates.append(published)
                    if not declared_start <= published <= declared_end:
                        raise ValueError(
                            f"publication date outside declared source window "
                            f"{source['source_id']}: {published}"
                        )

            raw = json.loads(record.raw_json)
            names = {
                record.supplier_legal_name,
                str(
                    raw.get("supplierLegalName-nomLegalFournisseur-fra")
                    or ""
                ).strip(),
            }
            matched_entity_ids = {
                alias_to_entity[normalized]
                for name in names
                if (normalized := normalize_name(name)) in alias_to_entity
            }
            if not matched_entity_ids:
                continue

            for entity_id in sorted(matched_entity_ids):
                matched_rows += 1
                if published is None:
                    undated_matches[entity_id] = (
                        undated_matches.get(entity_id, 0) + 1
                    )
                    continue

                material = "\x1f".join(
                    [
                        entity_id,
                        record.reference_number,
                        record.amendment_number,
                        published.isoformat(),
                        normalize_name(record.supplier_legal_name),
                    ]
                )
                evidence_id = hashlib.sha256(
                    material.encode("utf-8")
                ).hexdigest()
                row = evidence_by_id.get(evidence_id)
                if row is None:
                    row = {
                        "evidence_id": evidence_id,
                        "entity_id": entity_id,
                        "signal_family": SIGNAL_FAMILY,
                        "reference_number": record.reference_number,
                        "amendment_number": record.amendment_number,
                        "solicitation_number": record.solicitation_number,
                        "contract_number": record.contract_number,
                        "matched_supplier_name": record.supplier_legal_name,
                        "supplier_country": record.supplier_country,
                        "award_status": record.award_status,
                        "notice_type": record.notice_type,
                        "publicly_available_date": published.isoformat(),
                        "publicly_available_date_precision": "DAY",
                        "publicly_available_date_basis": (
                            "CanadaBuys award notice publicationDate-datePublication"
                        ),
                        "source_files": [],
                    }
                    evidence_by_id[evidence_id] = row
                files = row["source_files"]
                assert isinstance(files, list)
                if source["source_id"] not in files:
                    files.append(source["source_id"])

        source_proof.append(
            {
                "source_id": source["source_id"],
                "url": source["url"],
                "sha256": source["sha256"],
                "bytes": source["bytes"],
                "row_count": source_rows,
                "declared_coverage_start": source["coverage_start"],
                "declared_coverage_end": source["coverage_end"],
                "observed_min_publication_date": (
                    min(source_dates).isoformat() if source_dates else None
                ),
                "observed_max_publication_date": (
                    max(source_dates).isoformat() if source_dates else None
                ),
            }
        )

    coverage = []
    for entity in entities:
        entity_id = str(entity["entity_id"])
        missing_date_count = undated_matches.get(entity_id, 0)
        coverage.append(
            {
                "entity_id": entity_id,
                "signal_family": SIGNAL_FAMILY,
                "coverage_status": (
                    "COMPLETE_EXACT_ALIAS_HISTORY"
                    if missing_date_count == 0
                    else "INCOMPLETE_MATCH_PUBLICATION_DATE"
                ),
                "coverage_scope": (
                    "GOVERNMENT_OF_CANADA_AWARD_NOTICES_IN_CANADABUYS_"
                    "SOURCE_FROM_2012_02_03"
                ),
                "coverage_start_date": source_start.isoformat(),
                "coverage_end_date": source_end.isoformat(),
                "requested_cutoff_min": min(cutoff_dates).isoformat(),
                "requested_cutoff_max": max(cutoff_dates).isoformat(),
                "exact_aliases_normalized": sorted(
                    {
                        normalize_name(str(alias))
                        for alias in entity["exact_aliases"]
                        if normalize_name(str(alias))
                    }
                ),
                "identity_eligible": bool(
                    entity.get("foreign_signal_identity_eligible")
                ),
                "matched_rows_without_publication_date": missing_date_count,
            }
        )

    records = sorted(
        evidence_by_id.values(),
        key=lambda row: (
            str(row["entity_id"]),
            str(row["publicly_available_date"]),
            str(row["evidence_id"]),
        ),
    )
    for row in records:
        row["source_files"] = sorted(row["source_files"])

    return {
        "schema_version": 1,
        "source_family": SIGNAL_FAMILY,
        "source_definition": (
            "Exact reviewed foreign-legal-name appearance as supplier in the "
            "authoritative Government of Canada CanadaBuys award-notice source."
        ),
        "absence_interpretation": (
            "ABSENT means no exact reviewed foreign legal-name supplier mention "
            "in the covered CanadaBuys award-notice source history; it does not "
            "mean no Canadian procurement or no Canadian market activity."
        ),
        "source_metadata": {
            "authority_page": (
                "https://open.canada.ca/data/en/dataset/"
                "a1acb126-9ce8-40a9-b889-5da2b1dd20cb"
            ),
            "supporting_documentation": (
                "https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/"
                "soutien-support-eng.html"
            ),
            "coverage_start_date": source_start.isoformat(),
            "coverage_end_date": source_end.isoformat(),
            "files": source_proof,
        },
        "summary": {
            "entity_count": len(entities),
            "rows_scanned": rows_scanned,
            "matched_rows": matched_rows,
            "evidence_count": len(records),
            "invalid_publication_rows": invalid_publication_rows,
            "entities_with_undated_matches": len(undated_matches),
            "complete_coverage_entities": sum(
                row["coverage_status"] == "COMPLETE_EXACT_ALIAS_HISTORY"
                for row in coverage
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
    parser.add_argument("--cache-dir", default="control-output/canadabuys-cache")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    entities_payload = load_json(args.entities)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    source_files = [ensure_source(cache_dir, spec) for spec in SOURCES]
    payload = build_payload(
        entities_payload=entities_payload,
        source_files=source_files,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["source_metadata"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
