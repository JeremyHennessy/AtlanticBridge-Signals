import unittest

from scripts.probe_ns_awarded_tenders import DATASET_ID, probe_metadata


class NovaScotiaTendersSchemaProbeTests(unittest.TestCase):
    def metadata(self):
        return {
            "id": DATASET_ID,
            "name": "Awarded Public Tenders",
            "licenseId": "nova-scotia-open-government-licence",
            "attribution": "Government of Nova Scotia",
            "rowsUpdatedAt": 1792454400,
            "columns": [
                {"fieldName": "tender_id", "name": "Tender ID", "dataTypeName": "text"},
                {"fieldName": "awarded_date", "name": "Awarded Date", "dataTypeName": "calendar_date"},
            ],
        }

    def test_reports_verified_metadata_without_record_data(self):
        result = probe_metadata(lambda: self.metadata())
        self.assertEqual(result["dataset_id"], DATASET_ID)
        self.assertEqual(result["license_id"], "nova-scotia-open-government-licence")
        self.assertEqual(result["attribution"], "Government of Nova Scotia")
        self.assertEqual(result["records_requested"], 0)
        self.assertEqual([item["field_name"] for item in result["columns"]],
                         ["tender_id", "awarded_date"])

    def test_rejects_wrong_dataset_missing_schema_and_duplicate_fields(self):
        wrong = self.metadata()
        wrong["id"] = "other-id"
        with self.assertRaisesRegex(ValueError, "ID"):
            probe_metadata(lambda: wrong)

        missing = self.metadata()
        missing["columns"] = []
        with self.assertRaisesRegex(ValueError, "no columns"):
            probe_metadata(lambda: missing)

        duplicate = self.metadata()
        duplicate["columns"].append(dict(duplicate["columns"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate fields"):
            probe_metadata(lambda: duplicate)


if __name__ == "__main__":
    unittest.main()
