from copy import deepcopy
import unittest

from atlanticbridge.live_signal_scope import apply_commercial_scope, classify_signal
from atlanticbridge.live_signals import build_canadabuys_live_signals
from atlanticbridge.canadabuys_store import ingest_awards
from atlanticbridge.db import connect
from tests.test_live_signals import award
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
        self.assertEqual(out['summary']['cad_contract_amount'], '1000')
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
