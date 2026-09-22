import fs from 'node:fs';
import path from 'node:path';

// The real hosted feed is checked separately below. This deterministic fixture is test-only.
const ID='a'.repeat(64), OTHER='b'.repeat(64), MISSING='f'.repeat(64);
const KEY='atlanticbridge.analyst-workspace.v1';
const stamp='2026-09-22T12:00:00Z';
function fixture() {
  const signals=[0,1,2].map(i=>({
    id:String(i+1).repeat(64),record_id:String(i+1).repeat(64),company_id:i<2?ID:OTHER,
    company_name:i<2?'TEST Example France SAS':'TEST Example Germany GmbH',country:i<2?'France':'Germany',
    signal_family:'CANADABUYS_AWARD',source_confidence:'SOURCE_CONFIRMED',signal_kind:'FEDERAL_AWARD_PUBLISHED',
    signal_stage:'CANADIAN_BUYER_RELATIONSHIP_LOCATION_UNVERIFIED',identity_scope:'SUPPLIER_LEGAL_NAME_AS_PUBLISHED',
    publicly_available_date:i===0?'2026-09-20':'2026-08-01',event_date:'2026-07-01',recency_days:0,
    contract_amount:i===0?'':'1000.25',contract_currency:i===1?'':'CAD',title:'TEST-only notice '+i,
    source_url:'https://canadabuys.canada.ca/opendata/pub/2026-2027-awardNotice-avisAttribution.csv',
    contracting_entity:'TEST buyer',reference_number:'TEST-'+i,why_surfaced:'TEST fixture; not an expansion probability or proof of first entry.',
    scope_review:{state:'INCLUDED_BUYER_ONLY'},regions_of_delivery:'',award_description:'TEST-only source fields'
  }));
  return {schema_version:1,status:'ACTIVE',generated_at:stamp,as_of_date:'2026-09-22',
    source:{family:'CANADABUYS_AWARD',label:'TEST-only source',observed_at:stamp,source_url:signals[0].source_url,source_sha256:'c'.repeat(64)},
    summary:{signal_count:3,company_count:2,country_count:2,latest_public_date:'2026-09-20',lookback_days:365},signals};
}
async function settled(page) {await page.waitForFunction(()=>document.querySelector('#metric-cases')?.textContent==='27');}
async function hash(page,value) {await page.evaluate(v=>{location.hash=v;},value);await page.waitForTimeout(100);}
async function fits(page,label,check) {const v=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));check(`${label}: workbench page fits`,v.s<=v.w+2,JSON.stringify(v));}
export async function verifyLiveDossiers(page,live,label,out,check) {
  if(live.status!=='ACTIVE')return;
  const groups=new Map();for(const s of live.signals){const rows=groups.get(s.company_id)||[];rows.push(s);groups.set(s.company_id,rows);}
  for(const [id,rows] of groups){
    await hash(page,`#company?id=${id}`);await page.locator('#company-title').waitFor();
    check(`${label}: dossier identity ${id}`,await page.locator('#company-title').innerText()===rows[0].company_name);
    check(`${label}: dossier complete notices ${id}`,await page.locator('[data-company-notice]').count()===rows.length);
    check(`${label}: dossier boundaries ${id}`,(await page.locator('#company-content').innerText()).includes('not a verified parent'));
    for(const row of rows){const card=page.locator(`[data-company-notice="${row.id}"]`);check(`${label}: dossier exact source ${row.id}`,await card.locator('.source-link').getAttribute('href')===new URL(row.source_url).href);}
    await fits(page,`${label}/${id}`,check);
    if(id===[...groups.keys()][0])await page.screenshot({path:path.join(out,`${label}-company-dossier.png`),fullPage:true});
  }
}
export async function verifyWorkspace(browser,options,base,label,out,check) {
  const context=await browser.newContext(options);const p=await context.newPage();const errors=[];
  p.on('pageerror',e=>errors.push(e.message));
  await p.clock.install({time:new Date(stamp)});
  const live=fixture();
  await context.route('**/data/live-signals.json',r=>r.fulfill({status:200,json:live}));
  await context.addInitScript(({id})=>{if(localStorage.getItem('test-work-seeded')===null){localStorage.setItem('atlanticbridge.watched-companies.v1',JSON.stringify([id]));localStorage.setItem('atlanticbridge.saved-cases.v1','["preserved-case"]');localStorage.setItem('test-work-seeded','1');}},{id:ID});
  await p.goto(base,{waitUntil:'networkidle'});await settled(p);
  await hash(p,'#signals');
  check(`${label}: blank amount explicitly unknown`,(await p.locator('.live-signal-value').first().innerText()).includes('Amount not stated'));
  check(`${label}: source country not control`,(await p.locator('#signals-view').innerText()).includes('Supplier address countries; not control'));
  await p.locator('#signal-window').selectOption('30');
  check(`${label}: recency calculated from public date`,await p.locator('[data-live-signal-id]').count()===1);
  await p.locator('#open-worklist').click();await p.locator('.worklist-row').waitFor();
  check(`${label}: old watch star migrated`,await p.locator('[data-worklist-id]').count()===1);
  await p.locator('.work-company-link').click();await p.locator('#company-title').waitFor();
  check(`${label}: company sees all dates not just signal filter`,await p.locator('[data-company-notice]').count()===2);
  const note='=SUM(1,1)\n<img src=x onerror="window.workXSS=true">\nTEST research note';
  await p.locator('#work-notes').fill(note);await p.locator('#work-action').fill('Verify published Canadian footprint');await p.locator('#work-status').selectOption('follow_up');await p.locator('#work-date').fill('2026-09-21');
  await p.locator('#work-save').click();await p.waitForFunction(()=>document.querySelector('#work-save-state').textContent.startsWith('Saved in this browser'));
  const raw=await p.evaluate(key=>localStorage.getItem(key),KEY);
  check(`${label}: explicit save persisted user work`,JSON.parse(raw).entries[0].notes===note);
  await p.reload({waitUntil:'networkidle'});await settled(p);await p.locator('#work-notes').waitFor();
  check(`${label}: notes/status/date survive reload`,await p.locator('#work-notes').inputValue()===note && await p.locator('#work-status').inputValue()==='follow_up' && await p.locator('#work-date').inputValue()==='2026-09-21');
  check(`${label}: user text cannot execute HTML`,await p.evaluate(()=>!window.workXSS));
  check(`${label}: original bookmark storage untouched`,await p.evaluate(()=>localStorage.getItem('atlanticbridge.saved-cases.v1'))==='["preserved-case"]');
  check(`${label}: original watch key preserved for rollback`,await p.evaluate(()=>localStorage.getItem('atlanticbridge.watched-companies.v1'))===JSON.stringify([ID]));
  await p.locator('#work-notes').fill('unsaved draft');p.once('dialog',d=>d.dismiss());await hash(p,'#signals');
  check(`${label}: cancelling navigation retains draft`,p.url().includes('#company?') && await p.locator('#work-notes').inputValue()==='unsaved draft');
  p.once('dialog',d=>d.accept());await p.locator('#work-reload').click();
  await hash(p,'#worklist');await fits(p,label,check);
  await p.locator('#worklist-due').check();
  check(`${label}: due work filter and overdue badge`,await p.locator('[data-worklist-id]').count()===1 && (await p.locator('#worklist-rows').innerText()).includes('Overdue'));
  await p.screenshot({path:path.join(out,`${label}-worklist-fixture.png`),fullPage:true});
  const backupDownload=p.waitForEvent('download');await p.locator('#work-backup').click();const backup=await backupDownload;const backupText=fs.readFileSync(await backup.path(),'utf8');
  check(`${label}: actual JSON backup contains saved notes`,JSON.parse(backupText).entries[0].notes===note);
  const csvDownload=p.waitForEvent('download');await p.locator('#work-export').click();const csv=fs.readFileSync(await (await csvDownload).path(),'utf8');
  check(`${label}: actual CSV download neutralizes formulas`,csv.includes('"\'=SUM(1,1)'));
  const incoming=JSON.parse(backupText);incoming.entries[0].notes='must not overwrite';incoming.entries.push({...incoming.entries[0],id:MISSING,company_name:'TEST saved identity outside feed',notes:'retained offline work'});
  await p.locator('#work-import-file').setInputFiles({name:'restore.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(incoming))});await p.locator('#work-import-confirm').waitFor();
  check(`${label}: import preview is not a write`,await p.evaluate(key=>localStorage.getItem(key),KEY)===raw);
  await p.locator('#work-import-confirm').click();await p.waitForFunction(key=>JSON.parse(localStorage.getItem(key)).entries.length===2,KEY);
  check(`${label}: restore kept existing notes`,await p.evaluate(({key,id})=>JSON.parse(localStorage.getItem(key)).entries.find(x=>x.id===id).notes,{key:KEY,id:ID})===note);
  const imported=await p.evaluate(key=>localStorage.getItem(key),KEY);
  await p.locator('#work-import-file').setInputFiles({name:'invalid.json',mimeType:'application/json',buffer:Buffer.from('{"format":"wrong"}')});
  await p.waitForFunction(()=>document.querySelector('#work-import-state').textContent.startsWith('Nothing imported'));
  check(`${label}: malformed restore leaves store unchanged`,await p.evaluate(key=>localStorage.getItem(key),KEY)===imported);
  await hash(p,`#company?id=${MISSING}`);await p.locator('#company-title').waitFor();
  check(`${label}: missing feed company retains work without false absence`,(await p.locator('#company-content').innerText()).includes('not an absence finding') && await p.locator('#work-notes').inputValue()==='retained offline work');
  await hash(p,`#company?id=${ID}`);await p.locator('#work-notes').fill('draft while another tab edits');
  const other=await context.newPage();await other.goto(base);await settled(other);
  await other.evaluate(key=>{const d=JSON.parse(localStorage.getItem(key));d.entries[0].notes='other tab saved';localStorage.setItem(key,JSON.stringify(d));},KEY);
  await p.waitForFunction(()=>document.querySelector('#workspace-storage-notice').textContent.includes('another tab'));
  await p.locator('#work-save').click();
  check(`${label}: cross-tab conflict retains draft and other save`,await p.locator('#work-notes').inputValue()==='draft while another tab edits' && (await p.locator('#work-save-state').innerText()).includes('Another tab'));
  p.once('dialog',d=>d.accept());await p.locator('#work-reload').click();
  await context.route('**/data/dashboard.json',r=>r.fulfill({status:503,body:'unavailable'}));
  await p.reload({waitUntil:'networkidle'});await p.locator('#retry-load').waitFor();await hash(p,'#worklist');
  check(`${label}: historical source failure does not erase worklist`,await p.locator('[data-worklist-id]').count()===2);
  await hash(p,'#companies');await p.locator('#case-search').fill('cannot search unavailable history');
  await hash(p,'#research');await p.locator('#research-search').fill('cannot search unavailable research');
  check(`${label}: unavailable historical controls fail closed`,errors.length===0,errors.join(' | '));
  await hash(p,'#worklist');
  await context.route('**/data/live-signals.json',r=>r.fulfill({status:503,body:'unavailable'}));
  await p.reload({waitUntil:'networkidle'});await p.locator('#retry-load').waitFor();
  check(`${label}: both evidence feeds unavailable but saved work retained`,await p.locator('[data-worklist-id]').count()===2);
  await hash(p,`#company?id=${ID}`);await p.locator('#work-notes').waitFor();await p.locator('#work-notes').fill('not written on quota failure');
  await p.evaluate(key=>{const original=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k===key)throw new Error('Quota test');return original.call(this,k,v);};},KEY);
  await p.locator('#work-save').click();await p.waitForFunction(()=>document.querySelector('#work-save-state').textContent.startsWith('Not saved'));
  check(`${label}: quota failure never claims saved`,(await p.locator('#work-save-state').innerText()).includes('Quota test'));
  check(`${label}: no application page errors`,errors.length===0,errors.join(' | '));
  await context.close();
  const staleContext=await browser.newContext(options);const stale=await staleContext.newPage();await stale.clock.install({time:new Date('2026-10-23T12:00:00Z')});
  await staleContext.route('**/data/live-signals.json',r=>r.fulfill({json:live}));await stale.goto(base);await settled(stale);await hash(stale,'#signals');
  check(`${label}: stale observation clearly labelled`,await stale.locator('#signal-freshness').getAttribute('data-freshness')==='stale');
  await stale.locator('#signal-window').selectOption('30');check(`${label}: old event ages out without rebuilding`,await stale.locator('[data-live-signal-id]').count()===0);
  await staleContext.close();
}
