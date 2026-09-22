import unittest
from atlanticbridge.company_sources import parse_index


class TaxonomyRegressionTests(unittest.TestCase):
    def test_montreal_subject_links_are_not_articles(self):
        source = {"id": "fixture", "kind": "index", "url": "https://example.org/en/news/", "article_path_prefix": "/en/news/"}
        body = b'<a href="/en/news/subject/montreal-international-en/">Montreal International</a><a href="/en/news/company-announcement/">Company announces Canada office</a>'
        rows = parse_index(body, source)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_url"], "https://example.org/en/news/company-announcement/")


if __name__ == "__main__":
    unittest.main()
