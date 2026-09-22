const {test}=require('node:test');
const assert=require('node:assert/strict');
const W=require('../ui/workspace.js');
const ID='a'.repeat(64), OTHER='b'.repeat(64), NOW=Date.parse('2026-09-22T12:00:00Z');
function storage(seed={}) {const map=new Map(Object.entries(seed));return {getItem:key=>map.get(key)??null,setItem:(key,value)=>map.set(key,value),map};}
function entry(id=ID) {return W.blankEntry(id,{company_name:'Example SAS',country:'France',latest_public_date:'2026-09-20'},null,'2026-09-22T12:00:00Z');}
function store(seed={}) {const s=new W.Store(storage(seed));s.load();return s;}
test('calendar age ignores cached recency_days',()=>assert.equal(W.signalAge({publicly_available_date:'2026-09-01',recency_days:1},NOW),21));
test('calendar recency changes without source refresh',()=>assert.equal(W.signalAge({publicly_available_date:'2026-09-01'},NOW+10*86400000),31));
test('invalid date and normalized February day rejected',()=>{assert.equal(W.signalAge({publicly_available_date:'2026-02-30'},NOW),null);assert.equal(W.signalAge({},NOW),null);});
test('future date retained as negative age for explicit exclusion from recent view',()=>assert.equal(W.signalAge({publicly_available_date:'2026-09-23'},NOW),-1));
test('source clock not build clock',()=>assert.equal(W.feedHealth({status:'ACTIVE',generated_at:'2026-09-22',source:{observed_at:'2026-09-01'}},NOW).state,'stale'));
test('invalid or future observation is unverified',()=>{for(const observed_at of ['bad','2026-09-24T00:00Z']) assert.equal(W.feedHealth({status:'ACTIVE',source:{observed_at}},NOW).state,'unverified');});
test('freshness 48-hour boundary',()=>{assert.equal(W.feedHealth({status:'ACTIVE',source:{observed_at:'2026-09-20T12:00Z'}},NOW).state,'recent');assert.equal(W.feedHealth({status:'ACTIVE',source:{observed_at:'2026-09-20T11:59Z'}},NOW).state,'stale');});
test('unavailable feed does not become active empty',()=>assert.equal(W.feedHealth({status:'UNAVAILABLE'},NOW).state,'unavailable'));
test('missing amount not zero',()=>{for(const v of ['',null,undefined,'  '])assert.equal(W.money(v,'CAD'),'Amount not stated');});
test('actual zero retained',()=>assert.match(W.money('0','CAD'),/0\.00/));
test('missing currency not invented CAD',()=>assert.equal(W.money('1000',''),'1000 (currency not stated)'));
test('uninterpretable amount not sanitized into false number',()=>assert.equal(W.money('unknown','CAD'),'unknown CAD (as published)'));
test('no fuzzy identity merge',()=>{const payload={status:'ACTIVE',signals:[{company_id:ID,company_name:'Same name',country:'France'},{company_id:OTHER,company_name:'Same name',country:'France'}]};assert.equal(W.groupCompanies(payload).size,2);});
test('legacy watch migration preserves storage and missing identities',()=>{const db=storage({[W.LEGACY_KEY]:JSON.stringify([ID,OTHER])});const s=new W.Store(db);s.load();assert.equal(s.entries().length,2);assert.equal(db.getItem(W.KEY),null);s.put(entry());assert.equal(db.getItem(W.LEGACY_KEY),JSON.stringify([ID,OTHER]));});
test('canonical workspace does not resurrect removed legacy stars',()=>{const s=store({[W.LEGACY_KEY]:JSON.stringify([ID])});s.remove(ID);s.load();assert.equal(s.entries().length,0);});
test('notes persist and copies cannot mutate store',()=>{const s=store();s.put({...entry(),notes:'Review before outreach'});const copy=s.entries();copy[0].notes='changed';s.load();assert.equal(s.get(ID).notes,'Review before outreach');});
test('storage quota error preserves both states',()=>{const s=store();s.put(entry());const before=s.raw;s.storage.setItem=()=>{throw new Error('Quota');};assert.throws(()=>s.put({...entry(),notes:'not saved'}),/Quota/);assert.equal(s.raw,before);assert.equal(s.get(ID).notes,'');});
test('malformed existing state cannot silently be overwritten',()=>{const s=new W.Store(storage({[W.KEY]:'{"broken"'}));assert.throws(()=>s.load());assert.throws(()=>s.put(entry()),/not available/);assert.equal(s.storage.getItem(W.KEY),'{"broken"');});
test('revision conflict preserves external change and draft',()=>{const s=store();s.put(entry());const external=JSON.stringify({schema_version:1,entries:[{...entry(),notes:'other tab'}]});s.storage.setItem(W.KEY,external);assert.throws(()=>s.put({...entry(),notes:'draft'}),/another tab/);assert.equal(s.storage.getItem(W.KEY),external);});
test('backup round trip',()=>{const s=store();s.put(entry());const second=store();second.mergeNew(JSON.stringify(s.backup()));assert.deepEqual(second.entries(),s.entries());});
test('restore never overwrites existing notes',()=>{const s=store();s.put({...entry(),notes:'approved notes'});const restored={format:'atlanticbridge-analyst-workspace',schema_version:1,entries:[{...entry(),notes:'old notes'},entry(OTHER)]};assert.deepEqual(s.mergeNew(restored),{added:1,kept:1});assert.equal(s.get(ID).notes,'approved notes');});
test('duplicate backup identities rejected atomically',()=>{const s=store();assert.throws(()=>s.mergeNew({format:'atlanticbridge-analyst-workspace',schema_version:1,entries:[entry(),entry()]}),/Duplicate/);assert.equal(s.entries().length,0);});
test('prototype identity and inherited status rejected',()=>{assert.throws(()=>W.validateEntry({...entry(),id:'__proto__'}));assert.throws(()=>W.validateEntry({...entry(),status:'constructor'}));});
test('oversized notes or workspace rejected',()=>{assert.throws(()=>W.validateEntry({...entry(),notes:'x'.repeat(4001)}),/oversized/);assert.throws(()=>W.validateBackup('x'.repeat(W.MAX_BYTES+1)),/2 MB/);});
test('unsafe link or malformed snapshot hash rejected',()=>{assert.throws(()=>W.validateEntry({...entry(),source_url:'javascript:alert(1)'}));assert.throws(()=>W.validateEntry({...entry(),source_sha256:'bogus'}));});
test('invalid follow-up date rejected',()=>assert.throws(()=>W.validateEntry({...entry(),due_date:'2026-02-30'})));
test('export escapes CSV formulas and controls',()=>{for(const v of ['=1+1','+123','-1','@SUM(1)',' =1','\t=1','\rtest']) assert.ok(W.csvCell(v).startsWith('"\''));assert.equal(W.csvCell('He said "yes"'),'"He said ""yes"""');});
test('CSV field separation includes provenance and user work',()=>{const csv=W.worklistCSV([{...entry(),next_action:'Check, then call',notes:'=1+1'}]);assert.match(csv,/"source_sha256"/);assert.match(csv,/"Check, then call"/);assert.match(csv,/"'=1\+1"/);});
