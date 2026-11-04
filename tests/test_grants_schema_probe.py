import unittest

from scripts.probe_grants_schema import DATASET_ID, probe_schema


class GrantsSchemaProbeTests(unittest.TestCase):
    def test_reads_metadata_and_schema_without_rows(self):
        calls = []

        def fake(action, params):
            calls.append((action, dict(params)))
            if action == "package_show":
                return {"success": True, "result": {
                    "id": DATASET_ID,
                    "resources": [{"id": "resource-1", "name": "grants.csv",
                                   "format": "CSV", "datastore_active": True},
                                  {"id": "resource-2", "name": "readme.txt",
                                   "format": "TXT", "datastore_active": False}],
                }}
            return {"success": True, "result": {
                "total": 1234, "records": [],
                "fields": [{"id": "recipient_en", "type": "text"},
                           {"id": "agreement_value", "type": "numeric"}],
            }}

        result = probe_schema(fake)
        self.assertEqual(result["dataset_id"], DATASET_ID)
        self.assertEqual(result["resources"][0]["records_returned"], 0)
        self.assertEqual(result["resources"][0]["row_count"], 1234)
        self.assertEqual([name for name, _ in calls],
                         ["package_show", "datastore_search"])
        self.assertEqual(calls[1][1], {"resource_id": "resource-1", "limit": "0"})

    def test_rejects_datastore_rows_in_schema_only_probe(self):
        def fake(action, params):
            if action == "package_show":
                return {"success": True, "result": {
                    "id": DATASET_ID,
                    "resources": [{"id": "resource-1", "format": "CSV",
                                   "datastore_active": True}],
                }}
            return {"success": True, "result": {
                "total": 1, "records": [{"recipient_en": "sample"}],
                "fields": [{"id": "recipient_en", "type": "text"}],
            }}

        with self.assertRaisesRegex(ValueError, "unexpectedly returned data rows"):
            probe_schema(fake)

    def test_fails_closed_when_no_active_csv_datastore_exists(self):
        def fake(action, params):
            return {"success": True, "result": {
                "id": DATASET_ID,
                "resources": [{"id": "resource-1", "format": "CSV",
                               "datastore_active": False}],
            }}

        with self.assertRaisesRegex(ValueError, "No active CSV datastore"):
            probe_schema(fake)


if __name__ == "__main__":
    unittest.main()
