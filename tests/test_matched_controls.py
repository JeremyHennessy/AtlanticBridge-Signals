import unittest

from atlanticbridge.db import connect, ingest_cordis_snapshot
from atlanticbridge.matched_controls import build_matched_controls
from atlanticbridge.sources.cordis import CordisParticipationRecord, CordisProjectRecord


def project(project_id: str, title: str, start_date: str = "2019-01-01"):
    return CordisProjectRecord(
        project_id=project_id,
        acronym=project_id,
        status="CLOSED",
        title=title,
        start_date=start_date,
        end_date="2021-12-31",
        total_cost="1000000",
        ec_max_contribution="500000",
        topics="digital software industrial data",
        ec_signature_date="2018-12-01",
        framework_programme="HORIZON",
        master_call="",
        sub_call="",
        funding_scheme="RIA",
        nature="",
        objective="industrial software data platform engineering",
        content_update_date="2026-01-01",
        rcn=project_id,
        grant_doi="",
        keywords="software platform asset maintenance",
        human_validated="",
        legal_basis="",
    )


def participation(
    project_id: str,
    organisation_id: str,
    name: str,
    country: str,
    *,
    activity_type: str = "PRC",
):
    return CordisParticipationRecord(
        project_id=project_id,
        project_acronym=project_id,
        organisation_id=organisation_id,
        vat_number="",
        name=name,
        short_name=name,
        sme="true",
        activity_type=activity_type,
        street="",
        post_code="",
        city="Milan" if country == "IT" else "Toronto",
        country=country,
        nuts_code="",
        geolocation="",
        organization_url="https://example.test/" + organisation_id,
        contact_form="",
        content_update_date="2026-01-01",
        rcn=organisation_id,
        source_order="1",
        role="participant",
        ec_contribution="100000",
        net_ec_contribution="100000",
        total_cost="200000",
        end_of_participation="false",
        active="true",
    )


class MatchedControlTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect(":memory:")
        projects = [
            project("p1", "Industrial software data platform"),
            project("p2", "Digital asset maintenance engineering"),
            project("p3", "Software platform for industry"),
            project("p4", "Industrial data and maintenance"),
        ]
        participations = [
            participation("p1", "it-1", "Alpha Software SRL", "IT"),
            participation("p1", "ca-1", "Canadian University", "CA", activity_type="HES"),
            participation("p2", "it-2", "Beta Digital SRL", "IT"),
            participation("p3", "it-3", "Gamma Engineering SRL", "IT"),
            participation("p4", "it-4", "Excluded Software SRL", "IT"),
        ]
        ingest_cordis_snapshot(
            self.conn,
            projects,
            participations,
            observed_at="2026-09-20T00:00:00+00:00",
        )
        self.conn.execute(
            """
            INSERT INTO investment_canada_notifications (
                record_id, certification_month, notification_type, investor_text,
                investor_name, investor_locality, investor_node_id,
                country_of_ultimate_control, canadian_business_text,
                canadian_businesses_json, canadian_business_node_ids_json,
                is_new_business, is_eu27, source_url, source_bucket, source_page,
                raw_record_hash, record_json, first_observed_at, last_observed_at
            ) VALUES (?, ?, ?, ?, ?, '', '', ?, ?, '[]', '[]', 1, 1, ?, 'e', 1, ?, '{}', ?, ?)
            """,
            (
                "ica-1",
                "2018-01",
                "Notification - new business",
                "Excluded Software SRL",
                "Excluded Software SRL",
                "Italy",
                "Excluded Software Canada",
                "https://example.test/ica",
                "hash",
                "2026-09-20T00:00:00+00:00",
                "2026-09-20T00:00:00+00:00",
            ),
        )
        self.conn.commit()

    def test_country_sector_matching_and_outcome_exclusion(self):
        cases = {
            "cases": [
                {
                    "outcome_record_id": "positive-1",
                    "canadian_business_name": "Antea Canada Inc.",
                    "investor_name": "Antea Canada Inc.",
                    "ultimate_control_country": "Italy",
                    "notification_month": "2019-08",
                }
            ]
        }
        cohorts = {
            "cases": [
                {
                    "outcome_record_id": "positive-1",
                    "cohort": "TRUE_NEW_ENTRY_CANDIDATE",
                }
            ]
        }
        payload = build_matched_controls(
            self.conn,
            cases_payload=cases,
            cohort_payload=cohorts,
            controls_per_case=3,
        )
        self.assertEqual(payload["summary"]["positive_candidates"], 1)
        self.assertEqual(payload["summary"]["controls"], 3)
        self.assertEqual(payload["summary"]["unique_controls"], 3)
        names = {row["control_name"] for row in payload["matches"]}
        self.assertNotIn("Excluded Software SRL", names)
        self.assertEqual({row["country_iso2"] for row in payload["matches"]}, {"IT"})
        self.assertTrue(
            all(row["control_label"] == "NO_OBSERVED_ENTRY_CONTROL" for row in payload["matches"])
        )
        alpha = next(
            row for row in payload["matches"]
            if row["control_name"] == "Alpha Software SRL"
        )
        self.assertTrue(alpha["cordis_canada_shared_project_before_index"])

    def test_invalid_control_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "controls_per_case"):
            build_matched_controls(
                self.conn,
                cases_payload={"cases": []},
                cohort_payload={"cases": []},
                controls_per_case=0,
            )


if __name__ == "__main__":
    unittest.main()
