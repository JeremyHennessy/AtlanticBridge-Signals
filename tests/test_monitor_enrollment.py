import copy
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from run_company_monitor import reviewed_additions
from atlanticbridge.company_sources import VERSION,digest

OLD={'id':'old','kind':'article','company':'Old','url':'https://example.org/old'}
NEW={'id':'new','kind':'article','company':'New','url':'https://example.org/new'}

def approval(source=NEW):
    return {'id':source['id'],'proof_artifact_id':123,
            'proof_archive_sha256':'a'*64,
            'source_contract_sha256':digest({'parser_version':VERSION,'source':source})}

def manifest(sources=None, approvals=None):
    return {'sources':sources or [OLD,NEW],
            'enrollment':{'policy':'ADDITIVE_BASELINE_NO_EVENTS',
                          'approved_additions':approvals if approvals is not None else [approval()]}}

class MonitorEnrollmentTests(unittest.TestCase):
    def test_exact_reviewed_addition_is_accepted(self):
        self.assertEqual(reviewed_additions(manifest(),{'old'}),{'new'})

    def test_unchanged_source_set_needs_no_enrollment_block(self):
        self.assertEqual(reviewed_additions({'sources':[OLD]}, {'old'}),set())

    def test_source_removal_is_never_silent(self):
        with self.assertRaisesRegex(ValueError,'Source removal'):
            reviewed_additions({'sources':[NEW]}, {'old','new'})

    def test_new_source_without_exact_approval_is_rejected(self):
        with self.assertRaises(ValueError):
            reviewed_additions({'sources':[OLD,NEW]}, {'old'})

    def test_contract_change_invalidates_approval(self):
        changed=dict(NEW,url='https://example.org/changed')
        with self.assertRaisesRegex(ValueError,'contract'):
            reviewed_additions(manifest([OLD,changed],[approval(NEW)]), {'old'})

    def test_proof_hash_and_artifact_are_structured(self):
        bad=approval();bad['proof_archive_sha256']='bad'
        with self.assertRaisesRegex(ValueError,'proof hash'):
            reviewed_additions(manifest(approvals=[bad]), {'old'})
        bad=approval();bad['proof_artifact_id']=0
        with self.assertRaisesRegex(ValueError,'artifact id'):
            reviewed_additions(manifest(approvals=[bad]), {'old'})

    def test_approval_cannot_cover_existing_or_duplicate_source(self):
        extra=approval();extra['id']='old'
        with self.assertRaises(ValueError):
            reviewed_additions(manifest(approvals=[extra]), {'old'})

if __name__=='__main__':
    unittest.main()
