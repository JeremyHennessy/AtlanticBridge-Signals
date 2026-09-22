from __future__ import annotations

from datetime import date
import unittest

from atlanticbridge.canadabuys_store import ingest_awards
from atlanticbridge.db import connect
from atlanticbridge.live_signals import build_canadabuys_live_signals
from atlanticbridge.sources.canadabuys import CanadaBuysAwardRecord


def award(
    *,
    reference: str,
    supplier: str,
    country: str,
    publication: str,
    amount: str = "1000",
    currency: str = "CAD",
    amendment: str = "",
    amendment_date: str = "",
) -> CanadaBuysAwardRecord:
    return CanadaBuysAwardRecord(
        title=f"Award {reference}",
        reference_number=reference,
        amendment_number=amendment,
        solicitation_number=f"S-{reference}",
        contract_number=f"C-{reference}",
        publication_date=publication,
        contract_award_date=publication,
        amendment_date=amendment_date,
        contract_start_date=publication,
        contract_end_date="2027-03-31",
        contract_amount=amount,
        total_contract_value=amount,
        contract_currency=currency,
        award_status="Active",
        instrument_type="Contract",
        amendment_type="",
        gsin="",
        gsin_description="",
        unspsc="",
        unspsc_description="",
        procurement_category="Services",
        notice_type="Award Notice",
        procurement_method="Competitive",
        selection_criteria="",
        limited_tendering_reason="",
        trade_agreements="",
        regions_of_delivery="Canada",
        supplier_legal_name=supplier,
        supplier_address_line="1 Main St",
        supplier_city="Paris",
        supplier_province="",
        supplier_postal_code="",
        supplier_country_raw=country,
        supplier_country=country,
        contracting_entity_name="Public Services and Procurement Canada",
        contracting_entity_city="Ottawa",
        contracting_entity_province="Ontario",
        award_description="Official federal award",
        raw_json=f'{{"reference":"{reference}"}}',
        source_url="https://canadabuys.canada.ca/opendata/example.csv",
    )


class LiveSignalsTests(unittest.TestCase):
    def test_no_snapshot_is_unavailable_not_zero_evidence(self):
        conn = connect(":memory:")
        payload = build_canadabuys_live_signals(
            conn,
            as_of_date=date(2026, 9, 22),
            lookback_days=90,
        )
        self.assertEqual(payload["status"], "UNAVAILABLE")
        self.assertIn("No CanadaBuys snapshot", payload["reason"])

    def test_current_eu_awards_become_source_confirmed_signals(self):
        conn = connect(":memory:")
        records = [
            award(
                reference="EU-1",
                supplier="Example France SAS",
                country="France",
                publication="2026-09-20",
                amount="125000.50",
            ),
            award(
                reference="EU-2",
                supplier="Example Germany GmbH",
                country="Germany",
                publication="2026-05-01",
            ),
            award(
                reference="US-1",
                supplier="Example USA Inc",
                country="United States",
                publication="2026-09-21",
            ),
        ]
        ingest_awards(
            conn,
            records,
            source_sha256="sha-current",
            source_url="https://canadabuys.canada.ca/opendata/example.csv",
            source_bytes=123,
            observed_at="2026-09-22T12:00:00+00:00",
        )

        payload = build_canadabuys_live_signals(
            conn,
            as_of_date=date(2026, 9, 22),
            lookback_days=90,
        )
        self.assertEqual(payload["status"], "ACTIVE")
        self.assertEqual(payload["summary"]["signal_count"], 1)
        self.assertEqual(payload["summary"]["company_count"], 1)
        self.assertEqual(payload["summary"]["country_count"], 1)
        self.assertEqual(payload["summary"]["cad_contract_amount"], "125000.50")
        signal = payload["signals"][0]
        self.assertEqual(signal["company_name"], "Example France SAS")
        self.assertEqual(signal["country"], "France")
        self.assertEqual(signal["signal_family"], "CANADABUYS_AWARD")
        self.assertEqual(signal["signal_stage"], "ACTIVE_CANADIAN_COMMERCIAL_EVIDENCE")
        self.assertEqual(signal["source_confidence"], "SOURCE_CONFIRMED")
        self.assertEqual(signal["recency_days"], 2)
        self.assertIn("not proof of first market entry", signal["why_surfaced"])

    def test_amendment_date_is_the_public_availability_clock(self):
        conn = connect(":memory:")
        ingest_awards(
            conn,
            [
                award(
                    reference="EU-3",
                    supplier="Example Italy S.p.A.",
                    country="Italy",
                    publication="2026-04-01",
                    amendment="1",
                    amendment_date="2026-09-21",
                )
            ],
            source_sha256="sha-current",
            source_url="https://canadabuys.canada.ca/opendata/example.csv",
            source_bytes=123,
            observed_at="2026-09-22T12:00:00+00:00",
        )
        payload = build_canadabuys_live_signals(
            conn,
            as_of_date=date(2026, 9, 22),
            lookback_days=30,
        )
        self.assertEqual(payload["summary"]["signal_count"], 1)
        signal = payload["signals"][0]
        self.assertEqual(signal["signal_kind"], "FEDERAL_AWARD_AMENDED")
        self.assertEqual(signal["publicly_available_date"], "2026-09-21")
        self.assertEqual(signal["recency_days"], 1)

    def test_company_id_is_stable_across_multiple_awards(self):
        conn = connect(":memory:")
        ingest_awards(
            conn,
            [
                award(
                    reference="EU-4",
                    supplier="Stable GmbH",
                    country="Germany",
                    publication="2026-09-20",
                ),
                award(
                    reference="EU-5",
                    supplier="Stable GmbH",
                    country="Germany",
                    publication="2026-09-19",
                ),
            ],
            source_sha256="sha-current",
            source_url="https://canadabuys.canada.ca/opendata/example.csv",
            source_bytes=123,
            observed_at="2026-09-22T12:00:00+00:00",
        )
        payload = build_canadabuys_live_signals(
            conn,
            as_of_date=date(2026, 9, 22),
            lookback_days=30,
        )
        self.assertEqual(payload["summary"]["signal_count"], 2)
        self.assertEqual(payload["summary"]["company_count"], 1)
        self.assertEqual(
            len({signal["company_id"] for signal in payload["signals"]}),
            1,
        )


if __name__ == "__main__":
    unittest.main()
