import copy
import unittest
from atlanticbridge.pilot_measurement import analyse

def empty():return dict(schema_version=1,participants=[],reviews=[],paired_research_tasks=[],purchase_feedback=[])
def example():
    d=empty();d['participants']=[dict(reviewer='TEST reviewer',role='TEST business development',recorded_date='2026-09-22',consented=True,independent_user=True,consent_record='TEST ONLY private reference')]
    d['reviews']=[dict(reviewer='TEST reviewer',alert_id='TEST source',identity_correct=None,source_supported=True,useful=True,already_known=False,review_seconds=120,timing_basis='ELAPSED_PAGE_VIEW_INCLUDES_IDLE')];return d
class PilotMeasurementTests(unittest.TestCase):
    def test_empty_pilot_has_no_invented_users_or_savings(self):
        r=analyse(empty());self.assertEqual(r['independent_consented_participants'],0);self.assertIsNone(r['median_active_seconds_saved']);self.assertFalse(r['commercial_viability_proven'])
    def test_page_time_does_not_become_savings(self):
        r=analyse(example());self.assertIsNone(r['median_active_seconds_saved']);self.assertEqual(r['per_reviewer']['TEST reviewer']['mean_elapsed_page_view_seconds'],120)
    def test_unknown_identity_remains_unknown(self):
        r=analyse(example())['per_reviewer']['TEST reviewer'];self.assertIsNone(r['identity_accuracy']['rate']);self.assertEqual(r['verified_useful_alerts'],0)
    def test_unconsented_export_is_excluded_not_enrolled(self):
        d=example();d['participants']=[];r=analyse(d);self.assertEqual(r['participants_with_reviews'],0);self.assertEqual(r['excluded_unverified_reviewer_submissions'],1)
    def test_duplicates_do_not_inflate_participation(self):
        d=example();d['reviews']*=2
        with self.assertRaises(ValueError):analyse(d)
    def test_consent_needs_a_record(self):
        d=example();d['participants'][0]['consent_record']=None
        with self.assertRaises(ValueError):analyse(d)
    def test_negative_savings_are_not_hidden(self):
        d=example();d['paired_research_tasks']=[dict(reviewer='TEST reviewer',task_id='TEST task',timing_basis='MANUALLY_TIMED_ACTIVE_RESEARCH',order='TOOL_FIRST',baseline_method='MANUAL_RESEARCH',timing_record='TEST record',baseline_seconds=60,tool_seconds=90)]
        self.assertEqual(analyse(d)['median_active_seconds_saved'],-30)
        d['paired_research_tasks'][0]['timing_basis']='ELAPSED_PAGE_VIEW_INCLUDES_IDLE'
        with self.assertRaises(ValueError):analyse(d)
    def test_infinite_or_boolean_time_is_invalid(self):
        for v in (float('nan'),float('inf'),True,-1):
            d=example();d['reviews'][0]['review_seconds']=v
            with self.assertRaises(ValueError):analyse(d)
    def test_willingness_is_not_a_payment(self):
        d=example();d['purchase_feedback']=[dict(reviewer='TEST reviewer',willing_to_pay=True,payment_verified=False)]
        r=analyse(d);self.assertEqual(r['willing_to_pay_statements'],1);self.assertEqual(r['verified_paying_participants'],0)
        d['purchase_feedback'][0]['payment_verified']=True
        with self.assertRaises(ValueError):analyse(d)
    def test_multiple_reviewers_have_separate_denominators(self):
        d=example();p=copy.deepcopy(d['participants'][0]);p['reviewer']='TEST other';d['participants'].append(p)
        r=copy.deepcopy(d['reviews'][0]);r['reviewer']='TEST other';d['reviews'].append(r)
        result=analyse(d);self.assertEqual(result['submitted_review_observations'],2);self.assertEqual(result['unique_reviewed_alerts'],1)
