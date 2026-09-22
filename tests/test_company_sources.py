"""Regression fixtures are synthetic, never historical validation observations."""
import copy
import tempfile
import unittest
from pathlib import Path

from atlanticbridge.company_sources import (Ledger, discover_ats, parse_article,
    parse_ashby, parse_feed, parse_greenhouse, parse_index, record, url)

SOURCE = {"id": "fixture-jobs", "kind": "careers", "company": "Fixture", "url": "https://example.org/careers"}
NOW = "2026-09-22T20:00:00Z"
LATER = "2026-09-23T20:00:00Z"
HASH = "a" * 64


def gh(**kwargs):
    row = {"id": 1, "internal_job_id": 10, "title": "Engineer", "location": {"name": "Toronto, Canada"},
           "content": "Build tools", "absolute_url": "https://example.org/jobs/1", "updated_at": NOW}
    row.update(kwargs)
    return {"jobs": [row], "meta": {"total": 1}}


def ash(**kwargs):
    row = {"title": "Engineer", "location": "Paris", "isListed": True, "isRemote": False,
           "publishedAt": "2026-09-20T10:00:00Z", "jobUrl": "https://jobs.ashbyhq.com/fixture/1",
           "descriptionPlain": "Our company works in Canada and around the world."}
    row.update(kwargs)
    return {"apiVersion": "1", "jobs": [row]}


class ParserTests(unittest.TestCase):
    def test_greenhouse_update_is_not_publication(self):
        row = parse_greenhouse(gh(), SOURCE)[0]
        self.assertIsNone(row["source_publication_date"])
        self.assertEqual(row["source_updated_at"], NOW)
        self.assertFalse(row["public_alert_allowed"])

    def test_greenhouse_partial_fails(self):
        payload = gh()
        payload["meta"]["total"] = 2
        with self.assertRaises(ValueError):
            parse_greenhouse(payload, SOURCE)

    def test_greenhouse_duplicate_fails(self):
        payload = gh()
        payload["jobs"] *= 2
        payload["meta"]["total"] = 2
        with self.assertRaises(ValueError):
            parse_greenhouse(payload, SOURCE)

    def test_prospect_is_not_open_job(self):
        self.assertEqual(parse_greenhouse(gh(internal_job_id=None), SOURCE), [])

    def test_greenhouse_missing_location_fails(self):
        with self.assertRaises(ValueError):
            parse_greenhouse(gh(location={}), SOURCE)

    def test_ashby_last_published_not_first(self):
        self.assertEqual(parse_ashby(ash(), SOURCE)[0]["publication_clock"], "LAST_PUBLISHED_NOT_ORIGINAL_PUBLICATION")

    def test_ashby_unlisted_not_surfaced(self):
        self.assertEqual(parse_ashby(ash(isListed=False), SOURCE), [])

    def test_ashby_unknown_visibility_fails(self):
        with self.assertRaises(ValueError):
            parse_ashby(ash(isListed="true"), SOURCE)

    def test_ashby_unknown_version_fails(self):
        payload = ash()
        payload["apiVersion"] = "2"
        with self.assertRaises(ValueError):
            parse_ashby(payload, SOURCE)

    def test_global_boilerplate_not_canada_job(self):
        self.assertEqual(parse_ashby(ash(), SOURCE)[0]["canada_relevance"], "NOT_ESTABLISHED")

    def test_secondary_canada_location_retained(self):
        row = parse_ashby(ash(secondaryLocations=[{"location": "London", "address": {"addressCountry": "CAN"}}]), SOURCE)[0]
        self.assertEqual(row["canada_relevance"], "CANDIDATE_REQUIRES_REVIEW")

    def test_remote_not_new_office(self):
        row = parse_ashby(ash(location="Remote, Canada", isRemote=True), SOURCE)[0]
        self.assertTrue(row["remote"])
        self.assertFalse(row["public_alert_allowed"])
        self.assertIn("not proof", row["interpretation"])

    def test_vancouver_washington_not_canada(self):
        row = parse_greenhouse(gh(location={"name": "Vancouver, WA, United States"}), SOURCE)[0]
        self.assertEqual(row["canada_relevance"], "NOT_ESTABLISHED")

    def test_military_hold(self):
        row = parse_greenhouse(gh(title="Canadian military account manager"), SOURCE)[0]
        self.assertEqual(row["scope_exclusion"], "MILITARY_REVIEW_HOLD")

    def test_source_namespace_prevents_false_join(self):
        other = dict(SOURCE, id="another-company")
        self.assertNotEqual(parse_greenhouse(gh(), SOURCE)[0]["id"], parse_greenhouse(gh(), other)[0]["id"])

    def test_official_link_discovery_not_brand_guess(self):
        body = b'<a href="https://jobs.ashbyhq.com/real-board">Jobs</a><iframe src="https://boards.greenhouse.io/embed/job_board?for=other"></iframe>'
        self.assertEqual(discover_ats(body, SOURCE["url"]), [("ashby", "real-board"), ("greenhouse", "other")])
        self.assertEqual(discover_ats(b"We might use Greenhouse for Fixture", SOURCE["url"]), [])

    def test_tracking_url_dedup_keeps_functional_query(self):
        self.assertEqual(url("https://example.org/job?jobId=3&utm_source=x#x"), "https://example.org/job?jobId=3")

    def test_unsafe_url_rejected(self):
        for bad in ["http://example.org", "javascript:alert(1)", "https://u:p@example.org", "https://example.org:8888"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                url(bad)

    def test_index_window_not_absence(self):
        source = dict(SOURCE, kind="index", url="https://example.org/news/", article_path_prefix="/news/")
        body = b'<a href="/news/launch?utm_source=x">Launch</a><a href="/news/new-office">Company opens Canada office</a><a href="https://evil.org/news/launch">Wrong origin article</a>'
        rows = parse_index(body, source)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["source_publication_date"])
        with self.assertRaises(ValueError):
            parse_index(b"login required", source)

    def test_article_date_requires_literal_anchor(self):
        source = dict(SOURCE, kind="article", required_text=["opens in Canada"], reviewed_publication_date="2026-06-25", publication_date_text="June 25, 2026")
        body = b"<article><h1>Fixture opens in Canada</h1><p>June 25, 2026</p></article>"
        self.assertEqual(parse_article(body, source)[0]["source_publication_date"], "2026-06-25")
        with self.assertRaises(ValueError):
            parse_article(body.replace(b"June 25", b"June 26"), source)

    def test_atom_updated_not_publication(self):
        body = b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Canada office</title><link href="https://example.org/a"/><updated>2026-06-25T00:00:00Z</updated></entry></feed>'
        self.assertIsNone(parse_feed(body, dict(SOURCE, kind="feed"))[0]["source_publication_date"])

    def test_rss_published_date_and_duplicate(self):
        item = b'<item><title>Canada office</title><link>https://example.org/a</link><pubDate>Thu, 25 Jun 2026 12:00:00 GMT</pubDate></item>'
        source = dict(SOURCE, kind="feed")
        rows = parse_feed(b'<rss><channel>' + item + b'</channel></rss>', source)
        self.assertEqual(rows[0]["publication_precision"], "TIMESTAMP")
        with self.assertRaises(ValueError):
            parse_feed(b'<rss><channel>' + item * 2 + b'</channel></rss>', source)

    def test_xml_entities_fail_closed(self):
        with self.assertRaises(ValueError):
            parse_feed(b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss/>', SOURCE)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "state.sqlite")
        self.ledger = Ledger(self.path)
        self.rows = parse_greenhouse(gh(), SOURCE)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def baseline(self):
        self.assertEqual(self.ledger.apply(SOURCE, self.rows, NOW, HASH), [])

    def test_baseline_suppresses_alerts(self):
        self.baseline()

    def test_idempotent_replay(self):
        self.baseline()
        self.assertEqual(self.ledger.apply(SOURCE, self.rows, LATER, HASH), [])

    def test_new_observation_is_not_new_publication(self):
        self.baseline()
        rows = self.rows + parse_greenhouse(gh(id=2, absolute_url="https://example.org/jobs/2"), SOURCE)
        events = self.ledger.apply(SOURCE, rows, LATER, HASH)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["kind"], "NEWLY_OBSERVED_RECORD")
        self.assertFalse(events[0]["public_alert_allowed"])

    def test_update_timestamp_alone_no_alert(self):
        self.baseline()
        rows = parse_greenhouse(gh(updated_at=LATER), SOURCE)
        self.assertEqual(self.ledger.apply(SOURCE, rows, LATER, HASH), [])

    def test_material_revision_is_change_not_new(self):
        self.baseline()
        rows = parse_greenhouse(gh(title="Senior Engineer"), SOURCE)
        self.assertEqual(self.ledger.apply(SOURCE, rows, LATER, HASH)[0]["kind"], "RECORD_CHANGED")

    def test_outage_does_not_erase_baseline(self):
        self.baseline()
        with self.assertRaises(ValueError):
            self.ledger.apply(SOURCE, [], LATER, HASH, complete=False)
        self.assertEqual(self.ledger.apply(SOURCE, self.rows, LATER, HASH), [])

    def test_empty_window_reappearance_not_new(self):
        self.baseline()
        self.assertEqual(self.ledger.apply(SOURCE, [], LATER, HASH), [])
        self.assertEqual(self.ledger.apply(SOURCE, self.rows, "2026-09-24T20:00:00Z", HASH), [])

    def test_restart_preserves_first_seen(self):
        self.baseline()
        self.ledger.close()
        self.ledger = Ledger(self.path)
        self.assertEqual(self.ledger.apply(SOURCE, self.rows, LATER, HASH), [])
        self.assertEqual(self.ledger.db.execute("SELECT first_seen FROM company_observations").fetchone()[0], NOW)

    def test_contract_change_requires_review(self):
        self.baseline()
        with self.assertRaises(ValueError):
            self.ledger.apply(dict(SOURCE, company="Someone else"), self.rows, LATER, HASH)

    def test_future_date_rolls_back_whole_source(self):
        self.baseline()
        future = record(SOURCE, "future", "Future job", "https://example.org/future", published="2027-01-01")
        with self.assertRaises(ValueError):
            self.ledger.apply(SOURCE, self.rows + [future], LATER, HASH)
        self.assertEqual(self.ledger.db.execute("SELECT count(*) FROM company_observations").fetchone()[0], 1)

    def test_clock_regression_rejected(self):
        self.baseline()
        with self.assertRaises(ValueError):
            self.ledger.apply(SOURCE, self.rows, "2026-09-21T00:00:00Z", HASH)

    def test_missing_provenance_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.apply(SOURCE, self.rows, NOW, "")

    def test_mixed_source_rejected(self):
        self.rows[0]["source_id"] = "wrong"
        with self.assertRaises(ValueError):
            self.ledger.apply(SOURCE, self.rows, NOW, HASH)


if __name__ == "__main__":
    unittest.main()
