const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../ui/reviewed.js');
const load=()=>JSON.parse(fs.readFileSync('ui/data/reviewed-evidence.json'));
test('fifteen reviewed histories preserve the original six and remain independent of alerts',()=>{const d=api.validate(load());assert.equal(d.project_count,15);assert.equal(api.groups(d).size,15);assert.ok(d.projects.every(p=>p.public_alert_allowed===false));});
test('duplicate identities rejected',()=>{const d=load();d.projects[1].id=d.projects[0].id;assert.throws(()=>api.validate(d));});
test('unapproved first-entry inference rejected',()=>{const d=load();d.projects[0].first_entry_confirmed=true;assert.throws(()=>api.validate(d));});
test('unapproved public alert rejected',()=>{const d=load();d.projects[0].public_alert_allowed=true;assert.throws(()=>api.validate(d));});
test('source substitution rejected',()=>{const d=load();d.projects[0].events[0].source_url='https://example.com/other';assert.throws(()=>api.validate(d));});
test('unsafe evidence URL rejected',()=>{const d=load();d.projects[0].evidence[0].source_url='javascript:alert(1)';assert.throws(()=>api.validate(d));});
test('invalid publication day rejected',()=>{const d=load();d.projects[0].latest_public_date='2026-02-30';assert.throws(()=>api.validate(d));});
test('no catalog is unavailable not zero history',()=>assert.equal(api.groups(null).size,0));
test('stale monitor must remain stale despite latest generation',()=>assert.match(api.monitoringStatus({schema_version:1,status:'OBSERVED',sources:[],last_attempt_at:'2026-09-01T00:00:00Z'},Date.parse('2026-09-22T00:00:00Z')),/stale/));
test('failed source visible',()=>assert.match(api.monitoringStatus({schema_version:1,status:'DEGRADED',sources:[],last_attempt_at:'2026-09-22T00:00:00Z'},Date.parse('2026-09-22T00:10:00Z')),/failures/));
test('future monitoring time unverified',()=>assert.match(api.monitoringStatus({schema_version:1,status:'OBSERVED',sources:[],last_attempt_at:'2027-01-01T00:00:00Z'},Date.parse('2026-09-22T00:00:00Z')),/unverified/));
test('unknown feedback not negative or independent review',()=>{const r={alert_id:'a'.repeat(64),reviewer:'test-only',identity_correct:null,source_supported:null,useful:true,already_known:false,review_seconds:1};assert.equal(api.feedback([r])[0].identity_correct,null);});
test('corrupt feedback rejected before write',()=>assert.throws(()=>api.feedback({entries:[]})));
test('duplicate feedback cannot inflate denominator',()=>{const r={alert_id:'a'.repeat(64),reviewer:'test-only',identity_correct:null,source_supported:null,useful:null,already_known:null,review_seconds:0};assert.throws(()=>api.feedback([r,r]));});

test('unavailable saved project cannot acquire supplier-country semantics',()=>{
 const vm=require('node:vm'),nodes=new Map(),entry={company_name:'TEST historical project',country:'France',status:'review',next_action:'Check identity',notes:'Retained notes',due_date:'',updated_at:'2026-09-22T00:00:00Z'};
 const context={ABWorkspace:{groupCompanies:()=>new Map(),STATUSES:{review:'To review'}},ABReviewed:api,reviewedCatalog:null,reviewedProject:()=>null,state:{live:{}},document:{},escapeHtml:String,formatTimestamp:String,entry,$:id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',addEventListener(){}});return nodes.get(id);}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('ui/workbench.js','utf8'),context);vm.runInContext('workStore={get:()=>entry};renderCompany("test");',context);
 const html=nodes.get('company-content').innerHTML;assert.match(html,/Saved country label/);assert.doesNotMatch(html,/Supplier address country|Current supplier evidence/);assert.match(html,/Retained notes/);
});
