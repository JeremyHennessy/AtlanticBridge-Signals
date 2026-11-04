from __future__ import annotations

import hashlib
import json
import unittest
from datetime import date, datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from atlanticbridge.sources import bodacc


def _api_row(record_id: str, siren: object, published: str = "2026-11-02") -> dict:
    return {
        "record": {
            "fields": {
                "id": record_id,
                "publicationavis": "A",
                "dateparution": published,
                "familleavis": "mod",
                "familleavis_lib": "Modifications diverses",
                "typeavis": "annonce",
                "typeavis_lib": "Avis initial",
                "registre": siren,
                "url_complete": (
                    "https://www.bodacc.fr/pages/annonces-commerciales-detail/"
                    f"?q.id=id:{record_id}"
                ),
                "listepersonnes": "SHOULD NOT BE RETAINED",
                "listeetablissements": "SHOULD NOT BE RETAINED",
            }
        }
    }


class BODACCCollectorTests(unittest.TestCase):
    def test_build_query_url_is_fixed_bounded_and_date_scoped(self):
        url = bodacc.build_query_url("752461681", "2026-10-01", 20)
        parsed = urlsplit(url)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "bodacc-datadila.opendatasoft.com")
        self.assertEqual(
            parsed.path,
            "/api/explore/v2.0/catalog/datasets/annonces-commerciales/records",
        )
        query = parse_qs(parsed.query)
        self.assertIn("search(registre, \"752461681\")", query["where"][0])
        self.assertIn("dateparution >=", query["where"][0])
        self.assertEqual(query["limit"], ["20"])
        self.assertEqual(query["offset"], ["0"])
        self.assertEqual(query["select"], [",".join(bodacc.API_FIELDS)])

    def test_rejects_invalid_siren_date_and_unbounded_limit(self):
        for bad_siren in ("", "12345678", "1234567890", "12345abc9", "123456789&limit=100", "１２３４５６７８９"):
            with self.subTest(bad_siren=bad_siren), self.assertRaises(ValueError):
                bodacc.build_query_url(bad_siren, "2026-01-01")
        for bad_date in ("2026-1-1", "yesterday", "2026-02-30"):
            with self.subTest(bad_date=bad_date), self.assertRaises(ValueError):
                bodacc.build_query_url("752461681", bad_date)
        for bad_limit in (0, 101, True, "20"):
            with self.subTest(bad_limit=bad_limit), self.assertRaises(ValueError):
                bodacc.build_query_url("752461681", "2026-01-01", bad_limit)

    def test_parses_only_exact_siren_and_minimizes_fields_with_provenance(self):
        payload = {
            "total_count": 3,
            "records": [
                _api_row("A202600000001", ["752461681", "752 461 681"]),
                _api_row("A202600000002", "111222333"),
            ],
        }
        raw = json.dumps(payload).encode("utf-8")
        fetched_at = datetime(2026, 11, 3, 12, tzinfo=timezone.utc)
        with patch.object(
            bodacc,
            "_fetch_payload",
            return_value=(payload, hashlib.sha256(raw).hexdigest()),
        ) as fetch:
            result = bodacc.collect_siren_notices(
                "752461681",
                "2026-10-01",
                limit=10,
                retrieved_at=fetched_at,
            )
        fetch.assert_called_once()
        self.assertEqual(result.response_sha256, hashlib.sha256(raw).hexdigest())
        self.assertEqual(result.records_matching_exact_siren, 1)
        self.assertEqual(result.records_excluded_by_exact_siren_check, 1)
        self.assertTrue(result.api_query_has_more_results)
        self.assertEqual(result.records[0].publication_age_days, 1)
        self.assertEqual(
            result.records[0].publication_freshness,
            "NOTICE_PUBLISHED_WITHIN_90_DAYS",
        )
        output = result.as_dict()
        serialized = json.dumps(output)
        self.assertNotIn("SHOULD NOT BE RETAINED", serialized)
        self.assertNotIn("listepersonnes", serialized)
        self.assertEqual(output["records"][0]["siren"], "752461681")
        self.assertEqual(output["records"][0]["registry_source_type"], "list")
        self.assertEqual(
            output["interpretation_limit"],
            "French corporate notice context only; not evidence of Canadian activity, "
            "Canada-directed expansion, an uncommitted mandate, investment intent, or market fit.",
        )

    def test_no_result_is_not_an_absence_claim_and_large_pages_fail(self):
        payload = {"total_count": 0, "records": []}
        with patch.object(bodacc, "_fetch_payload", return_value=(payload, "a" * 64)):
            result = bodacc.collect_siren_notices(
                "752461681", "2026-10-01", retrieved_at=datetime(2026, 11, 3, tzinfo=timezone.utc)
            )
        self.assertEqual(result.records_matching_exact_siren, 0)
        self.assertIn("NOT_AN_ABSENCE_PROOF", result.coverage)
        with self.assertRaises(ValueError):
            bodacc._parse_records(
                [_api_row("x", "752461681")] * 2,
                siren="752461681",
                retrieved_date=date(2026, 11, 3),
                limit=1,
                since_date=date(2026, 10, 1),
            )
        with patch.object(
            bodacc,
            "_fetch_payload",
            return_value=({"total_count": 0, "records": [_api_row("x", "752461681")]}, "d" * 64),
        ):
            with self.assertRaisesRegex(ValueError, "total_count is smaller"):
                bodacc.collect_siren_notices("752461681", "2026-10-01")


    def test_rejects_records_before_the_requested_date_bound(self):
        old = _api_row("A202600000003", "752461681", published="2026-09-30")
        with patch.object(
            bodacc,
            "_fetch_payload",
            return_value=({"total_count": 1, "records": [old]}, "c" * 64),
        ):
            with self.assertRaisesRegex(ValueError, "before the requested lower date bound"):
                bodacc.collect_siren_notices(
                    "752461681",
                    "2026-10-01",
                    retrieved_at=datetime(2026, 11, 3, tzinfo=timezone.utc),
                )


    def test_registry_identifiers_are_strictly_parsed(self):
        self.assertEqual(
            bodacc._registry_sirens(["752461681", "752 461 681"]),
            {"752461681"},
        )
        self.assertEqual(
            bodacc._registry_sirens("752461681,752 461 681"),
            {"752461681"},
        )
        self.assertEqual(bodacc._registry_sirens(752461681), {"752461681"})
        for bad in ("RCS 752461681", "１２３４５６７８９", ["prefix 752461681"], {"id": "752461681"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                bodacc._registry_sirens(bad)

    def test_notice_urls_reject_credentials_ports_wrong_paths_and_id_mismatch(self):
        record_id = "A202600000001"
        invalid = [
            f"https://user@www.bodacc.fr/pages/annonces-commerciales-detail/?q.id=id:{record_id}",
            f"https://www.bodacc.fr:444/pages/annonces-commerciales-detail/?q.id=id:{record_id}",
            f"https://www.bodacc.fr/untrusted/?q.id=id:{record_id}",
            "https://www.bodacc.fr/pages/annonces-commerciales-detail/?q.id=id:other",
        ]
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValueError):
                bodacc._notice_url(url, record_id)

    def test_redirects_are_never_followed(self):
        handler = bodacc._NoRedirect()
        self.assertIsNone(
            handler.redirect_request(
                None, None, 302, "Found", {}, "https://example.org/redirect"
            )
        )

    def test_schema_drift_and_non_official_notice_urls_fail_closed(self):
        with patch.object(
            bodacc,
            "_fetch_payload",
            return_value=({"total_count": 1, "results": [_api_row("x", "752461681")]}, "a" * 64),
        ):
            with self.assertRaisesRegex(ValueError, "records array"):
                bodacc.collect_siren_notices("752461681", "2026-10-01")
        bad = _api_row("x", "752461681")
        bad["record"]["fields"]["url_complete"] = "https://example.org/not-a-bodacc-record"
        with patch.object(bodacc, "_fetch_payload", return_value=({"total_count": 1, "records": [bad]}, "b" * 64)):
            with self.assertRaisesRegex(ValueError, "canonical official detail URL"):
                bodacc.collect_siren_notices("752461681", "2026-10-01")


if __name__ == "__main__":
    unittest.main()
