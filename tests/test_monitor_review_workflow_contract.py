"""Offline regression checks for large checkpoint downloads in the proof job."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MonitorReviewWorkflowContractTests(unittest.TestCase):
    def setUp(self):
        text = (ROOT / ".github/workflows/monitor-review-proof.yml").read_text()
        start = text.index("      - name: Read one exact production metadata snapshot")
        end = text.index("      - name: Preserve tested code", start)
        self.step = text[start:end]

    def test_raw_media_reads_exact_pinned_checkpoint_above_inline_limit(self):
        self.assertIn('STATE="$(cat artifacts/metadata-review/state-commit.txt)"', self.step)
        self.assertIn('gh api -H "Accept: application/vnd.github.raw+json" '
                      '"repos/JeremyHennessy/AtlanticBridge-Signals/contents/checkpoint.json?ref=$STATE" '
                      '> artifacts/metadata-review/checkpoint.json', self.step)
        self.assertNotIn("--jq '.content'", self.step)
        self.assertNotIn("base64 -d", self.step)

    def test_empty_oversized_and_invalid_checkpoints_cannot_pass(self):
        self.assertIn("assert 0 < p.stat().st_size <= 16*1024*1024", self.step)
        self.assertIn("c=validate(json.loads(p.read_text()))", self.step)
        self.assertIn("api.parse(raw,register)", self.step)
        self.assertNotIn("continue-on-error", self.step)


if __name__ == "__main__":
    unittest.main()
