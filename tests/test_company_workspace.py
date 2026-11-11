"""Company identity migration/persistence without network, server or source writes."""
from concurrent.futures import ThreadPoolExecutor
import copy
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from atlanticbridge.automation import company_workspace as W
from atlanticbridge.automation.store import Conflict, Store
from atlanticbridge.automation.models import canonical, timestamp

FIXTURE = Path(__file__).parent/'fixtures/company_workspace/browser-export.json'
NOW = '2026-11-06T13:00:00Z'
LATER = '2026-11-07T13:00:00Z'


class CompanyWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.db=self.root/'private.sqlite'
        self.backup=json.loads(FIXTURE.read_text())
        W.initialize(self.db)

    def apply(self, backup=None, **kwargs):
        backup=self.backup if backup is None else backup
        plan=W.plan_import(self.db,backup)
        return W.import_backup(self.db,backup,expected_state=plan['state_token'],
            expected_backup=plan['backup_token'],actor='test',at=NOW,**kwargs)

    def summary(self):
        with W.snapshot(self.db) as db:
            return W._verify(db)

    def fields(self, **kwargs):
        return dict(status='researching',notes='Persisted analyst edit',next_action='Review later',due_date='',**kwargs)

    def test_actual_browser_backup_roundtrip_all_statuses_unicode_and_exact_ids(self):
        result=self.apply()
        self.assertEqual(result['added'],5)
        self.assertEqual(W.export_backup(self.db,at=LATER)['entries'],self.backup['entries'])
        self.assertEqual({r['entry']['status'] for r in W.entries(self.db)},W.STATUSES)
        self.assertEqual(len(W.entries(self.db)),5)  # same company name, five distinct identities
        self.assertFalse(result['evidence_verified']); self.assertFalse(result['identity_mapping_performed'])

    def test_plan_is_readonly_and_contains_no_private_fields(self):
        before=self.db.read_bytes()
        plan=W.plan_import(self.db,self.backup)
        self.assertEqual(self.db.read_bytes(),before)
        self.assertEqual(plan['new'],5)
        self.assertNotIn('Private invented note',json.dumps(plan))
        self.assertNotIn('company_name',json.dumps(plan))

    def test_repeat_import_and_reordered_backup_are_noops(self):
        self.apply(); before=self.summary()
        backup=copy.deepcopy(self.backup); backup['entries'].reverse();backup['exported_at']=LATER
        result=self.apply(backup)
        self.assertEqual(result['added'],0)
        self.assertEqual(self.summary(),before)

    def test_conflict_is_atomic_even_with_new_company(self):
        self.apply(); before=self.summary()
        changed=copy.deepcopy(self.backup)
        changed['entries'][0]['notes']='Older exported draft'
        added=copy.deepcopy(changed['entries'][1]);added['id']='f'*64;changed['entries'].append(added)
        self.assertEqual(W.plan_import(self.db,changed)['conflicting_company_ids'],['a'*64])
        with self.assertRaises(Conflict):self.apply(changed)
        self.assertEqual(self.summary(),before)

    def test_state_and_selected_backup_are_both_pinned(self):
        plan=W.plan_import(self.db,self.backup)
        changed=copy.deepcopy(self.backup);changed['entries'][0]['notes']='Changed since review'
        with self.assertRaises(Conflict):
            W.import_backup(self.db,changed,expected_state=plan['state_token'],expected_backup=plan['backup_token'],actor='test',at=NOW)
        self.apply()
        with self.assertRaises(Conflict):
            W.import_backup(self.db,self.backup,expected_state=plan['state_token'],expected_backup=plan['backup_token'],actor='test',at=NOW)

    def test_analyst_save_persists_and_keeps_source_metadata(self):
        self.apply(); before=self.backup['entries'][0]
        saved=W.save(self.db,'a'*64,expected_revision=1,fields=self.fields(),actor='reviewer',at=LATER)
        self.assertEqual(saved['revision'],2)
        reopened=W.entries(self.db)[0]
        self.assertEqual(reopened,saved)
        for key in set(before)-W.EDIT_FIELDS-{'updated_at'}:
            self.assertEqual(reopened['entry'][key],before[key])
        self.assertEqual(reopened['entry']['updated_at'],timestamp(LATER))

    def test_stale_revision_and_unknown_company_fail(self):
        self.apply()
        W.save(self.db,'a'*64,expected_revision=1,fields=self.fields(),actor='reviewer',at=LATER)
        for company in ('a'*64,'f'*64):
            with self.assertRaises(Conflict):W.save(self.db,company,expected_revision=1,fields=self.fields(),actor='reviewer',at=LATER)
        self.assertEqual(self.summary()['history'],6)

    def test_concurrent_edits_exactly_one_commits(self):
        self.apply()
        def save(note):
            fields=self.fields();fields['notes']=note
            try:return W.save(self.db,'a'*64,expected_revision=1,fields=fields,actor='test',at=LATER)
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(save,['first','second']))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.summary()['history'],6)

    def test_concurrent_imports_with_one_reviewed_state_do_not_race(self):
        plan=W.plan_import(self.db,self.backup)
        def apply(_):
            try:return W.import_backup(self.db,self.backup,expected_state=plan['state_token'],expected_backup=plan['backup_token'],actor='test',at=NOW)
            except Conflict:return None
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(apply,range(2)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.summary()['history'],5)

    def test_noop_text_edit_still_advances_revision_and_state_token(self):
        self.apply();before=self.summary()
        original=self.backup['entries'][0]
        fields={key:original[key] for key in W.EDIT_FIELDS}
        W.save(self.db,'a'*64,expected_revision=1,fields=fields,actor='test',at=LATER)
        self.assertNotEqual(self.summary()['state_token'],before['state_token'])

    def test_interrupted_import_rolls_back_entire_batch(self):
        original=W._audit;calls=[]
        def fail(*args,**kwargs):
            original(*args,**kwargs);calls.append(1)
            if len(calls)==2:raise RuntimeError('simulated interruption')
        with patch.object(W,'_audit',side_effect=fail),self.assertRaises(RuntimeError):self.apply()
        self.assertEqual(self.summary()['entries'],0);self.assertEqual(self.summary()['history'],0)

    def test_save_commit_without_received_result_is_recovered_by_revision(self):
        self.apply()
        # A caller can lose its response after commit. Stale retry cannot overwrite.
        W.save(self.db,'a'*64,expected_revision=1,fields=self.fields(),actor='test',at=LATER)
        with self.assertRaises(Conflict):W.save(self.db,'a'*64,expected_revision=1,fields=self.fields(),actor='test',at=LATER)
        self.assertEqual(W.entries(self.db)[0]['entry']['notes'],'Persisted analyst edit')

    def test_no_silent_identity_status_mapping_or_source_metadata_edit(self):
        self.apply()
        for extra in ({'company_id':'f'*64},{'id':'f'*64},{'source_sha256':'0'*64},{'company_name':'other'}):
            fields={**self.fields(),**extra}
            with self.assertRaises(ValueError):W.save(self.db,'a'*64,expected_revision=1,fields=fields,actor='test',at=LATER)
        for status in ('TRIAGE','ACTIVE','HOLD','DONE'):
            fields=self.fields();fields['status']=status
            with self.assertRaises(ValueError):W.save(self.db,'a'*64,expected_revision=1,fields=fields,actor='test',at=LATER)

    def test_backdated_save_fails_and_preserves_current(self):
        self.apply();before=self.summary()
        with self.assertRaises(ValueError):W.save(self.db,'a'*64,expected_revision=1,fields=self.fields(),actor='test',at='2026-11-01T00:00:00Z')
        self.assertEqual(self.summary(),before)

    def test_unknown_fields_rejected_instead_of_discarded(self):
        for scope in ('top','entry'):
            value=copy.deepcopy(self.backup)
            (value if scope=='top' else value['entries'][0])['unrecognized_notes']='Must not lose me'
            with self.assertRaises(ValueError):self.apply(value)
        self.assertEqual(self.summary()['entries'],0)

    def test_oversize_utf16_bounds_and_surrogates(self):
        for notes in ('x'*4001,'🦞'*2001,'\ud800'):
            value=copy.deepcopy(self.backup);value['entries'][0]['notes']=notes
            with self.assertRaises((ValueError,UnicodeError)):self.apply(value)
        value=copy.deepcopy(self.backup);value['entries'][0]['notes']='🦞'*2000
        self.apply(value)
        self.assertEqual(W.entries(self.db)[0]['entry']['notes'],'🦞'*2000)

    def test_duplicate_keys_ids_and_nonfinite_are_rejected(self):
        raw=FIXTURE.read_text().replace('"schema_version": 1','"schema_version": 1, "schema_version": 1')
        with self.assertRaises(ValueError):self.apply(raw)
        raw=FIXTURE.read_text().replace('"schema_version": 1','"schema_version": NaN')
        with self.assertRaises(ValueError):self.apply(raw)
        value=copy.deepcopy(self.backup);value['entries'].append(value['entries'][0])
        with self.assertRaises(ValueError):self.apply(value)

    def test_invalid_dates_urls_hashes_and_types_rejected(self):
        mutations={'id':'A'*64,'status':'constructor','due_date':'2026-02-30','latest_public_date':'2026-02-30',
            'updated_at':'2026-11-06','snapshot_observed_at':'not-a-date','source_url':'javascript:alert(1)',
            'source_sha256':'xyz','notes':False}
        for key,value in mutations.items():
            candidate=copy.deepcopy(self.backup);candidate['entries'][0][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.apply(candidate)
        for version in (True,'1',2):
            candidate=copy.deepcopy(self.backup);candidate['schema_version']=version
            with self.assertRaises(ValueError):self.apply(candidate)

    def test_invalid_timezone_offsets_rejected_before_roundtrip(self):
        for offset in ('+00:60','-01:99','+24:00','+1:00'):
            for field in ('updated_at','snapshot_observed_at','exported_at'):
                candidate=copy.deepcopy(self.backup)
                target=candidate if field=='exported_at' else candidate['entries'][0]
                target[field]='2026-11-06T13:00:00'+offset
                with self.subTest(offset=offset,field=field),self.assertRaises(ValueError):self.apply(candidate)

    def test_byte_and_count_limits(self):
        with self.assertRaises(ValueError):W.validate_backup(b' '* (W.MAX_BYTES+1))
        candidate=copy.deepcopy(self.backup)
        candidate['entries']=[{**candidate['entries'][0],'id':format(i,'064x')} for i in range(501)]
        with self.assertRaises(ValueError):self.apply(candidate)

    def test_combined_capacity_rejected_before_insert(self):
        candidate=copy.deepcopy(self.backup)
        candidate['entries']=[{**candidate['entries'][0],'id':format(i,'064x')} for i in range(500)]
        self.apply(candidate)
        extra=copy.deepcopy(self.backup);extra['entries']=extra['entries'][:1]
        self.assertTrue(W.plan_import(self.db,extra)['capacity_exceeded'])
        with self.assertRaises(Conflict):self.apply(extra)
        self.assertEqual(self.summary()['entries'],500)

    def test_combined_bytes_preserve_browser_export_capacity(self):
        candidate=copy.deepcopy(self.backup)
        seed={**candidate['entries'][0],'notes':'x'*4000,'company_name':'c'*1000,'source_url':'https://example.org/'+'u'*1900}
        candidate['entries']=[{**seed,'id':format(i,'064x')} for i in range(200)]
        self.apply(candidate)
        second={**candidate,'entries':[{**seed,'id':format(i,'064x')} for i in range(200,400)]}
        self.assertTrue(W.plan_import(self.db,second)['capacity_exceeded'])
        with self.assertRaises(Conflict):self.apply(second)
        self.assertEqual(len(W.export_backup(self.db,at=LATER)['entries']),200)

    def test_existing_or_missing_database_never_overwritten_or_created(self):
        original=self.db.read_bytes()
        with self.assertRaises(FileExistsError):W.initialize(self.db)
        self.assertEqual(self.db.read_bytes(),original)
        missing=self.root/'missing.sqlite'
        with self.assertRaises(FileNotFoundError):W.plan_import(missing,self.backup)
        self.assertFalse(missing.exists())
        with self.assertRaises(FileNotFoundError):W.import_backup(missing,self.backup,expected_state='a'*64,expected_backup='b'*64,actor='test',at=NOW)
        self.assertFalse(missing.exists())

    def test_rejects_evidence_foundation_database(self):
        evidence=self.root/'foundation.sqlite'
        with Store(evidence):pass
        before=evidence.read_bytes()
        with self.assertRaises(ValueError):W.plan_import(evidence,self.backup)
        self.assertEqual(evidence.read_bytes(),before)

    def test_private_files_symlinks_hardlinks_and_sidecars(self):
        self.assertEqual(self.db.stat().st_mode & 0o777,0o600)
        self.db.chmod(0o644)
        with self.assertRaises(ValueError):W.plan_import(self.db,self.backup)
        self.db.chmod(0o600)
        link=self.root/'link.sqlite';link.symlink_to(self.db)
        with self.assertRaises(ValueError):W.plan_import(link,self.backup)
        link.unlink();os.link(self.db,link)
        with self.assertRaises(ValueError):W.plan_import(self.db,self.backup)
        link.unlink();sidecar=Path(str(self.db)+'-wal');sidecar.write_bytes(b'unsafe');sidecar.chmod(0o644)
        with self.assertRaises(ValueError):W.plan_import(self.db,self.backup)

    def test_init_refuses_orphan_sidecar(self):
        missing=self.root/'new.sqlite';sidecar=Path(str(missing)+'-wal');sidecar.write_bytes(b'leave intact')
        with self.assertRaises(FileExistsError):W.initialize(missing)
        self.assertEqual(sidecar.read_bytes(),b'leave intact');self.assertFalse(missing.exists())

    def test_tampered_materialized_state_rejected(self):
        self.apply()
        with sqlite3.connect(self.db) as db:db.execute('UPDATE company_entries SET revision=2')
        with self.assertRaises(ValueError):W.entries(self.db)

    def test_changed_schema_and_history_tampering_rejected(self):
        self.apply()
        with sqlite3.connect(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM analyst_history')
            db.execute('DROP TRIGGER analyst_history_DELETE')
        with self.assertRaises(ValueError):W.entries(self.db)

    def test_export_uses_public_format_and_no_internal_audit_fields(self):
        self.apply()
        export=W.export_backup(self.db,at=LATER)
        self.assertEqual(set(export),{'format','schema_version','exported_at','entries'})
        self.assertEqual(W.validate_backup(export),self.backup['entries'])
        self.assertNotIn('revision',export['entries'][0])

    def test_cli_errors_do_not_leak_notes_or_paths(self):
        output=io.StringIO()
        with redirect_stdout(output):code=W.main(['--db',str(self.root/'private-missing.sqlite'),'verify'])
        self.assertEqual(code,1)
        self.assertNotIn('private-missing',output.getvalue());self.assertNotIn(str(self.root),output.getvalue())

    def test_cli_export_private_and_no_overwrite(self):
        self.apply();output=self.root/'export.json';stream=io.StringIO()
        with redirect_stdout(stream):self.assertEqual(W.main(['--db',str(self.db),'export','--output',str(output)]),0)
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertEqual(W.validate_backup(output.read_bytes()),self.backup['entries'])
        self.assertNotIn('Private invented note',stream.getvalue())
        before=output.read_bytes()
        with redirect_stdout(stream):self.assertEqual(W.main(['--db',str(self.db),'export','--output',str(output)]),1)
        self.assertEqual(output.read_bytes(),before)


if __name__=='__main__':unittest.main()
