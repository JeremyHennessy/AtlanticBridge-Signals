"""Offline contract for the pinned Playwright runner; does not start browsers."""
from pathlib import Path
import re
import unittest
ROOT=Path(__file__).resolve().parents[1]

class BrowserWorkflowContractTests(unittest.TestCase):
    def job(self, filename, job):
        text=(ROOT/".github/workflows"/filename).read_text()
        marker="  "+job+":"
        start=text.index(marker)
        rest=text[start+len(marker):]
        match=re.search(r"^  [A-Za-z0-9_-]+:\s*$",rest,re.M)
        return rest[:match.start()] if match else rest

    def test_hosted_acceptance_uses_supported_pinned_runner(self):
        job=self.job("pages.yml","hosted-acceptance")
        self.assertIn("runs-on: ubuntu-24.04",job)
        self.assertNotIn("runs-on: ubuntu-latest",job)
        self.assertIn("playwright@1.55.0",job)
        self.assertIn("chromium webkit",job)
        self.assertIn("needs: deploy",job)

    def test_pr_browser_acceptance_uses_same_supported_runner(self):
        job=self.job("ui-usability.yml","browser-acceptance")
        self.assertIn("runs-on: ubuntu-24.04",job)
        self.assertNotIn("runs-on: ubuntu-latest",job)
        self.assertIn("playwright@1.55.0",job)
        self.assertIn("chromium webkit",job)
        self.assertIn("node tests/ui_visual_acceptance.mjs",job)
        self.assertIn("tests/test_canadabuys_quality.cjs",job)

if __name__=="__main__":unittest.main()
