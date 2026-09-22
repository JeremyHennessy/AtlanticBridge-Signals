import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReviewedLayoutTests(unittest.TestCase):
    def source(self, key):
        manifest = json.loads((ROOT / 'reviews/commercial_validation/discovery-review-2026-09-22.json').read_text())
        return next(s for s in manifest['sources'] if s['id'] == key)

    def test_empty_hero_does_not_replace_actual_sanofi_title(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('sanofi-flu-inauguration-20260916')
        body=b'<title>Actual flu announcement</title><h1 class="hero_title"></h1><div id="ReleaseContent">Sept. 16, 2026 Charles Best Building will manufacture</div>'
        row=parse_review_document(body,s)[0]
        self.assertEqual(row['title'],'Actual flu announcement')
        self.assertEqual(row['source_publication_date'],'2026-09-16')

    def test_sidebar_article_does_not_replace_disclosure_body(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('avanade-halifax-20220628')
        body=b'<h1 class="page-title">Annual disclosures</h1><article>Unrelated sidebar</article><article class="article--full"><div class="field--name-body">Tuesday June 28, 2022 Avanade Canada Inc. has established and will grow a new Halifax office with up to 700 jobs. Media contact:</div></article>'
        row=parse_review_document(body,s)[0]
        self.assertIn('Avanade Canada Inc.',row['evidence_text'])
        self.assertNotIn('Unrelated sidebar',row['evidence_text'])

    def test_duplicate_selected_region_blocks(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('sanofi-flu-inauguration-20260916')
        with self.assertRaises(ValueError):
            parse_review_document(b'<title>Title</title><div id="ReleaseContent">A</div><div id="ReleaseContent">B</div>',s)

    def test_missing_selected_region_cannot_fall_back_to_page(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('sanofi-flu-inauguration-20260916')
        with self.assertRaises(ValueError):
            parse_review_document(b'<title>Title</title><main>Sept. 16, 2026 Charles Best Building will manufacture</main>',s)

    def test_arbitrary_selector_changes_are_not_accepted(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('sanofi-flu-inauguration-20260916');s['reviewed_layout']['content_selector']='body'
        with self.assertRaises(ValueError):parse_review_document(b'<body>Title</body>',s)

    def test_scoped_content_still_requires_date_anchor(self):
        from atlanticbridge.outcome_qualification import parse_review_document
        s=self.source('sanofi-flu-inauguration-20260916')
        with self.assertRaises(ValueError):
            parse_review_document(b'<title>Title</title><div id="ReleaseContent">Charles Best Building will manufacture</div>',s)
