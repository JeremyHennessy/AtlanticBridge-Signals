"""Isolated network-contract tests: no requests are made by these fixtures."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from scripts.probe_company_sources import Capture, unavailable_robots_allowed

PUBLIC = "https://api.ashbyhq.com/posting-api/job-board/fixture"


class NetworkContractTests(unittest.TestCase):
    def test_documented_api_robots_unavailable_is_not_protected_job_data(self):
        self.assertTrue(unavailable_robots_allowed(401, PUBLIC))
        self.assertTrue(unavailable_robots_allowed(403, PUBLIC))
        self.assertFalse(unavailable_robots_allowed(401, "https://api.ashbyhq.com/private"))
        self.assertFalse(unavailable_robots_allowed(401, "https://example.org/jobs"))

    def test_rate_limit_and_server_errors_do_not_allow_fetch(self):
        for status in (429, 500, 503):
            self.assertFalse(unavailable_robots_allowed(status, PUBLIC))

    def test_public_content_after_unavailable_robots(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = Capture(Path(temp), {"api.ashbyhq.com"})
            exc = HTTPError("https://api.ashbyhq.com/robots.txt", 401, "Unauthorized", {}, None)
            with patch.object(capture, "raw", side_effect=[exc, (b'{"jobs":[]}', "a" * 64)]) as fetch:
                self.assertEqual(capture.get(PUBLIC)[0], b'{"jobs":[]}')
                self.assertEqual(fetch.call_count, 2)

    def test_content_authorization_failure_still_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = Capture(Path(temp), {"api.ashbyhq.com"})
            robots = HTTPError("https://api.ashbyhq.com/robots.txt", 401, "Unauthorized", {}, None)
            protected = HTTPError(PUBLIC, 401, "Unauthorized", {}, None)
            with patch.object(capture, "raw", side_effect=[robots, protected]), self.assertRaises(HTTPError):
                capture.get(PUBLIC)

    def test_actual_disallow_blocks_documented_api_too(self):
        with tempfile.TemporaryDirectory() as temp:
            capture = Capture(Path(temp), {"api.ashbyhq.com"})
            with patch.object(capture, "raw", return_value=(b"User-agent: *\nDisallow: /posting-api/\n", "a" * 64)) as fetch:
                with self.assertRaises(ValueError):
                    capture.get(PUBLIC)
                self.assertEqual(fetch.call_count, 1)


if __name__ == "__main__":
    unittest.main()
