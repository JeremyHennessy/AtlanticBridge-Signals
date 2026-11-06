import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import plan_evidence_backfill as p
import archive_evidence as a


class BackfillPlanTests(unittest.TestCase):
    def inventory(self, **fields):
        return {'schema_version': 1, 'observations': [
            {'artifact_id': next(iter(a.PINS)), **fields}]}

    def test_no_inputs_is_seven_uncertain_pins_without_network(self):
        with patch.object(a.Client, '__init__', side_effect=AssertionError('No client allowed')):
            result = p.plan()
        self.assertEqual(result['counts'], {'uncertain': 7})
        self.assertEqual({row['artifact_id']: row['expected_sha256'] for row in result['items']}, a.PINS)
        self.assertEqual(result['current_remote_availability'], 'not_checked')

    def test_metadata_never_establishes_available_bytes(self):
        result = p.plan(self.inventory(http_status=200, expired=False))
        self.assertEqual(result['items'][0]['status'], 'metadata_only_not_byte_verified')
        self.assertEqual(result['items'][0]['next_step'], 'manual_review_before_any_backfill')

    def test_api_errors_and_omissions_are_uncertain(self):
        for status in (None, 401, 403, 429, 500, 502):
            with self.subTest(status=status):
                result = p.plan(self.inventory(http_status=status, expired=True))
                self.assertEqual(result['counts'], {'uncertain': 7})
        self.assertEqual(p.plan({'schema_version': 1, 'observations': []})['counts'], {'uncertain': 7})

    def test_expired_and_unavailable_are_only_supplied_observations(self):
        for status, expired, expected in [(200, True, 'observed_expired'),
                                          (404, None, 'observed_unavailable'),
                                          (410, None, 'observed_unavailable')]:
            result = p.plan(self.inventory(http_status=status, expired=expired))
            self.assertEqual(result['items'][0]['status'], expected)
            self.assertEqual(result['current_remote_availability'], 'not_checked')

    def test_inventory_ignores_secrets_and_does_not_echo_unknown_fields(self):
        result = p.plan(self.inventory(http_status=403, error='SECRET RESPONSE',
                                      download_url='https://example.org/?token=SECRET'))
        self.assertNotIn('SECRET', json.dumps(result))
        self.assertNotIn('example.org', json.dumps(result))

    def test_invalid_inventory_rejected_without_values(self):
        for value in ([], {}, {'schema_version': 1, 'observations': ['SECRET']},
                      self.inventory(http_status=True), self.inventory(expired='SECRET'),
                      {'schema_version': 1, 'observations': [{'artifact_id': 'SECRET'}]}):
            with self.subTest(value=value), self.assertRaises(ValueError) as caught:
                p.plan(value)
            self.assertNotIn('SECRET', str(caught.exception))
        value = self.inventory(http_status=200)
        value['observations'] *= 2
        with self.assertRaises(ValueError):
            p.plan(value)

    def test_local_copy_verified_against_pin_and_inner_raw_hash(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            archive.writestr('raw/' + hashlib.sha256(b'evidence').hexdigest() + '.bin', b'evidence')
        raw = out.getvalue()
        with tempfile.TemporaryDirectory() as tmp, patch.object(p, 'PINS', {1: hashlib.sha256(raw).hexdigest()}):
            path = Path(tmp) / 'retained.zip'
            path.write_bytes(raw)
            result = p.plan({'schema_version': 1, 'observations': [{'artifact_id': 1, 'http_status': 410}]}, {1: path})
            self.assertEqual(result['counts'], {'verified_retained': 1})
            self.assertEqual(result['items'][0]['source_observation'], 'observed_unavailable')
            self.assertNotIn(str(path), json.dumps(result))
            path.write_bytes(b'tampered')
            self.assertEqual(p.plan(retained={1: path})['counts'], {'needs_manual_review': 1})

    def test_matching_zip_hash_does_not_hide_invalid_inner_evidence(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, 'w') as archive:
            archive.writestr('raw/' + '0' * 64 + '.bin', b'tampered')
        raw = out.getvalue()
        with patch.object(p, 'PINS', {1: hashlib.sha256(raw).hexdigest()}), patch.object(p, 'read_bounded', return_value=raw):
            self.assertEqual(p.plan(retained={1: 'unused'})['counts'], {'needs_manual_review': 1})

    def test_missing_local_copy_does_not_claim_remote_absence(self):
        with patch.object(p, 'read_bounded', side_effect=FileNotFoundError('SECRET PATH')):
            result = p.plan(retained={next(iter(a.PINS)): 'unused'})
        self.assertEqual(result['items'][0]['status'], 'missing_local_copy')
        self.assertEqual(result['items'][0]['source_observation'], 'uncertain')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_unknown_retained_id_rejected(self):
        with self.assertRaises(ValueError):
            p.plan(retained={123: 'SECRET PATH'})

    def test_cli_errors_are_redacted_and_nonzero(self):
        for args in (['--retained', 'SECRET'], ['--retained', '1=SECRET'],
                     ['--inventory', 'SECRET-MISSING-PATH']):
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(p.main(args), 2)
            self.assertEqual(stdout.getvalue(), '')
            self.assertNotIn('SECRET', stderr.getvalue())

    def test_cli_emits_deterministic_plan_and_bounded_reader(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            self.assertEqual(p.main([]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), p.plan())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'input'
            path.write_bytes(b'12345')
            self.assertEqual(p.read_bounded(path, 5), b'12345')
            with self.assertRaises(ValueError):
                p.read_bounded(path, 4)

    def test_schema_and_retained_container_types_are_strict(self):
        with self.assertRaises(ValueError):
            p.plan({"schema_version":True,"observations":[]})
        for value in ([],[1],"",False,0,1):
            with self.subTest(value=value),self.assertRaises(ValueError):
                p.plan(retained=value)
