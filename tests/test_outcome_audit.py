from contextlib import redirect_stdout
import hashlib
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from atlanticbridge.entry_identity import ensure_entry_identity_schema, entry_identity_summary

spec = spec_from_file_location('export_outcome_audit', Path(__file__).resolve().parents[1] / 'scripts/export_outcome_audit.py')
audit = module_from_spec(spec)
spec.loader.exec_module(audit)


class OutcomeAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'audit.sqlite'
        self.conn = sqlite3.connect(self.db)
        self.conn.row_factory = sqlite3.Row
        ensure_entry_identity_schema(self.conn)
        self.conn.execute('CREATE TABLE investment_canada_notifications (record_id TEXT, source_url TEXT, investor_node_id TEXT, notification_type TEXT)')
        self.conn.execute("INSERT INTO entry_identity_runs VALUES ('run', '2019-01', '2025-12', 'a', 1, 'b', 1, 27, 140, 20, '2026-09-20')")
        columns = self.conn.execute('PRAGMA table_info(entry_identity_matches)').fetchall()
        raw = json.dumps({'activities': [{'activity': {'activity': 'Incorporation', 'date': '2019-02-21'}}]})
        for i in range(27):
            row = {c['name']: 0 if c['type'] == 'INTEGER' else '' for c in columns}
            row.update(run_id='run', outcome_record_id=str(i), certification_month='2019-10',
                       investor_name=f'Investor {i}', source_businesses_json='[]',
                       detail_status='FEDERAL_ENTITY_CONFIRMED', detail_raw_json=raw,
                       detail_raw_hash=hashlib.sha256(raw.encode()).hexdigest(),
                       federal_event_type='Incorporation', federal_event_date='2019-02-21',
                       timing_status='PRE_ENTRY', lead_days_to_outcome_month_start=222,
                       gold_selected=int(i < 20), gold_rank=i+1)
            self.conn.execute(f"INSERT INTO entry_identity_matches ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", list(row.values()))
            self.conn.execute('INSERT INTO investment_canada_notifications VALUES (?, ?, ?, ?)', (str(i), 'https://example.test', str(i), 'New Business'))
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_all_confirmations_exported_without_gold_sample_truncation(self):
        with redirect_stdout(io.StringIO()):
            payload = audit.export_audit(self.db, Path(self.tmp.name) / 'result.json')
        self.assertEqual(payload['case_count'], 27)
        self.assertEqual(len({c['outcome_record_id'] for c in payload['cases']}), 27)
        self.assertTrue(all(not c['model_eligible'] and c['first_canadian_operations_date'] is None for c in payload['cases']))
        self.assertEqual(payload['cases'][0]['notification_timing'], 'BEFORE_NOTIFICATION_MONTH')
        self.assertEqual(payload['cases'][0]['days_before_notification_month'], 222)

    def test_tampered_registry_payload_fails_export(self):
        self.conn.execute("UPDATE entry_identity_matches SET detail_raw_json = '{}' WHERE outcome_record_id = '0'")
        self.conn.commit()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            audit.export_audit(self.db, Path(self.tmp.name) / 'bad.json')

    def test_legacy_summary_corrects_label_without_rewriting_stored_evidence(self):
        summary = entry_identity_summary(self.conn)
        self.assertEqual(summary['timing_status_counts'], [{'timing_status': 'BEFORE_NOTIFICATION_MONTH', 'records': 27}])
        self.assertTrue(all(r['timing_status'] == 'BEFORE_NOTIFICATION_MONTH' for r in summary['gold_cohort']))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM entry_identity_matches WHERE timing_status = 'PRE_ENTRY'").fetchone()[0], 27)

    def test_tvm_cross_name_fund_evidence_does_not_promote_outcomes(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        cases = [
            case for case in payload['cases']
            if case['investor_name'] == 'TVM Life Science Ventures VIII SCSp'
        ]
        self.assertEqual(
            {case['canadian_business_name'] for case in cases},
            {'Ocellaris Pharma Inc.', 'Acanthas Pharma Inc.'},
        )
        for case in cases:
            self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
            self.assertIsNone(case['first_canadian_operations_date'])
            self.assertFalse(case['model_eligible'])
            supports = {e['supports'] for e in case['additional_evidence']}
            self.assertIn('CROSS_NAME_FUND_COMMITMENT_SUPPORTED', supports)
            self.assertIn('LEGAL_ENTITY_EQUIVALENCE_UNVERIFIED', supports)
            self.assertIn('no legal SAME_LEGAL_ENTITY_AS', case['audit_note'])

    def test_relieve_recruitment_evidence_does_not_promote_outcome(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Relieve Consulting Services Canada Inc.'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_RECRUITMENT_ACTIVITY_BY_2022_09', supports)
        self.assertIn('does not establish the first Canadian operating date', case['audit_note'])

    def test_sanllo_market_evidence_does_not_promote_outcome_or_identity(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Sanllo Canada Inc'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('FOREIGN_SIDE_SANLLO_MANAGEMENT_CHAIN_PREENTRY', supports)
        self.assertIn('CANADIAN_PRODUCE_TRADE_MEMBERSHIP_BY_2022_11_15', supports)
        self.assertIn('CANADA_MARKET_TRADEMARK_ACTIVITY_BY_2022_11_24', supports)
        self.assertIn('does not establish direct ownership of Sanllo Canada', case['audit_note'])
        self.assertIn('named-investor relationship', case['audit_note'])

    def test_vaxxinova_parent_activity_does_not_promote_local_outcome(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Vaxxinova Canada, Inc.'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('PARENT_CANADA_FACING_ACTIVITY_BEFORE_LOCAL_INCORPORATION', supports)
        self.assertIn('CANADIAN_BRAND_REGISTRATION_PREENTRY_NOT_OPERATIONAL_PROOF', supports)
        self.assertIn('Neither source establishes when Vaxxinova Canada itself first sold', case['audit_note'])

    def test_tiandingfeng_preentry_signal_does_not_promote_outcome(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Tiandingfeng Canada Nonwovens Co., Ltd.'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADA_MARKET_INTENT_BEFORE_LOCAL_INCORPORATION', supports)
        self.assertIn('POST_NOTIFICATION_FACTORY_SITE_PROJECT', supports)
        self.assertIn('not proof of Canadian operations', case['audit_note'])
        self.assertIn('France as ultimate control', case['audit_note'])

    def test_sioo_establishment_evidence_does_not_create_first_operation_date(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Sioo Wood Protection Industry Canada Inc.'
        )
        self.assertEqual(
            case['outcome_classification'],
            'ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED',
        )
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_ESTABLISHMENT_BY_2023_06_21', supports)
        self.assertIn('CANADA_MARKET_INTENT_PREESTABLISHMENT_NOT_OPERATIONAL_PROOF', supports)
        self.assertIn('Neither source gives', case['audit_note'])
        self.assertIn('first sale', case['audit_note'])

    def test_leadership_establishment_year_does_not_order_notification_or_services(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Leadership Pipeline Institute Canada Inc.'
        )
        self.assertEqual(
            case['outcome_classification'],
            'ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED',
        )
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_SUBSIDIARY_ESTABLISHMENT_DURING_2023', supports)
        self.assertIn('cannot order establishment relative to the September 2023', case['audit_note'])
        self.assertIn('first Canadian training, consulting or service date', case['audit_note'])

    def test_digitary_project_evidence_does_not_order_notification_or_first_service(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'DIGITARY CANADA INC.'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_NATIONAL_PROJECT_AWARD_DURING_NOTIFICATION_MONTH', supports)
        self.assertIn('CANADIAN_PROJECT_IMPLEMENTATION_START_MONTH', supports)
        self.assertIn('CURRENT_CANADIAN_ENTITY_PROJECT_RELATIONSHIP', supports)
        self.assertIn('do not establish whether the award preceded the notification within June', case['audit_note'])
        self.assertIn('exact first Canadian service/operation date', case['audit_note'])

    def test_hanecs_year_level_location_does_not_order_notification_or_resolve_identity(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'HANECS Canada Inc.'
        )
        self.assertEqual(
            case['outcome_classification'],
            'ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED',
        )
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_LOCATION_ESTABLISHMENT_DURING_2021', supports)
        self.assertIn('FOREIGN_GROUP_ROLE_CONTEXT_ONLY', supports)
        self.assertIn('cannot order establishment relative to the notification', case['audit_note'])
        self.assertIn('named-investor relationship open', case['audit_note'])

    def test_trillium_january_transition_evidence_does_not_create_first_operation_date(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Trillium Supply Chain Inc.'
        )
        self.assertEqual(
            case['outcome_classification'],
            'ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED',
        )
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('PLANNED_TRILLIUM_FACILITY_OPERATIONAL_TRANSITION_JAN_2021', supports)
        self.assertIn('RETROSPECTIVE_PLEADED_OPERATIONAL_HISTORY_JAN_2021', supports)
        self.assertIn('not independent fact-finding', case['audit_note'])
        self.assertIn('does not establish Trillium\'s absolute first Canadian operation', case['audit_note'])

    def test_antea_2020_establishment_does_not_backdate_2019_operations(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'Antea Canada Inc.'
        )
        self.assertEqual(
            case['outcome_classification'],
            'ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED',
        )
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        supports = {e['supports'] for e in case['additional_evidence']}
        self.assertIn('CANADIAN_OFFICE_ESTABLISHMENT_DURING_2020', supports)
        self.assertIn('CURRENT_CANADIAN_OPERATING_FOOTPRINT', supports)
        self.assertIn('after the August 2019 Investment Canada notification', case['audit_note'])
        self.assertIn('does not establish the exact opening date', case['audit_note'])

    def test_conteyor_cipo_signal_does_not_promote_local_outcome(self):
        root = Path(__file__).resolve().parents[1]
        payload = json.loads(
            (root / 'reviews/outcome_audit/2026-09-20-cases.json').read_text()
        )
        case = next(
            case for case in payload['cases']
            if case['canadian_business_name'] == 'conTeyor Canada Ltd.'
        )
        self.assertEqual(case['outcome_classification'], 'UNRESOLVED')
        self.assertIsNone(case['first_canadian_operations_date'])
        self.assertFalse(case['model_eligible'])
        evidence = case['additional_evidence']
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]['source_date'], '1999-07-13')
        self.assertEqual(
            evidence[0]['supports'],
            'CANADA_IP_MARKET_SIGNAL_LONG_BEFORE_LOCAL_INCORPORATION',
        )
        self.assertIn('does not establish local Canadian manufacturing', case['audit_note'])
        self.assertIn('no relationship to Xcel Fabrication is asserted', case['audit_note'])

