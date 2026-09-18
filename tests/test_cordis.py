from __future__ import annotations

import csv
import tempfile
import unittest
import zipfile
from pathlib import Path

from atlanticbridge.db import connect, cordis_summary, ingest_cordis_snapshot
from atlanticbridge.sources.cordis import (
    ORGANIZATION_HEADER,
    PROJECT_HEADER,
    iter_participations,
    iter_projects,
)


def _write_csv(archive: zipfile.ZipFile, member: str, header: list[str], rows: list[list[str]]) -> None:
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", newline="", delete=False) as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)
        path = Path(handle.name)
    try:
        archive.write(path, arcname=member)
    finally:
        path.unlink(missing_ok=True)


def _project(project_id: str, acronym: str) -> list[str]:
    values = {field: "" for field in PROJECT_HEADER}
    values.update(
        {
            "id": project_id,
            "acronym": acronym,
            "status": "SIGNED",
            "title": f"Project {acronym}",
            "startDate": "2025-01-01",
            "endDate": "2027-12-31",
            "frameworkProgramme": "HORIZON",
            "rcn": f"RCN-{project_id}",
        }
    )
    return [values[field] for field in PROJECT_HEADER]


def _org(
    project_id: str,
    organisation_id: str,
    name: str,
    country: str,
    activity_type: str,
    order: str,
) -> list[str]:
    values = {field: "" for field in ORGANIZATION_HEADER}
    values.update(
        {
            "projectID": project_id,
            "projectAcronym": f"P{project_id}",
            "organisationID": organisation_id,
            "name": name,
            "shortName": name[:10],
            "activityType": activity_type,
            "country": country,
            "rcn": f"{project_id}-{organisation_id}",
            "order": order,
            "role": "participant",
            "active": "true",
        }
    )
    return [values[field] for field in ORGANIZATION_HEADER]


def _archive(path: Path, *, second_project: bool = True) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        project_rows = [_project("1", "P1")]
        organization_rows = [
            _org("1", "CA-1", "Canadian University", "CA", "HES", "1"),
            _org("1", "FR-1", "French Company", "FR", "PRC", "2"),
            _org("1", "DE-1", "German University", "DE", "HES", "3"),
        ]
        if second_project:
            project_rows.append(_project("2", "P2"))
            organization_rows.extend(
                [
                    _org("2", "CA-1", "Canadian University", "CA", "HES", "1"),
                    _org("2", "US-1", "US Partner", "US", "PRC", "2"),
                ]
            )
        _write_csv(archive, "project.csv", PROJECT_HEADER, project_rows)
        _write_csv(archive, "organization.csv", ORGANIZATION_HEADER, organization_rows)


class CordisTests(unittest.TestCase):
    def test_archive_parser_and_relationship_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cordis.zip"
            _archive(path)

            projects = list(iter_projects(path, source_url="https://example.test/cordis.zip"))
            participations = list(
                iter_participations(path, source_url="https://example.test/cordis.zip")
            )

            self.assertEqual(len(projects), 2)
            self.assertEqual(len(participations), 5)
            self.assertEqual(participations[1].organisation_id, "FR-1")
            self.assertEqual(participations[1].activity_type, "PRC")

            conn = connect(":memory:")
            result = ingest_cordis_snapshot(
                conn,
                projects,
                participations,
                observed_at="2026-09-18T20:00:00+00:00",
            )
            self.assertEqual(result, {"projects": 2, "participations": 5})

            summary = cordis_summary(conn)
            self.assertEqual(summary["projects"], 2)
            self.assertEqual(summary["participations"], 5)
            self.assertEqual(summary["canada_participation_rows"], 2)
            self.assertEqual(summary["canada_unique_organizations"], 1)
            self.assertEqual(summary["canada_unique_projects"], 2)
            self.assertEqual(summary["eu_participation_rows_on_canada_projects"], 2)
            self.assertEqual(summary["eu_unique_organizations_on_canada_projects"], 2)
            self.assertEqual(
                summary["eu_prc_activity_code_unique_organizations_on_canada_projects"],
                1,
            )
            self.assertEqual(summary["canada_eu_shared_projects"], 1)

    def test_snapshot_replacement_removes_stale_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            full = Path(temp_dir) / "full.zip"
            reduced = Path(temp_dir) / "reduced.zip"
            _archive(full, second_project=True)
            _archive(reduced, second_project=False)

            conn = connect(":memory:")
            ingest_cordis_snapshot(
                conn,
                iter_projects(full),
                iter_participations(full),
                observed_at="2026-09-18T20:00:00+00:00",
            )
            ingest_cordis_snapshot(
                conn,
                iter_projects(reduced),
                iter_participations(reduced),
                observed_at="2026-10-18T20:00:00+00:00",
            )

            summary = cordis_summary(conn)
            self.assertEqual(summary["projects"], 1)
            self.assertEqual(summary["participations"], 3)
            self.assertEqual(summary["canada_unique_projects"], 1)

    def test_schema_change_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.zip"
            with zipfile.ZipFile(path, "w") as archive:
                _write_csv(archive, "project.csv", ["unexpected"], [["1"]])
                _write_csv(archive, "organization.csv", ORGANIZATION_HEADER, [])

            with self.assertRaisesRegex(ValueError, "schema changed"):
                list(iter_projects(path))


if __name__ == "__main__":
    unittest.main()
