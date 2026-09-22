import copy
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from probe_company_sources import accept_header_for, unavailable_robots_allowed
from atlanticbridge.outcome_qualification import parse_review_document

class DocumentSourceRepairTests(unittest.TestCase):
    def test_plain_text_robots_negotiation_only(self):
        self.assertEqual(accept_header_for('https://export.alberta.ca/robots.txt'),'text/plain, */*;q=0.1')
        self.assertEqual(accept_header_for('https://example.org/article'),'application/json, text/html, application/xml;q=0.9')
    def test_no_access_failure_is_waived(self):
        for code in (401,403,406,429,500,503):
            self.assertFalse(unavailable_robots_allowed(code,'https://export.alberta.ca/robots.txt'))
    def check_article(self,cid,heading,article):
        m=json.loads((ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json').read_text())
        s=copy.deepcopy(next(x for x in m['sources'] if x['id']==cid))
        s['required_text']=['Retained source fact']
        raw=f'<header>unrelated navigation</header><article class="{article}"><header><h1 class="{heading}">Primary title</h1><time>{s["publication_date_text"]}</time></header><p>Retained source fact</p></article>'.encode()
        rows=parse_review_document(raw,s)
        self.assertEqual(rows[0]['source_publication_date'],s['reviewed_publication_date'])
        self.assertNotIn('unrelated navigation',rows[0]['evidence_text'])
        with self.assertRaises(ValueError):parse_review_document(raw.replace(s['publication_date_text'].encode(),b'UNKNOWN'),s)
        with self.assertRaises(ValueError):parse_review_document(raw.replace(b'Retained source fact',b'gone'),s)
        with self.assertRaises(ValueError):parse_review_document(raw+raw,s)
    def test_nature_article_header_date_is_preserved(self):
        self.check_article('nature-farnham-plan-20220315','','news-release')
    def test_roquette_article_header_date_is_preserved(self):
        self.check_article('roquette-rd-20200619','page__heading','page__content')
    def test_original_failed_paths_are_not_silently_erased(self):
        m=json.loads((ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json').read_text())
        self.assertEqual({r['id'] for r in m['known_unavailable_paths']},{'stellantis-ontario-20220502','enel-alberta-operating-20200521'})
    def test_enel_prior_presence_is_explicit(self):
        m=json.loads((ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json').read_text())
        c=next(x for x in m['cases'] if x['id']=='enel-pincher-creek')
        self.assertIn('began operations in 2012',c['prior_presence_evidence']['required_text'])
        self.assertFalse(c['first_entry_confirmed'])

    def test_enel_escaped_publisher_body_and_date(self):
        import html
        m=json.loads((ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json').read_text())
        src=copy.deepcopy(next(x for x in m['sources'] if x['id']=='enel-issuer-alberta-operating-20200521'))
        content='<p>'+'. '.join(src['required_text'])+'</p>'
        raw=('<main><article-header><h1>Issuer release</h1><time>May 21, 2020</time></article-header><free-text><section data-content="'+html.escape(content,quote=True)+'"></section></free-text></main>').encode()
        self.assertEqual(parse_review_document(raw,src)[0]['source_publication_date'],'2020-05-21')
        with self.assertRaises(ValueError):parse_review_document(raw.replace(b'May 21, 2020',b'UNKNOWN'),src)
        with self.assertRaises(ValueError):parse_review_document(raw.replace(b'Riverview',b'Other project'),src)
        with self.assertRaises(ValueError):parse_review_document(raw+raw,src)
        src['reviewed_layout']['content_attribute']='invented'
        with self.assertRaises(ValueError):parse_review_document(raw,src)
    def test_invest_ontario_canonical_hostname_and_retained_tls_failure(self):
        m=json.loads((ROOT/'reviews/commercial_validation/discovery-review-2-2026-09-22.json').read_text())
        src=next(x for x in m['sources'] if x['id']=='stellantis-investontario-20220502')
        self.assertTrue(src['url'].startswith('https://www.investontario.ca/'))
        old=next(x for x in m['known_unavailable_paths'] if x['id']=='stellantis-ontario-20220502')
        self.assertEqual(old['alias_diagnostic_artifact_id'],10723187655)
