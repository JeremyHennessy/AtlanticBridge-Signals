"""Offline adversarial staging tests: no external notification transport."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from atlanticbridge.automation.store import Store, Conflict, verify_database
from atlanticbridge.automation.models import canonical, decode_batch, digest, timestamp
from atlanticbridge.automation.review_notifications import ReviewJournal, inspect, snapshot, verify_journal, main, MODE
from test_automation_foundation import contract, body, NOW, LATER, THIRD

FOURTH = '2026-11-09T12:00:00Z'


class ReviewNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.foundation = self.root/'foundation.sqlite'; self.journal = self.root/'review.sqlite'
        self.store = Store(self.foundation); self.addCleanup(self.store.close)
        self.c = contract(); self.store.register(self.c,at=NOW)
        self.store.set_source_state(self.c.source_id,'READY',at=NOW,actor='test')
        with ReviewJournal.initialize(self.journal) as j:
            j.register(self.foundation,plan_id='test',sources=['fixture'],since=NOW)

    def ingest(self, rows=None, at=NOW, c=None):
        c = c or self.c
        run = self.store.claim(c.source_id,at=at)
        self.assertIsNotNone(run)
        return self.store.complete(run,decode_batch(body(c,rows),c),at=at)

    def changes(self):
        self.ingest()
        self.ingest([{'record_id':'one','facts':{'title':'changed'},'event_date':'2020-01-01','published_date':'2020-02-01'},
                     {'record_id':'two','facts':{'title':'new'},'event_date':'2019-01-01'}],at=LATER)

    def stage(self, **kw):
        with ReviewJournal(self.journal) as j:
            return j.stage(self.foundation,plan_id='test',at=kw.pop('at',THIRD),**kw)

    def test_inert_baseline_and_replay(self):
        self.ingest(); self.assertEqual(inspect(self.journal),[])
        self.assertEqual(self.stage()['staged'],0)
        self.ingest(at=LATER); self.assertEqual(self.stage()['staged'],0)

    def test_changed_first_observations_preserve_dates_and_private_origin(self):
        self.changes(); result = self.stage()
        self.assertEqual(result['staged'],2); self.assertFalse(result['has_more'])
        packets = inspect(self.journal)
        self.assertEqual({p['event_kind'] for p in packets},{'RECORD_CONTENT_CHANGED','RECORD_FIRST_OBSERVED'})
        p = next(p for p in packets if p['record_id']=='one')
        self.assertEqual(p['event_date'],'2020-01-01'); self.assertEqual(p['published_date'],'2020-02-01')
        self.assertEqual(p['imported_at'],timestamp(LATER)); self.assertEqual(p['origin'],'INVENTED_FIXTURE')
        self.assertEqual(p['source_contract_id'], self.c.contract_id)
        for p in packets:
            for k in ('production_enabled','public_alert','lead_eligible','delivery_enabled','delivered'): self.assertIs(p[k],False)
            self.assertIn('superseded',p['interpretation'])

    def test_notes_facts_paths_and_source_urls_excluded(self):
        self.changes()
        item = self.store.work_items()[0]
        self.store.update_work_item(item['item_id'],expected_revision=item['revision'],status='ACTIVE',notes='SECRET-NOTE',due_date='2026-11-10',needs_review=True,at=THIRD,actor='test')
        self.stage(); raw = canonical(inspect(self.journal))
        for forbidden in ('SECRET-NOTE','due_date','input_path','facts','source_url','changed'):
            self.assertNotIn(forbidden,raw)

    def test_paging_restart_and_durable_dedup(self):
        self.changes(); a=self.stage(max_scan=1); b=self.stage(max_scan=1); c=self.stage(max_scan=1)
        self.assertEqual((a['staged'],a['has_more'],a['cursor']),(1,True,1))
        self.assertEqual((b['staged'],b['has_more'],b['cursor']),(1,False,2))
        self.assertEqual((c['staged'],c['has_more'],c['cursor']),(0,False,2))
        self.assertEqual(len(inspect(self.journal)),2)

    def test_concurrent_stage_calls_serialize(self):
        self.changes()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.stage(),range(2)))
        self.assertEqual(sorted(r['staged'] for r in results),[0,2])
        self.assertEqual(len(inspect(self.journal)),2)

    def test_source_and_since_filters_advance_global_cursor(self):
        self.changes()
        with ReviewJournal(self.journal) as j:
            j.register(self.foundation,plan_id='later',sources=['fixture'],since=THIRD)
            result=j.stage(self.foundation,plan_id='later',at=THIRD,max_scan=1)
        self.assertEqual(result['scanned'],1); self.assertEqual(result['staged'],0); self.assertTrue(result['has_more'])
        self.assertEqual(inspect(self.journal,plan_id='later'),[])

    def test_unselected_and_late_append_use_row_order_not_timestamp(self):
        other=contract('other'); self.store.register(other,at=NOW)
        self.store.set_source_state('other','READY',at=NOW,actor='test')
        self.ingest(c=other); self.changes(); self.stage()
        # This source appends later with an earlier valid import clock.
        self.ingest([{'record_id':'late','facts':{'title':'older clock'}}],at=LATER,c=other)
        result=self.stage()
        self.assertEqual((result['scanned'],result['staged'],result['cursor']),(1,0,3))
        with ReviewJournal(self.journal) as j:
            j.register(self.foundation,plan_id='other',sources=['other'],since=NOW)
            self.assertEqual(j.stage(self.foundation,plan_id='other',at=THIRD)['staged'],1)

    def test_selected_late_append_is_not_lost(self):
        other=contract('other'); self.store.register(other,at=NOW)
        self.store.set_source_state('other','READY',at=NOW,actor='test'); self.ingest(c=other)
        with ReviewJournal(self.journal) as j: j.register(self.foundation,plan_id='both',sources=['other','fixture'],since=NOW)
        self.changes()
        with ReviewJournal(self.journal) as j: j.stage(self.foundation,plan_id='both',at=THIRD)
        self.ingest([{'record_id':'late','facts':{'title':'older'}}],at=LATER,c=other)
        with ReviewJournal(self.journal) as j: self.assertEqual(j.stage(self.foundation,plan_id='both',at=THIRD)['staged'],1)
        self.assertEqual(len(inspect(self.journal,plan_id='both')),3)

    def test_older_foundation_fails_without_cursor_reset(self):
        self.ingest(); old=self.root/'old.sqlite'; self.store.backup(old)
        self.ingest([{'record_id':'new','facts':{'title':'new'}}],at=LATER); self.stage()
        with ReviewJournal(self.journal) as j:
            with self.assertRaises(Conflict): j.stage(old,plan_id='test',at=THIRD)
        self.assertEqual(self.stage()['staged'],0)

    def test_different_valid_history_anchor_rejected(self):
        self.ingest(); old=self.root/'old.sqlite'; self.store.backup(old)
        self.ingest([{'record_id':'a','facts':{'title':'a'}}],at=LATER); self.stage()
        with Store(old) as fork:
            run=fork.claim('fixture',at=LATER)
            fork.complete(run,decode_batch(body(self.c,[{'record_id':'b','facts':{'title':'b'}}]),self.c),at=LATER)
        with ReviewJournal(self.journal) as j:
            with self.assertRaises(Conflict): j.stage(old,plan_id='test',at=THIRD)

    def test_future_events_and_backwards_stage_time_rollback(self):
        self.changes()
        with self.assertRaises(Conflict): self.stage(at=NOW)
        self.assertEqual(inspect(self.journal),[])
        self.stage()
        with self.assertRaises(Conflict): self.stage(at=LATER)

    def test_strict_bounds_and_utc(self):
        for n in (0,1001,True,1.1):
            with self.subTest(n=n), self.assertRaises(ValueError): self.stage(max_scan=n)
        with self.assertRaises(ValueError): self.stage(at='2026-11-08T08:00:00-04:00')
        with ReviewJournal(self.journal) as j:
            for sources in ([],['fixture','fixture'],['fixture']*101):
                with self.assertRaises(ValueError): j.register(self.foundation,plan_id='bad',sources=sources,since=NOW)
            with self.assertRaises(ValueError): j.register(self.foundation,plan_id='../bad',sources=['fixture'],since=NOW)

    def test_plan_idempotent_immutable_and_contract_pin(self):
        with ReviewJournal(self.journal) as j:
            self.assertFalse(j.register(self.foundation,plan_id='test',sources=['fixture'],since=NOW))
            with self.assertRaises(Conflict): j.register(self.foundation,plan_id='test',sources=['fixture'],since=LATER)
        alternate=self.root/'alternate.sqlite'
        with Store(alternate) as store: store.register(replace(self.c,parser_version='new'),at=NOW)
        with ReviewJournal(self.journal) as j:
            with self.assertRaises(Conflict): j.stage(alternate,plan_id='test',at=THIRD)

    def test_wrong_schema_and_readonly_missing_never_create(self):
        absent=self.root/'absent.sqlite'
        for operation in (lambda: inspect(absent),lambda: ReviewJournal(absent)):
            with self.assertRaises(OSError): operation()
        self.assertFalse(absent.exists())
        with self.assertRaises(ValueError): ReviewJournal(self.foundation)
        with self.assertRaises((ValueError,sqlite3.DatabaseError)):
            with snapshot(self.journal,foundation=True): pass
        self.assertEqual(inspect(self.journal),[])

    def test_permissions_symlinks_and_hardlinks_rejected(self):
        for target in (self.foundation,self.journal):
            link=self.root/('link'+target.name); link.symlink_to(target)
            hard=self.root/('hard'+target.name); os.link(target,hard)
            with self.assertRaises(ValueError):
                with snapshot(link,foundation=target==self.foundation): pass
            with self.assertRaises(ValueError):
                with snapshot(hard,foundation=target==self.foundation): pass
            hard.unlink(); link.unlink()
            os.chmod(target,0o644)
            with self.assertRaises(ValueError):
                with snapshot(target,foundation=target==self.foundation): pass
            os.chmod(target,0o600)
        self.assertEqual(self.journal.stat().st_mode & 0o777,0o600)

    def test_append_only_sql_protection(self):
        self.changes(); self.stage()
        with ReviewJournal(self.journal) as j:
            for table in ('plans','passes','packets','review_meta'):
                with self.assertRaises(sqlite3.IntegrityError): j.db.execute('DELETE FROM '+table)

    def tamper(self, table, statement, values=()):
        db=sqlite3.connect(self.journal)
        trigger=db.execute('SELECT sql FROM sqlite_master WHERE name=?',(table+'_UPDATE',)).fetchone()[0]
        db.execute(f'DROP TRIGGER {table}_UPDATE'); db.execute(statement,values); db.execute(trigger); db.commit(); db.close()

    def test_tampered_packet_hash_and_fixed_semantics_rejected(self):
        self.changes(); self.stage()
        p=inspect(self.journal)[0]; p['delivered']=True
        self.tamper('packets','UPDATE packets SET payload=?,sha=? WHERE event_id=?',(canonical(p),digest(p),p['event_id']))
        with self.assertRaises(ValueError): inspect(self.journal)

    def test_stale_payload_hash_rejected(self):
        self.changes(); self.stage()
        p=inspect(self.journal)[0]; p['attribution']='changed'
        self.tamper('packets','UPDATE packets SET payload=? WHERE event_id=?',(canonical(p),p['event_id']))
        with self.assertRaises(ValueError): inspect(self.journal)

    def test_tampered_cursor_and_pass_counts_rejected(self):
        self.changes(); self.stage()
        self.tamper('passes','UPDATE passes SET end_seq=999')
        with self.assertRaises(ValueError): inspect(self.journal)

    def test_backup_wal_restore_and_no_overwrite(self):
        self.changes(); self.stage(max_scan=1); backup=self.root/'backup.sqlite'
        with ReviewJournal(self.journal) as j:
            self.assertEqual(j.backup(backup)['packets'],1)
            with self.assertRaises(FileExistsError): j.backup(backup)
        with ReviewJournal(backup) as j:
            self.assertEqual(j.stage(self.foundation,plan_id='test',at=THIRD)['staged'],1)
            self.assertEqual(j.stage(self.foundation,plan_id='test',at=THIRD)['staged'],0)
        self.assertEqual(len(inspect(backup)),2)
        self.assertEqual(backup.stat().st_mode & 0o777,0o600)

    def test_failed_backup_artifact_retained(self):
        destination=self.root/'failed.sqlite'
        with ReviewJournal(self.journal) as j:
            with patch('atlanticbridge.automation.review_notifications.verify_journal',side_effect=ValueError('test failure')):
                with self.assertRaises(ValueError): j.backup(destination)
        self.assertTrue(destination.exists())

    def test_same_snapshot_verified_and_queried(self):
        self.changes()
        from atlanticbridge.automation import review_notifications as module
        original=module.verify_connection
        seen=[]
        def verify(db):
            seen.append(db); result=original(db)
            # Independently append after the verified snapshot has been taken.
            self.ingest([{'record_id':'after','facts':{'title':'after snapshot'}}],at=THIRD)
            return result
        with patch.object(module,'verify_connection',side_effect=verify):
            self.assertEqual(self.stage(at=FOURTH)['staged'],2)
        self.assertEqual(len(seen),1)
        self.assertEqual(self.stage(at=FOURTH)['staged'],1)

    def test_foundation_unchanged_and_semantically_verified(self):
        self.changes(); before='\n'.join(self.store.db.iterdump()); self.stage()
        self.assertEqual('\n'.join(self.store.db.iterdump()),before)
        verify_database(self.foundation)
        # Privileged evidence corruption must be caught before any staging write.
        self.store.db.execute("DROP TRIGGER immutable_version_update")
        self.store.db.execute("UPDATE record_versions SET content_sha256='bad' WHERE rowid=1")
        with self.assertRaises(ValueError): self.stage()

    def test_private_sidecar_and_schema_tampering_rejected(self):
        sidecar=Path(str(self.journal)+'-journal')
        sidecar.write_bytes(b''); sidecar.chmod(0o644)
        with self.assertRaises(ValueError): inspect(self.journal)
        sidecar.unlink()
        db=sqlite3.connect(self.journal); db.execute('DROP TRIGGER packets_DELETE'); db.commit(); db.close()
        with self.assertRaises(ValueError): inspect(self.journal)

    def test_packet_type_identity_and_extra_fields_rejected(self):
        from atlanticbridge.automation.review_notifications import validate_payload
        self.changes(); self.stage()
        p=inspect(self.journal)[0]
        with ReviewJournal(self.journal) as j:
            config=json.loads(j.db.execute('SELECT config FROM plans').fetchone()[0])
        for key,value in (('public_alert',0),('work_item_id','a'*64),('event_kind','VERIFIED_LEAD'),
                          ('source_id',[]),('notes','private'),('origin','LIVE_HTTP_RESPONSE'),
                          ('event_date','not-a-date'),('from_version_id',False)):
            changed=dict(p); changed[key]=value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_payload(changed,config)

    def test_future_filtered_event_also_rejected(self):
        self.changes()
        with ReviewJournal(self.journal) as j:
            j.register(self.foundation,plan_id='later',sources=['fixture'],since=FOURTH)
            with self.assertRaises(Conflict): j.stage(self.foundation,plan_id='later',at=NOW)
        self.assertEqual(inspect(self.journal,plan_id='later'),[])

    def test_changed_consumed_prefix_with_same_last_anchor_rejected(self):
        self.changes()
        self.ingest([{'record_id':'third','facts':{'title':'third'}}],at=THIRD)
        self.stage(at=FOURTH)
        alternate=self.root/'reordered.sqlite'; self.store.backup(alternate)
        db=sqlite3.connect(alternate)
        trigger=db.execute("SELECT sql FROM sqlite_master WHERE name='immutable_event_update'").fetchone()[0]
        db.execute('DROP TRIGGER immutable_event_update')
        db.execute('UPDATE evidence_events SET rowid=100 WHERE rowid=1')
        db.execute('UPDATE evidence_events SET rowid=1 WHERE rowid=2')
        db.execute('UPDATE evidence_events SET rowid=2 WHERE rowid=100')
        db.execute(trigger); db.commit(); db.close()
        verify_database(alternate)
        with ReviewJournal(self.journal) as j:
            with self.assertRaises(Conflict): j.stage(alternate,plan_id='test',at=FOURTH)

    def test_new_destinations_refuse_all_existing_sidecars(self):
        for suffix in ('-wal','-shm','-journal'):
            for operation in ('init','backup','foundation-backup'):
                target=self.root/(operation+suffix+'.sqlite'); sidecar=Path(str(target)+suffix)
                sidecar.write_bytes(b'preserve orphan bytes'); sidecar.chmod(0o644)
                with self.subTest(suffix=suffix,operation=operation), self.assertRaises(FileExistsError):
                    if operation == 'init': ReviewJournal.initialize(target)
                    elif operation == 'foundation-backup': self.store.backup(target)
                    else:
                        with ReviewJournal(self.journal) as journal: journal.backup(target)
                self.assertFalse(target.exists())
                self.assertEqual(sidecar.read_bytes(),b'preserve orphan bytes')
                self.assertEqual(sidecar.stat().st_mode & 0o777,0o644)

    def test_new_destination_sidecar_links_preserved(self):
        for suffix in ('-wal','-shm','-journal'):
            for kind in ('private','symlink','dangling-symlink','hardlink'):
                for operation in ('init','backup','foundation-backup'):
                    target=self.root/(operation+kind+suffix+'.sqlite')
                    sidecar=Path(str(target)+suffix)
                    sentinel=self.root/(operation+kind+suffix+'.sentinel')
                    sentinel.write_bytes(b'preserve linked bytes'); sentinel.chmod(0o600)
                    if kind == 'symlink': sidecar.symlink_to(sentinel)
                    elif kind == 'dangling-symlink': sidecar.symlink_to(self.root/'absent-link-target')
                    elif kind == 'hardlink': os.link(sentinel,sidecar)
                    else: sidecar.write_bytes(b'private orphan'); sidecar.chmod(0o600)
                    before=sidecar.lstat()
                    with self.subTest(suffix=suffix,kind=kind,operation=operation), self.assertRaises(FileExistsError):
                        if operation == 'init': ReviewJournal.initialize(target)
                        elif operation == 'foundation-backup': self.store.backup(target)
                        else:
                            with ReviewJournal(self.journal) as journal: journal.backup(target)
                    self.assertFalse(target.exists()); self.assertTrue(os.path.lexists(sidecar))
                    self.assertEqual(sidecar.lstat().st_ino,before.st_ino)
                    self.assertEqual(sidecar.lstat().st_mode,before.st_mode)
                    self.assertEqual(sentinel.read_bytes(),b'preserve linked bytes')
                    if kind == 'private': self.assertEqual(sidecar.read_bytes(),b'private orphan')

    def test_cli_errors_exclude_private_paths(self):
        path=self.root/'private-customer-name.sqlite'; capture=io.StringIO()
        with redirect_stdout(capture): code=main(['--journal',str(path),'verify'])
        self.assertEqual(code,1)
        self.assertNotIn(str(path),capture.getvalue())
        self.assertNotIn('private-customer-name',capture.getvalue())

    def test_cli_explicit_lifecycle(self):
        path=self.root/'cli.sqlite'
        def cli(*args):
            capture=io.StringIO()
            with redirect_stdout(capture): code=main(['--journal',str(path),*args])
            return code,json.loads(capture.getvalue())
        self.assertEqual(cli('verify')[0],1); self.assertFalse(path.exists())
        self.assertEqual(cli('init')[0],0)
        self.assertEqual(cli('register','--foundation',str(self.foundation),'--plan-id','cli','--source','fixture','--since',NOW)[0],0)
        self.changes()
        self.assertEqual(cli('stage','--foundation',str(self.foundation),'--plan-id','cli','--at',THIRD)[1]['staged'],2)
        self.assertEqual(len(cli('inspect')[1]),2); self.assertEqual(cli('verify')[1]['integrity'],'ok')
        self.assertEqual(cli('backup','--destination',str(self.root/'cli-backup.sqlite'))[0],0)


if __name__ == '__main__': unittest.main()
