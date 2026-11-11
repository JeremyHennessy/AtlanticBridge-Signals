"""Offline regressions for unreconciled CanadaBuys notice values."""
from copy import deepcopy
from dataclasses import replace
from datetime import date
import unittest

from atlanticbridge.canadabuys_quality import AMOUNT_STATUS, AMOUNT_WARNING, amount_policy
from atlanticbridge.canadabuys_store import canadabuys_summary, ingest_awards
from atlanticbridge.live_signals import build_canadabuys_live_signals, unavailable_payload
from atlanticbridge.live_signal_scope import apply_commercial_scope
from tests.test_live_signals import award, connect

class NoticeAmountQualityTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        self.addCleanup(self.conn.close)

    def record(self, **kw):
        return award(reference="same-contract", supplier="Example SAS", country="France",
                     publication="2026-09-20", **kw)

    def ingest(self, records):
        ingest_awards(self.conn, records, source_sha256="offline-fixture", source_url="https://example.test/awards.csv",
                      source_bytes=123, observed_at="2026-09-22T12:00:00+00:00")

    def live(self, **kw):
        return build_canadabuys_live_signals(self.conn, as_of_date=date(2026, 9, 22), **kw)

    def assertWithheld(self, summary, field="cad_contract_amount"):
        self.assertIsNone(summary[field])
        self.assertEqual(summary["amount_aggregation_status"], AMOUNT_STATUS)
        self.assertIn("do not sum raw notice or history rows", summary["amount_aggregation_reason"])

    def test_initial_and_administrative_amendment_are_not_added(self):
        initial = self.record(amount="100000.00", amendment="000")
        amendment = replace(initial, amendment_number="001", amendment_type="Administrative",
                            amendment_date="2026-09-21", raw_json='{"note":"administrative correction"}')
        self.ingest([initial, amendment])
        before = [tuple(r) for r in self.conn.execute("SELECT * FROM canadabuys_awards ORDER BY record_id")]
        live = self.live()
        self.assertWithheld(live["summary"])
        self.assertEqual(live["summary"]["signal_count"], 2)
        self.assertEqual({s["contract_amount"] for s in live["signals"]}, {"100000.00"})
        self.assertEqual({s["total_contract_value"] for s in live["signals"]}, {"100000.00"})
        summary = canadabuys_summary(self.conn)
        self.assertEqual(summary["eu27_suppliers"][0]["award_records"], 2)
        self.assertWithheld(summary["eu27_suppliers"][0], "contract_amount_cad")
        self.assertEqual(before, [tuple(r) for r in self.conn.execute("SELECT * FROM canadabuys_awards ORDER BY record_id")])

    def test_no_snapshot_and_browser_style_unavailable_are_unknown_not_zero(self):
        self.assertWithheld(self.live()["summary"])
        self.assertWithheld(unavailable_payload(reason="source unavailable")["summary"])
        self.assertEqual(canadabuys_summary(self.conn)["amount_aggregation_status"], AMOUNT_STATUS)

    def test_non_cad_supplier_does_not_look_like_zero_cad(self):
        self.ingest([self.record(amount="2000", currency="EUR")])
        self.assertWithheld(canadabuys_summary(self.conn)["eu27_suppliers"][0], "contract_amount_cad")
        p = self.live()
        self.assertWithheld(p["summary"])
        self.assertEqual((p["signals"][0]["contract_amount"], p["signals"][0]["contract_currency"]), ("2000", "EUR"))

    def test_actual_zero_and_uninterpreted_source_values_are_preserved(self):
        for amount in ["0", "", "not stated", "1,000.00"]:
            with self.subTest(amount=amount):
                self.ingest([self.record(amount=amount)])
                p = self.live()
                self.assertWithheld(p["summary"])
                self.assertEqual(p["signals"][0]["contract_amount"], amount)

    def test_empty_lookback_withholds_amount_without_zero_spend_claim(self):
        self.ingest([replace(self.record(), publication_date="2025-01-01")])
        p = self.live(lookback_days=30)
        self.assertEqual(p["signals"], [])
        self.assertWithheld(p["summary"])

    def test_legacy_payload_scope_adds_warning_without_mutating_input(self):
        self.ingest([self.record()])
        legacy = self.live()
        legacy["summary"] = {"cad_contract_amount": "999999"}
        for s in legacy["signals"]:
            for k in ["amount_warning", "amount_interpretation", "evidence_role"]:
                s.pop(k)
        before = deepcopy(legacy)
        scoped = apply_commercial_scope(legacy)
        self.assertWithheld(scoped["summary"])
        self.assertIn(AMOUNT_WARNING, scoped["signals"][0]["why_surfaced"])
        self.assertEqual(scoped["signals"][0]["amount_warning"], AMOUNT_WARNING)
        self.assertEqual(scoped["signals"][0]["evidence_role"], "COMMERCIAL_RESEARCH_SIGNAL")
        self.assertEqual(legacy, before)

    def test_scope_ledger_preserves_warning_when_all_rows_are_excluded_or_held(self):
        self.ingest([self.record()])
        for field, value, ledger in [("title", "Department of National Defence", "excluded_signals"),
                                     ("regions_of_delivery", "*Europe *Remote Offsite", "review_required_signals")]:
            with self.subTest(ledger=ledger):
                p = self.live()
                p["signals"][0][field] = value
                out = apply_commercial_scope(p)
                self.assertEqual(out["signals"], [])
                self.assertWithheld(out["summary"])
                row = out["scope_audit"][ledger][0]
                self.assertEqual(row["amount_warning"], AMOUNT_WARNING)
                self.assertEqual(row["contract_amount"], "1000")

    def test_unavailable_old_summary_cannot_reintroduce_zero(self):
        old = {"status": "UNAVAILABLE", "summary": {"cad_contract_amount": "0"}, "signals": []}
        self.assertWithheld(apply_commercial_scope(old)["summary"])
        self.assertEqual(old["summary"]["cad_contract_amount"], "0")

    def test_history_notice_has_explicit_dataset_scope(self):
        policy = amount_policy()
        self.assertEqual(policy["source_history_notice_scope"], "CANADABUYS_CONTRACT_HISTORY_NOT_AWARD_NOTICE_FEED")
        self.assertIn("does not establish that the award-notice feed was affected", policy["source_history_warning"])
        self.assertIn("does not establish cancellation", policy["source_history_warning"])
        self.assertTrue(policy["source_history_notice_url"].endswith("COsoutien-CHsupport-eng.html"))
        policy["amount_aggregation_status"] = "edited"
        self.assertEqual(amount_policy()["amount_aggregation_status"], AMOUNT_STATUS)

if __name__ == "__main__":
    unittest.main()
