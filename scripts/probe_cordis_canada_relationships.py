from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

from atlanticbridge.sources.cordis import (
    download_horizon_archive,
    iter_participations,
    iter_projects,
)


def normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in decomposed.casefold() if char.isalnum())


def build_alias_index(entities_payload: dict[str, object]):
    entities = entities_payload.get("entities")
    if not isinstance(entities, list):
        raise ValueError("entities payload requires entities list")
    aliases: dict[str, set[str]] = {}
    for entity in entities:
        if not isinstance(entity, dict):
            raise ValueError("entity row must be object")
        entity_id = str(entity["entity_id"])
        for alias in entity.get("exact_aliases") or []:
            normalized = normalize_name(str(alias))
            if normalized:
                aliases.setdefault(normalized, set()).add(entity_id)
    return aliases


def collect(
    *,
    entities_payload: dict[str, object],
    archive_path: Path,
    source_metadata: dict[str, object],
) -> dict[str, object]:
    alias_index = build_alias_index(entities_payload)

    matched_participations: list[dict[str, object]] = []
    canada_projects: set[str] = set()
    participation_rows = 0

    for row in iter_participations(archive_path):
        participation_rows += 1
        if row.country.upper() == "CA":
            canada_projects.add(row.project_id)

        entity_ids = alias_index.get(normalize_name(row.name))
        if not entity_ids:
            continue
        for entity_id in sorted(entity_ids):
            matched_participations.append(
                {
                    "entity_id": entity_id,
                    "project_id": row.project_id,
                    "project_acronym": row.project_acronym,
                    "organisation_id": row.organisation_id,
                    "vat_number": row.vat_number,
                    "organisation_name": row.name,
                    "country": row.country,
                    "role": row.role,
                    "content_update_date": row.content_update_date,
                }
            )

    project_ids = {
        str(row["project_id"])
        for row in matched_participations
        if str(row["project_id"]) in canada_projects
    }

    projects: dict[str, dict[str, object]] = {}
    project_rows = 0
    for project in iter_projects(archive_path):
        project_rows += 1
        if project.project_id not in project_ids:
            continue
        projects[project.project_id] = {
            "project_id": project.project_id,
            "acronym": project.acronym,
            "title": project.title,
            "status": project.status,
            "start_date": project.start_date,
            "end_date": project.end_date,
            "ec_signature_date": project.ec_signature_date,
            "content_update_date": project.content_update_date,
            "framework_programme": project.framework_programme,
            "grant_doi": project.grant_doi,
        }

    records = []
    for match in matched_participations:
        project_id = str(match["project_id"])
        if project_id not in canada_projects:
            continue
        project = projects.get(project_id)
        if project is None:
            raise ValueError(f"matched project missing project metadata: {project_id}")
        records.append({**match, **project})

    records.sort(
        key=lambda row: (
            str(row["entity_id"]),
            str(row["project_id"]),
        )
    )

    key_material = "\n".join(
        f"{row['entity_id']}\x1f{row['project_id']}"
        for row in records
    )

    entity_counts = {
        str(entity["entity_id"]): 0
        for entity in entities_payload["entities"]
    }
    for row in records:
        entity_counts[str(row["entity_id"])] += 1

    return {
        "schema_version": 1,
        "purpose": (
            "Presence probe only: exact reviewed foreign legal-entity aliases "
            "that participate in a CORDIS Horizon project which also contains "
            "at least one Canadian organisation."
        ),
        "source_metadata": source_metadata,
        "summary": {
            "entity_count": len(entity_counts),
            "participation_rows_scanned": participation_rows,
            "project_rows_scanned": project_rows,
            "canada_project_count": len(canada_projects),
            "matched_foreign_participation_rows": len(matched_participations),
            "canada_relationship_records": len(records),
            "entities_with_canada_relationship": sum(
                count > 0 for count in entity_counts.values()
            ),
            "relationship_key_sha256": hashlib.sha256(
                key_material.encode("utf-8")
            ).hexdigest(),
        },
        "entity_relationship_counts": entity_counts,
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
        default="control-output/cordis-cache",
    )
    parser.add_argument(
        "--output",
        default="control-output/cordis-positive-probe.json",
    )
    args = parser.parse_args()

    entities = json.loads(Path(args.entities).read_text(encoding="utf-8"))
    cache_dir = Path(args.cache_dir)
    archive_path = cache_dir / "cordis-HORIZONprojects-csv.zip"
    download = download_horizon_archive(archive_path)

    payload = collect(
        entities_payload=entities,
        archive_path=archive_path,
        source_metadata={
            "url": download.source_url,
            "sha256": download.sha256,
            "bytes": download.byte_count,
        },
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload["summary"], indent=2, sort_keys=True))
    print(json.dumps(payload["entity_relationship_counts"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
