import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('delivery',ROOT/'scripts/check_monitor_delivery.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now='2026-09-23T10:45:00Z';self.w={'state':'active'}
        self.h={'schema_version':1,'status':'OBSERVED','last_attempt_at':'2026-09-22T22:01:26Z'}
    def check(self,runs=None):return g.decide(self.now,self.w,self.h,runs or [])
    def runrow(self,**changes):
        return dict(head_branch='main',event='schedule',status='completed',created_at='2026-09-23T09:37:00Z')|changes
    def test_missing_trigger_is_recoverable(self):self.assertEqual(self.check(),'MISSING_DAILY_EXECUTION')
    def test_primary_grace_preserved(self):
        self.now='2026-09-23T10:06:59Z';self.assertEqual(self.check(),'BEFORE_RECOVERY_WINDOW')
    def test_no_duplicate_when_collected_today(self):
        self.h['last_attempt_at']='2026-09-23T10:40:00Z';self.assertEqual(self.check(),'ALREADY_COLLECTED_TODAY')
    def test_disabled_not_overridden(self):
        self.w['state']='disabled_manually';self.assertEqual(self.check(),'DISABLED_WORKFLOW_REQUIRES_REVIEW')
    def test_running_not_restarted(self):self.assertEqual(self.check([self.runrow(status='in_progress')]),'RUN_ALREADY_ACTIVE')
    def test_queued_not_duplicated(self):self.assertEqual(self.check([self.runrow(status='queued')]),'RUN_ALREADY_ACTIVE')
    def test_stalled_requires_review(self):self.assertEqual(self.check([self.runrow(status='in_progress',created_at='2026-09-23T08:00:00Z')]),'STALLED_RUN_REQUIRES_REVIEW')
    def test_failed_run_not_hidden_with_retry(self):self.assertEqual(self.check([self.runrow(conclusion='failure')]),'ATTEMPT_EXISTS_BUT_STATE_MISSING_REQUIRES_REVIEW')
    def test_success_without_state_is_not_success(self):self.assertEqual(self.check([self.runrow(conclusion='success')]),'ATTEMPT_EXISTS_BUT_STATE_MISSING_REQUIRES_REVIEW')
    def test_degraded_today_not_retried(self):
        self.h.update(status='DEGRADED',last_attempt_at='2026-09-23T10:40:00Z');self.assertEqual(self.check(),'FAILED_COLLECTION_REQUIRES_REVIEW')
    def test_pr_does_not_prove_collection(self):self.assertEqual(self.check([self.runrow(event='pull_request')]),'MISSING_DAILY_EXECUTION')
    def test_future_health_fails_closed(self):
        self.h['last_attempt_at']='2027-01-01T00:00:00Z'
        with self.assertRaises(ValueError):self.check()
    def test_invalid_health_fails_closed(self):
        self.h['status']='INVENTED'
        with self.assertRaises(ValueError):self.check()
    def test_future_run_fails_closed(self):
        with self.assertRaises(ValueError):self.check([self.runrow(created_at='2027-01-01T00:00:00Z')])
    def test_naive_clock_rejected(self):
        self.now='2026-09-23T10:45:00'
        with self.assertRaises(ValueError):self.check()
