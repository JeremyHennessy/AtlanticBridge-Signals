const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const W=require('../ui/workspace.js'),O=require('../ui/opportunities.js');
const read=p=>fs.readFileSync(path.join(__dirname,'..',p),'utf8');
const app=read('ui/app.js'),html=read('ui/index.html');
const id='a'.repeat(64),sid='b'.repeat(64),now=Date.parse('2026-09-22T12:00Z');
const signal=()=>({id:sid,company_id:id,company_name:'Example <script>x</script>',country:'France',title:'Award',
  source_url:'https://example.test/award',publicly_available_date:'2026-09-21',signal_kind:'FEDERAL_AWARD_AMENDED',
  contract_amount:'1000',contract_currency:'CAD',reference_number:'same-contract',why_surfaced:'Legacy unqualified explanation'});
const feed=()=>({status:'ACTIVE',source:{observed_at:'2026-09-22T12:00Z'},signals:[signal()]});
test('legacy notice queue remains research and warns without new server fields',()=>{
  const f=feed(),before=JSON.stringify(f),q=O.queue(f,null,null,now),r=q.current[0];
  assert.equal(r.kind,'Commercial/research signal');assert.match(r.what,/administrative.*does not establish new spending/);
  assert.match(r.next_action,/Reconcile.*not an open procurement/);assert.equal(r.qualified,false);
  assert.equal(q.qualified.length,0);assert.equal(JSON.stringify(f),before);
});
test('initial notice queue warns that value is not incremental spend',()=>{
  const f=feed();f.signals[0].signal_kind='FEDERAL_AWARD_PUBLISHED';
  assert.match(O.queue(f,null,null,now).current[0].what,/does not establish incremental spending or payments/);
});
test('signal renderer labels amounts and warns on legacy payloads, safely escaping evidence',()=>{
  const nodes=new Map(),get=id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},innerHTML:'',textContent:''});return nodes.get(id);};
  const state={live:feed(),watched:new Set()};
  const esc=v=>String(v??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const context={state,$:get,ABWorkspace:W,filteredSignals:()=>state.live.signals,escapeHtml:esc,
    formatDate:v=>v,formatMoney:W.money,safeUrl:v=>v,companyHash:v=>'#company?id='+v,
    liveFreshnessText:()=> 'Fixture snapshot',workSourceCoverage:()=> 'Offline fixture'};
  vm.runInNewContext(app.slice(app.indexOf('function renderSignals()'),app.indexOf('function renderMetrics()'))+'\nrenderSignals();',context);
  const rendered=get('signals-list').innerHTML;
  assert.match(rendered,/Published notice value/);assert.match(rendered,/Award notice amended/);
  assert.match(rendered,/Commercial\/research signal/);assert.match(rendered,/Do not sum raw notice or history rows/);
  assert.ok(!rendered.includes('<script>'));assert.match(rendered,/&lt;script&gt;/);
});
test('browser unavailable fallback withholds amount rather than showing zero',()=>{
  const start=app.indexOf('function unavailableLivePayload('),end=app.indexOf('\n}',start)+2;
  const context={ABWorkspace:W};vm.runInNewContext(app.slice(start,end)+'\nresult=unavailableLivePayload("test");',context);
  assert.equal(context.result.summary.cad_contract_amount,null);
  assert.equal(context.result.summary.amount_aggregation_status,'WITHHELD_UNRECONCILED_NOTICE_AMOUNTS');
});
test('guide separates dataset correction and evidence roles without automatic qualification',()=>{
  for(const phrase of ['Announced expansion:','Commercial/research signal:','Relevant opportunity:','this guide does not qualify records','product uses a separate award-notice CSV','does not establish that this feed was affected','removed history row alone'])assert.ok(html.includes(phrase),phrase);
  assert.ok(html.includes('COsoutien-CHsupport-eng.html'));
  const dossier=read('ui/workbench.js');
  assert.ok(dossier.includes('ABWorkspace.CANADABUYS_AMOUNT_WARNING'));
  assert.ok(dossier.includes('Counts are notice records, not distinct contracts'));
  assert.ok(dossier.includes('Published notice value:'));
});
test('cached unavailable asset is unchanged in availability and not zero spending',()=>{
  const p=JSON.parse(read('ui/data/live-signals.json'));
  assert.equal(p.status,'UNAVAILABLE');assert.equal(p.summary.cad_contract_amount,null);
  assert.equal(p.summary.amount_aggregation_status,'WITHHELD_UNRECONCILED_NOTICE_AMOUNTS');
});
