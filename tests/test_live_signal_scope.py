from copy import deepcopy
import unittest

from atlanticbridge.live_signal_scope import apply_commercial_scope, classify_signal
from atlanticbridge.live_signals import build_canadabuys_live_signals
from atlanticbridge.canadabuys_store import ingest_awards
from tests.test_live_signals import award, connect
from datetime import date


class LiveScopeTests(unittest.TestCase):
    def test_explicit_military_is_excluded(self):
        for text in ['Department of National Defence', 'DND C9 Machine Gun', 'Spares for armament loaders']:
            self.assertEqual(classify_signal({'title': text})['state'], 'EXCLUDED_MILITARY')

    def test_military_end_user_is_not_hidden_by_pspc(self):
        signal = {'contracting_entity': 'PSPC', 'title': 'Equipment'}
        raw = {'endUserEntitiesName-nomEntitesUtilisateurFinal-eng': 'Department of National Defence'}
        self.assertEqual(classify_signal(signal, raw)['state'], 'EXCLUDED_MILITARY')

    def test_civilian_coast_guard_is_not_military_by_fuel_name(self):
        signal = {'title': 'Naval Distillate Fuel', 'award_description': 'Canadian Coast Guard requirement',
                  'regions_of_delivery': '*Nunavut Territory'}
        self.assertEqual(classify_signal(signal)['state'], 'INCLUDED_CANADIAN_DELIVERY')

    def test_embassy_contract_abroad_is_not_canadian_entry(self):
        signal = {'title': 'Cleaning Embassy of Canada in Madrid', 'regions_of_delivery': '*Spain'}
        self.assertEqual(classify_signal(signal)['state'], 'EXCLUDED_FOREIGN_DELIVERY')

    def test_mixed_delivery_preserves_canadian_evidence(self):
        self.assertEqual(classify_signal({'regions_of_delivery': '*Netherlands *Ontario (except NCR)'})['state'],
                         'INCLUDED_CANADIAN_DELIVERY')

    def test_unknown_is_not_negative(self):
        self.assertEqual(classify_signal({})['state'], 'INCLUDED_BUYER_ONLY')
        self.assertEqual(classify_signal({'regions_of_delivery': '*Europe *Remote Offsite'})['state'], 'REVIEW_REQUIRED')
        self.assertEqual(classify_signal({'title': 'CBRN analysis', 'regions_of_delivery': '*Canada'})['state'], 'REVIEW_REQUIRED')

    def test_accented_reviewed_canadian_regions_are_not_unknown(self):
        for region in ('Montréal', 'Montre\u0301al', 'MONTRÉAL', 'Québec', 'Québec (except NCR)'):
            with self.subTest(region=region):
                self.assertEqual(classify_signal({'regions_of_delivery': '*' + region})['state'],
                                 'INCLUDED_CANADIAN_DELIVERY')

    def test_accent_normalization_keeps_exact_reviewed_region_boundary(self):
        for region in ('Montréal-Nord', 'Québec Street', 'Montréal;Remote Offsite'):
            with self.subTest(region=region):
                expected = ('INCLUDED_CANADIAN_DELIVERY' if ';' in region
                            else 'INCLUDED_BUYER_ONLY')
                self.assertEqual(classify_signal({'regions_of_delivery': '*' + region})['state'],
                                 expected)
        self.assertEqual(classify_signal({'regions_of_delivery': '*Europe *Montréal-Nord'})['state'],
                         'REVIEW_REQUIRED')
        self.assertEqual(classify_signal({'regions_of_delivery': '*Europe *Montréal'})['state'],
                         'INCLUDED_CANADIAN_DELIVERY')

    def test_accented_canadian_region_does_not_override_scope_exclusions(self):
        for title, expected in (('DND equipment', 'EXCLUDED_MILITARY'),
                                ('CBRN analysis', 'REVIEW_REQUIRED')):
            with self.subTest(title=title):
                self.assertEqual(classify_signal({'title': title, 'regions_of_delivery': '*Montréal'})['state'],
                                 expected)

    def test_accented_region_preserves_published_source_values(self):
        conn = connect(':memory:')
        self.addCleanup(conn.close)
        ingest_awards(conn, [award(reference='accented', supplier='Example', country='France',
                                  publication='2026-09-20')], source_sha256='proof',
                      source_url='https://example.test/source.csv', source_bytes=1)
        payload = build_canadabuys_live_signals(conn, as_of_date=date(2026, 9, 22))
        payload['signals'][0]['regions_of_delivery'] = '*Montréal'
        original = deepcopy(payload)
        result = apply_commercial_scope(payload, conn)
        self.assertEqual(payload, original)
        self.assertEqual(result['source'], original['source'])
        self.assertEqual(result['summary'], original['summary'])
        signal = result['signals'][0]
        self.assertEqual(signal['scope_review']['state'], 'INCLUDED_CANADIAN_DELIVERY')
        for key in ('regions_of_delivery', 'publicly_available_date', 'event_date',
                    'first_observed_at', 'last_observed_at', 'source_url', 'record_id', 'id'):
            self.assertEqual(signal[key], original['signals'][0][key])
        self.assertIn('does not establish a Canadian office or first entry', signal['why_surfaced'])

    def test_unavailable_stays_unavailable(self):
        p = {'status': 'UNAVAILABLE', 'reason': 'source failed', 'signals': []}
        self.assertEqual(apply_commercial_scope(p), p)

    def test_scope_ledger_preserves_source_and_recomputes_counts(self):
        conn = connect(':memory:')
        records = [award(reference=str(i),supplier=f'Supplier {i}',country='France',publication='2026-09-20') for i in range(3)]
        ingest_awards(conn, records, source_sha256='proof', source_url='https://example.test/source.csv', source_bytes=1)
        p = build_canadabuys_live_signals(conn, as_of_date=date(2026,9,22))
        p['signals'][0]['title'] = 'DND armament'
        p['signals'][1]['regions_of_delivery'] = '*Spain'
        original = deepcopy(p)
        out = apply_commercial_scope(p, conn)
        self.assertEqual(p, original)
        self.assertEqual(out['summary']['signal_count'], 1)
        self.assertEqual(out['summary']['company_count'], 1)
        self.assertIsNone(out['summary']['cad_contract_amount'])
        self.assertEqual(out['scope_audit']['input_signal_count'], 3)
        self.assertEqual(len(out['scope_audit']['excluded_signals']), 2)
        self.assertEqual(out['source'], p['source'])
        self.assertEqual(conn.execute('SELECT COUNT(*) FROM canadabuys_awards').fetchone()[0], 3)
        conn.close()

    def test_buyer_only_explanation_does_not_invent_location_or_control(self):
        conn = connect(':memory:')
        ingest_awards(conn, [award(reference='x',supplier='Example',country='Ireland',publication='2026-09-20')],
                      source_sha256='proof',source_url='https://example.test/source.csv',source_bytes=1)
        p = build_canadabuys_live_signals(conn,as_of_date=date(2026,9,22))
        p['signals'][0]['regions_of_delivery'] = ''
        s = apply_commercial_scope(p, conn)['signals'][0]
        self.assertEqual(s['signal_stage'], 'CANADIAN_BUYER_RELATIONSHIP_LOCATION_UNVERIFIED')
        self.assertIn('ultimate control is not established', s['why_surfaced'])
        self.assertIn('not operations in Canada', s['why_surfaced'])
        conn.close()
