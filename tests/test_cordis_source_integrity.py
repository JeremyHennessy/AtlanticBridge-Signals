"""The legacy ingest must reject source corruption instead of shifting columns."""
import csv
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from atlanticbridge.db import connect, cordis_summary, ingest_cordis_snapshot
from atlanticbridge.sources.cordis import ORGANIZATION_HEADER, PROJECT_HEADER, iter_projects, iter_participations
from test_cordis import _archive, _project, _org


def encoded(header, rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out, delimiter=";")
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode()


class CordisSourceIntegrityTests(unittest.TestCase):
    def write_archive(self, path, projects=None, organisations=None):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("project.csv", projects or encoded(PROJECT_HEADER, [_project("1", "P1")]))
            archive.writestr("organization.csv", organisations or encoded(ORGANIZATION_HEADER, [_org("1", "1", "Company", "CA", "PRC", "1")]))

    def test_missing_and_extra_columns_fail_closed_for_both_members(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            for member, header, row, read in [
                ("projects", PROJECT_HEADER, _project("1", "P1"), iter_projects),
                ("organisations", ORGANIZATION_HEADER, _org("1", "1", "Company", "CA", "PRC", "1"), iter_participations),
            ]:
                for broken in [row[:-1], row + ["shifted"]]:
                    with self.subTest(member=member, width=len(broken)):
                        self.write_archive(path, **{member: encoded(header, [broken])})
                        with self.assertRaisesRegex(ValueError, "malformed CSV row width"):
                            list(read(path))

    def test_invalid_utf8_and_quote_boundary_are_not_silently_repaired(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.zip"
            head = encoded(PROJECT_HEADER, [])
            for broken, exception in [(head + b'1;\xff\n', UnicodeDecodeError), (head + b'1;"bad"quote;\n', csv.Error)]:
                self.write_archive(path, projects=broken)
                with self.assertRaises(exception):
                    list(iter_projects(path))

    def test_corrupt_replacement_rolls_back_preserving_existing_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            clean, bad = Path(temp) / "clean.zip", Path(temp) / "bad.zip"
            _archive(clean)
            self.write_archive(bad, projects=encoded(PROJECT_HEADER, [_project("3", "P3"), _project("4", "P4") + ["extra"]]))
            conn = connect(":memory:")
            ingest_cordis_snapshot(conn, iter_projects(clean), iter_participations(clean), observed_at="2026-11-01T00:00:00Z")
            before = cordis_summary(conn)
            with self.assertRaises(ValueError):
                ingest_cordis_snapshot(conn, iter_projects(bad), iter_participations(bad), observed_at="2026-11-09T00:00:00Z")
            self.assertEqual(cordis_summary(conn), before)
            conn.close()
