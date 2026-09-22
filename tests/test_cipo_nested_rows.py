from dataclasses import replace
import unittest
from unittest.mock import Mock

from atlanticbridge.sources.cipo import parse_detail_html
from atlanticbridge.current_cipo import observe_current_owners
from tests.test_cipo import FIXTURE, _search_result


class NestedCIPORowsTests(unittest.TestCase):
    def test_outer_layout_row_does_not_steal_first_fact(self):
        original = FIXTURE.read_text()
        html = '<div class="row"><div>' + original + '</div><div><h3>Index headings</h3>Unrelated goods description</div></div>'
        detail = parse_detail_html(html, record_id='2319647', detail_url='https://example.test/2319647')
        self.assertEqual(detail.application_number, '2319647')
        self.assertEqual(detail.owner_name, 'Siemens Aktiengesellschaft')
        self.assertEqual(detail.filed_date, '2024-02-06')

    def test_corrupt_application_number_fails_current_proof(self):
        session = Mock()
        session.search_owner.return_value = _search_result()
        detail = parse_detail_html(FIXTURE.read_text(), record_id='2319647', detail_url='https://example.test/2319647')
        session.fetch_detail.return_value = replace(detail, application_number='Index headings | Goods')
        result = observe_current_owners([{'id': 'reviewed', 'foreign_legal_name': 'Siemens Aktiengesellschaft', 'identity_confidence': 'HIGH'}], session, delay=0)
        self.assertEqual(result['status'], 'PARTIAL')
        self.assertEqual(result['observations'], [])
        self.assertEqual(result['summary']['failures'], 1)
        self.assertIn('does not match', result['failures'][0]['error'])
