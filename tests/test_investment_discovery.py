import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from atlanticbridge.company_sources import Ledger, parse_article
from atlanticbridge.investment_discovery import parse_investment_cards, discovery_summary, retained_review_records

ROOT = Path(__file__).resolve().parents[1]
SOURCE = json.loads((ROOT / 'reviews/company_sources/investment-discovery-2026-09-22.json').read_text())['sources'][0]


def page(company='Example', country='Germany', location='St. Thomas, ON', kind='Battery factory'):
    return f'''<a class="investment-announcement" data-controls="investment-1"></a>
    <a class="investment-announcement" data-controls="investment-1"></a>
    <article class="investment-announcement" id="investment-1"><h3 class="slide-title">{company}</h3>
    <div class="field--name-field-investment-type"><div class="field--item">{kind}</div></div>
    <div class="field--name-field-country"><div class="field--item">{country}</div></div>
    <div class="field--name-field-location"><div class="field--item">{location}</div></div>
    <div class="field--name-field-total-invested"><div class="field--item">$7 billion</div></div>
    <div class="field--name-field-total-jobs"><div class="field--item">3,000</div></div>
    </article>'''.encode()


class InvestmentDiscoveryTests(unittest.TestCase):
    def test_source_fields_preserved_without_realization_or_date_claim(self):
        row = parse_investment_cards(page(), SOURCE)[0]
        self.assertEqual(row['company_candidate'], 'Example')
        self.assertEqual(row['amount_as_published'], '$7 billion')
        self.assertEqual(row['jobs_as_published'], '3,000')
        self.assertIsNone(row['source_publication_date'])
        self.assertIsNone(row['operational_opening_date'])
        self.assertFalse(row['first_entry_confirmed'])
        self.assertFalse(row['backtest_eligible'])

    def test_mobile_controls_not_duplicate_cases(self):
        self.assertEqual(len(parse_investment_cards(page(), SOURCE)), 1)

    def test_missing_cards_is_failure_not_zero_outcomes(self):
        with self.assertRaises(ValueError):parse_investment_cards(b'<html>Maintenance</html>', SOURCE)

    def test_control_without_card_is_incomplete(self):
        with self.assertRaises(ValueError):parse_investment_cards(page()+b'<a class="investment-announcement" data-controls="investment-2"></a>', SOURCE)

    def test_duplicate_card_identity_is_rejected(self):
        with self.assertRaises(ValueError):parse_investment_cards(page()+page(), SOURCE)

    def test_required_fields_fail_closed(self):
        for changes in [{'country':''},{'company':''},{'kind':''},{'location':''}]:
            with self.assertRaises(ValueError):parse_investment_cards(page(**changes), SOURCE)

    def test_ambiguous_field_rejected(self):
        altered=page().replace(b'>Germany</div>', b'>Germany</div><div class="field--item">France</div>')
        with self.assertRaises(ValueError):parse_investment_cards(altered,SOURCE)

    def test_mixed_country_not_silently_normalized_to_eu(self):
        rows=parse_investment_cards(page(country='Netherlands & South Korea'),SOURCE)
        self.assertEqual(discovery_summary(rows)['country_labels_as_published'], {'Netherlands & South Korea':1})
        self.assertFalse(rows[0]['legal_identity_confirmed'])

    def test_scope_review_always_required_and_existing_hold_preserved(self):
        row=parse_investment_cards(page(kind='Military manufacturing'),SOURCE)[0]
        self.assertEqual(row['scope_exclusion'],'MILITARY_REVIEW_HOLD')
        self.assertEqual(row['sector_scope_review_status'],'REQUIRED_BEFORE_QUALIFICATION')

    def test_absent_money_is_unknown_not_zero(self):
        altered=page().replace(b'$7 billion',b'')
        self.assertIsNone(parse_investment_cards(altered,SOURCE)[0]['amount_as_published'])

    def test_incorrect_source_and_excess_size_rejected(self):
        with self.assertRaises(ValueError):parse_investment_cards(page(),dict(SOURCE,url='https://example.com/'))
        with self.assertRaises(ValueError):parse_investment_cards(b'x'*(16*1024*1024+1),SOURCE)

    def test_discovery_cannot_be_reported_as_qualified_labels(self):
        rows=parse_investment_cards(page(),SOURCE);rows[0]['first_entry_confirmed']=True
        with self.assertRaises(ValueError):discovery_summary(rows)

    def test_accepted_ledger_baselines_and_replays_identically(self):
        rows=parse_investment_cards(page(),SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            ledger=Ledger(str(Path(directory)/'state.sqlite'))
            try:
                sha=hashlib.sha256(page()).hexdigest()
                self.assertEqual(ledger.apply(SOURCE,rows,'2026-09-22T20:00:00Z',sha),[])
                self.assertEqual(ledger.apply(SOURCE,rows,'2026-09-22T20:01:00Z',sha),[])
                self.assertEqual(discovery_summary(rows)['dated_first_entry_labels'],0)
            finally:ledger.close()

    def test_publication_date_anchor_for_product_launch_is_required(self):
        source=json.loads((ROOT/'reviews/company_sources/investment-discovery-2026-09-22.json').read_text())['sources'][1]
        with self.assertRaises(ValueError):parse_article(b'<h1>Canada launch</h1><main>part of Ericsson in Canada</main>',source)

    def test_export_preserves_first_observation_after_second_capture(self):
        rows=parse_investment_cards(page(),SOURCE)
        ledger=Ledger(":memory:")
        try:
            sha=hashlib.sha256(page()).hexdigest()
            ledger.apply(SOURCE,rows,'2026-09-22T20:00:00Z',sha)
            ledger.apply(SOURCE,rows,'2026-09-22T20:10:00Z',sha)
            exported=retained_review_records(ledger,rows)[0]
            self.assertEqual(exported['first_observed_at'],'2026-09-22T20:00:00Z')
            self.assertEqual(exported['last_observed_at'],'2026-09-22T20:10:00Z')
            self.assertEqual(exported['raw_sha256'],sha)
        finally:ledger.close()

    def test_uncommitted_records_cannot_be_exported_as_observed(self):
        ledger=Ledger(":memory:")
        try:
            with self.assertRaises(ValueError):retained_review_records(ledger,parse_investment_cards(page(),SOURCE))
        finally:ledger.close()
