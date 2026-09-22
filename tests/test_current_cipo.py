from dataclasses import replace
import unittest
from unittest.mock import Mock

from atlanticbridge.current_cipo import observe_current_owners
from atlanticbridge.sources.cipo import parse_detail_html
from tests.test_cipo import _search_result, FIXTURE


class CurrentCIPOTests(unittest.TestCase):
    def setUp(self):
        self.entity = {'id': 'reviewed', 'foreign_legal_name': 'Siemens Aktiengesellschaft', 'identity_confidence': 'HIGH'}
        self.session = Mock()
        self.session.search_owner.return_value = _search_result()
        self.session.fetch_detail.return_value = parse_detail_html(FIXTURE.read_text(), record_id='2319647', detail_url='https://example.test/2319647')

    def observe(self, **kw):
        return observe_current_owners([self.entity], self.session, delay=0, observed_at='2026-09-22T19:00:00Z', **kw)

    def test_observation_is_not_a_new_event_or_historical_clock(self):
        p = self.observe()
        self.assertEqual(len(p['observations']), 1)
        self.assertIsNone(p['observations'][0]['publicly_available_date'])
        self.assertEqual(p['observations'][0]['filed_date'], '2024-02-06')
        self.assertFalse(p['absence_inference_allowed'])
        self.assertFalse(p['backtest_eligible'])

    def test_owner_mismatch_is_not_promoted(self):
        self.session.fetch_detail.return_value = replace(self.session.fetch_detail.return_value, owner_name='Another company')
        self.assertEqual(self.observe()['observations'], [])

    def test_zero_results_remain_unknown_for_absence(self):
        self.session.search_owner.return_value = replace(_search_result(), num_found=0, num_returned=0, records=())
        p = self.observe()
        self.assertEqual(p['entities'][0]['coverage_state'], 'UNKNOWN_FOR_ABSENCE')
        self.assertEqual(p['observations'], [])

    def test_transport_failure_is_partial_not_zero_evidence(self):
        self.session.search_owner.side_effect = TimeoutError('source timeout')
        p = self.observe()
        self.assertEqual(p['status'], 'PARTIAL')
        self.assertEqual(p['summary']['successful_searches'], 0)
        self.assertEqual(len(p['failures']), 1)

    def test_detail_cap_is_explicit(self):
        original = _search_result()
        self.session.search_owner.return_value = replace(original, num_found=2, num_returned=2, records=original.records * 2)
        p = self.observe(detail_limit=1)
        self.assertTrue(p['entities'][0]['details_truncated'])
        self.assertEqual(self.session.fetch_detail.call_count, 1)
        self.assertFalse(p['absence_inference_allowed'])

    def test_unreviewed_identity_rejected(self):
        self.entity['identity_confidence'] = 'LOW'
        with self.assertRaises(ValueError):
            self.observe()
