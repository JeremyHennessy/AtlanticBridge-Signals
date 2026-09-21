from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import unittest

from atlanticbridge.sources.cipo_journal import (
    JournalIssue,
    inventory_sha256,
    locate_known_application,
    normalize_application_number,
    normalize_name,
    parse_archive,
)


ROOT = Path(__file__).resolve().parents[1]
IDENTITIES = ROOT / "reviews/backtests/2026-09-21-cipo-journal-identities.json"


class CIPOJournalTests(unittest.TestCase):
    def test_archive_parser_uses_publication_date_and_english_pdf(self):
        html = """
        <table>
          <tr>
            <td>2018-12-12</td>
            <td><a href="/opic-cipo/tmj/eng/12Dec2018_en.pdf?edition=12-12&amp;year=2018">PDF 6.5 MB</a></td>
            <td><a href="/opic-cipo/tmj/fra/12Dec2018_fr.pdf?edition=12-12&amp;year=2018">PDF 6.7 MB</a></td>
          </tr>
        </table>
        """
        issues = parse_archive(
            html,
            year=2018,
            source_url="https://cipo.ic.gc.ca/opic-cipo/tmj/eng/archive.html?year=2018",
        )
        self.assertEqual(len(issues), 1)
        issue = issues[0]
        self.assertEqual(issue.publication_date, date(2018, 12, 12))
        self.assertIn("/eng/12Dec2018_en.pdf", issue.pdf_url)
        self.assertIn("edition=12-12", issue.html_url)
        self.assertIn("year=2018", issue.html_url)

    def test_archive_parser_supports_legacy_non_table_layout(self):
        html = """
        <div>Publication Date</div>
        <div>Full Version</div>
        <div>2000-01-05</div>
        <div><a href="/opic-cipo/tmj/eng/05Jan2000_en.pdf">PDF 1.47 MB</a></div>
        <div>2000-01-12</div>
        <div><a href="/opic-cipo/tmj/eng/12Jan2000_en.pdf">PDF 1.93 MB</a></div>
        """
        issues = parse_archive(
            html,
            year=2000,
            source_url="https://cipo.ic.gc.ca/opic-cipo/tmj/eng/archive.html?year=2000",
        )
        self.assertEqual(
            [issue.publication_date for issue in issues],
            [date(2000, 1, 5), date(2000, 1, 12)],
        )
        self.assertTrue(issues[0].pdf_url.endswith("05Jan2000_en.pdf"))

    def test_application_locator_stays_inside_advertised_section(self):
        text = """
        Table of contents
        Advertised applications
        Applications to extend the statement of goods or services
        Registered trademarks

        Advertised applications

        Application Number 1,799,092
        Filing Date 2016-09-07
        APPLICANT AND REPRESENTATIVE FOR SERVICE
        Applicant
        SIOO WOODPROTECTION AB, Von Utfallsgatan 20, Göteborg, SWEDEN
        Representative for Service
        Example Agent
        TRADEMARK
        SIOO:X

        Application Number 1,800,000
        Applicant
        Another Company

        Registered trademarks
        Application Number 1,799,092
        Applicant
        Wrong Later Owner Inc.
        """
        found = locate_known_application(
            text,
            application_number="1799092",
            expected_applicant="SIOO WOODPROTECTION AB",
        )
        self.assertIsNotNone(found)
        assert found is not None
        self.assertTrue(found["exact_expected_name_in_application_window"])
        self.assertIn("SIOO WOODPROTECTION AB", found["extracted_applicant"])

        wrong = locate_known_application(
            text,
            application_number="1799092",
            expected_applicant="Wrong Later Owner Inc.",
        )
        self.assertIsNone(wrong)

    def test_application_number_and_name_normalization(self):
        self.assertEqual(normalize_application_number("1,336,566"), "1336566")
        self.assertEqual(
            normalize_name("MOLINO ANDRIANI S.r.l."),
            normalize_name("Molino Andriani Srl"),
        )

    def test_inventory_hash_is_order_sensitive_and_deterministic(self):
        issues = [
            JournalIssue(
                publication_date=date(2008, 2, 13),
                pdf_url="https://example/13.pdf",
                html_url="https://example/13.html",
            ),
            JournalIssue(
                publication_date=date(2008, 2, 20),
                pdf_url="https://example/20.pdf",
                html_url="https://example/20.html",
            ),
        ]
        first = inventory_sha256(issues)
        second = inventory_sha256(list(issues))
        reversed_hash = inventory_sha256(list(reversed(issues)))
        self.assertEqual(first, second)
        self.assertNotEqual(first, reversed_hash)

    def test_andriani_historical_alias_requires_source_backed_relation(self):
        payload = json.loads(IDENTITIES.read_text(encoding="utf-8"))
        case = next(
            row for row in payload["cases"]
            if row["case_id"] == "ANDRIANI_1702825"
        )
        self.assertEqual(
            case["expected_applicant"],
            "MOLINO ANDRIANI S.r.l.",
        )
        self.assertEqual(
            case["relation"],
            "SOURCE_BACKED_LEGAL_NAME_PREDECESSOR_SAME_COMPANY",
        )
        history = case["legal_name_history"]
        self.assertEqual(history["historical_name"], "Molino Andriani S.r.l.")
        self.assertEqual(history["current_name"], "Andriani S.p.A.")
        self.assertEqual(history["transformation_year"], 2016)
        self.assertTrue(history["source_url"].startswith("https://www.andrianispa.com/"))


if __name__ == "__main__":
    unittest.main()
