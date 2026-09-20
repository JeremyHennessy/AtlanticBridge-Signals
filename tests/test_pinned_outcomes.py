from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from atlanticbridge.entry_identity import _lead_timing, normalize_legal_name
from atlanticbridge.sources.corporations_canada import detail_corporation_names, first_federal_jurisdiction_event

ROOT = Path(__file__).resolve().parents[1]
spec = spec_from_file_location('refresh_outcome_cases', ROOT / 'scripts/refresh_outcome_cases.py')
refresh = module_from_spec(spec)
spec.loader.exec_module(refresh)


class PinnedOutcomeTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((ROOT / 'reviews/outcome_audit/2026-09-20-cases.json').read_text())

    def test_every_baseline_case_has_a_consistent_review_disposition(self):
        base = json.loads((ROOT / 'reviews/outcome_audit/2026-09-20-baseline.json').read_text())
        cases = self.payload['cases']
        self.assertEqual(len(cases), 27)
        self.assertEqual(len({c['outcome_record_id'] for c in cases}), 27)
        self.assertEqual({q['canadian_entry_corporation_number'] for q in base['queue']} | {'11075896'}, {c['corporation_number'] for c in cases})
        for c in cases:
            self.assertEqual(first_federal_jurisdiction_event(c['registry_projection']), (c['federal_event_type'], c['federal_event_date']))
            self.assertIn(normalize_legal_name(c['canadian_business_name']), {normalize_legal_name(n) for n in detail_corporation_names(c['registry_projection'])})
            self.assertEqual(_lead_timing(c['notification_month'], c['federal_event_date']), (c['notification_timing'], c['days_before_notification_month']))
            self.assertFalse(c['model_eligible'])
            self.assertTrue(c['audit_note'])

    def test_topdesk_primary_evidence_excludes_2022_as_assumed_first_entry(self):
        case = next(c for c in self.payload['cases'] if c['outcome_record_id'] == 'b206b73fcd9d6ee2451a66884be6094f77bafaf2b5c469199c9f0d868ac1f7cb')
        self.assertEqual(case['outcome_classification'], 'EXISTING_CANADIAN_PRESENCE')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        primary = [e for e in case['additional_evidence'] if e['source_type'] == 'OFFICIAL_MUNICIPAL_ANNUAL_REPORT']
        self.assertEqual(len(primary), 1)
        self.assertEqual(primary[0]['event_date'], '2015')
        self.assertEqual(primary[0]['event_date_precision'], 'YEAR')
        self.assertEqual(primary[0]['supports'], 'EXISTING_CANADIAN_PRESENCE')

    def test_bayer_environmental_science_is_not_treated_as_2022_first_entry(self):
        case = next(c for c in self.payload['cases'] if c['outcome_record_id'] == '814a591396e8a1ef40318eefe89e7c27c15c6bcdabb0dbe5100da163c89c4b58')
        self.assertEqual(case['outcome_classification'], 'EXISTING_CANADIAN_PRESENCE')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        evidence = {e['source_type']: e for e in case['additional_evidence']}
        self.assertEqual(evidence['PMRA_APPROVED_LABEL_ARCHIVE']['registration_number'], '32800')
        self.assertEqual(evidence['PMRA_APPROVED_LABEL_ARCHIVE']['source_date'], '2018-06-13')
        self.assertEqual(evidence['OFFICIAL_GOVERNMENT_REGULATORY_DECISION']['registration_number'], '32800')
        self.assertEqual(evidence['OFFICIAL_GOVERNMENT_REGULATORY_DECISION']['supports'], 'PRODUCT_REGISTRATION_CONTINUITY_POST_TRANSFER')

    def test_refresh_verifies_both_sources_and_fails_on_event_change(self):
        c = self.payload['cases'][0]
        record = SimpleNamespace(record_id=c['outcome_record_id'], is_new_business=True,
                                 investor_name=c['investor_name'], certification_month=c['notification_month'],
                                 canadian_businesses_json=json.dumps([{'name': c['canadian_business_name']}]))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.json'
            path.write_text(json.dumps({'case_count': 1, 'cases': [c]}))
            with patch.object(refresh, 'fetch_index_page', return_value=(c['outcome_source_url'], '<html>')), \
                 patch.object(refresh, 'parse_index_html', return_value=[record]), \
                 patch.object(refresh, 'fetch_corporation_json', return_value=(c['registry_source_url'], c['registry_projection'])):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(refresh.refresh(path, Path(tmp)/'output')['case_count'], 1)
                changed = json.loads(json.dumps(c))
                changed['federal_event_date'] = '1900-01-01'
                path.write_text(json.dumps({'case_count': 1, 'cases': [changed]}))
                with self.assertRaisesRegex(ValueError, 'Registry event changed'):
                    refresh.refresh(path, Path(tmp)/'changed')

    def test_missing_notification_is_not_silently_accepted(self):
        c = self.payload['cases'][0]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'cases.json'
            path.write_text(json.dumps({'case_count': 1, 'cases': [c]}))
            with patch.object(refresh, 'fetch_index_page', return_value=(c['outcome_source_url'], '<html>')), \
                 patch.object(refresh, 'parse_index_html', return_value=[]):
                with self.assertRaisesRegex(ValueError, 'Notification moved or changed'):
                    refresh.refresh(path, Path(tmp)/'output')
