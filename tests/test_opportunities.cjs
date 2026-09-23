const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../ui/opportunities.js');
const now=Date.parse('2026-09-22T23:00:00Z'),id='a'.repeat(64),sid='b'.repeat(64),hash='c'.repeat(64);
function signal(day='2026-09-20'){return {id:sid,company_id:id,company_name:'Example <script>company</script>',title:'Canadian award',source_url:'https://example.org/award',publicly_available_date:day,why_surfaced:'Canadian buyer',source_sha256:hash};}
function feed(signals=[signal()]){return {status:'ACTIVE',signals,source:{observed_at:'2026-09-22T00:00:00Z',source_sha256:hash}};}
function project(day='2020-01-01'){return {id,company_name:'Historical company',title:'Historical project',location:'Halifax, NS',latest_public_date:day,summary:'A historical announcement.',next_action:'Verify current status',source:{source_url:'https://example.org/project',source_sha256:hash,observed_at:'2026-09-22T00:00:00Z'}};}
function register(){return {schema_version:1,status:'REVIEW_REGISTER_NOT_PREDICTIONS',decision_count:1,decisions:[{id:sid,project_id:id,company_name:'Historical company',decision:'HOLD',reviewer:'fixture-only',review_date:'2026-09-22',reason:'Identity pending',next_action:'Resolve identity',checks:Object.fromEntries(api.checks.map(k=>[k,'UNKNOWN'])),check_sources:Object.fromEntries(api.checks.map(k=>[k,[]])),evidence:[{source_id:'fixture',source_url:'https://example.org/document',raw_sha256:hash,observed_at:'2026-09-22T00:00:00Z',source_publication_date:'2026-09-20'}],first_entry_confirmed:false,predictive_score_allowed:false,independent_holdout:false,current_status_date:null,current_status_source_id:null}]};}
test('missing feeds are unknown not no activity',()=>{const q=api.queue(null,null,null,now);assert.equal(q.source_available,false);assert.equal(q.qualification_count,null);assert.equal(q.reviewed_decisions,null);});
test('public date controls recency not a new generation or fetch',()=>{const q=api.queue({...feed([signal('2020-01-01')]),generated_at:new Date(now).toISOString()},{projects:[project()]},null,now);assert.equal(q.current.length,0);assert.equal(q.history.length,1);});
test('future and malformed dates are not current evidence',()=>{assert.equal(api.queue(feed([signal('2027-01-01'),signal('2026-02-30')]),null,null,now).current.length,0);});
test('current documentary evidence is still historical context, not a new automated alert',()=>{const q=api.queue(null,{projects:[project('2026-09-16')]},null,now);assert.equal(q.current.length,1);assert.equal(q.history.length,1);assert.equal(q.current[0].qualified,false);});
test('source-supported procurement is not automatically qualified',()=>{assert.equal(api.queue(feed(),null,register(),now).qualified.length,0);});
test('review hold remains explicit',()=>{const q=api.queue(null,{projects:[project('2026-09-20')]},register(),now);assert.equal(q.current[0].decision.decision,'HOLD');assert.equal(q.qualified.length,0);});
test('one unknown check prevents qualification',()=>{const r=register();r.decisions[0].decision='QUALIFIED_FOR_INVESTIGATION';assert.throws(()=>api.validate(r));});
test('supported checks need references actually in the decision',()=>{const r=register();r.decisions[0].checks.legal_identity='SUPPORTED';assert.throws(()=>api.validate(r));r.decisions[0].check_sources.legal_identity=['absent'];assert.throws(()=>api.validate(r));});
test('complete current qualification is possible only with all bound checks',()=>{const r=register(),d=r.decisions[0];d.decision='QUALIFIED_FOR_INVESTIGATION';for(const k of api.checks){d.checks[k]='SUPPORTED';d.check_sources[k]=['fixture'];}d.current_status_date='2026-09-20';d.current_status_source_id='fixture';assert.equal(api.queue(null,{projects:[project('2026-09-20')]},r,now).qualified.length,1);d.current_status_source_id='invented';assert.throws(()=>api.validate(r));});
test('old qualification must age back into review',()=>{const r=register(),d=r.decisions[0];d.decision='QUALIFIED_FOR_INVESTIGATION';for(const k of api.checks){d.checks[k]='SUPPORTED';d.check_sources[k]=['fixture'];}d.current_status_date='2026-09-20';d.current_status_source_id='fixture';assert.equal(api.qualified(d,Date.parse('2027-01-01')),false);});
test('duplicate decisions fail closed',()=>{const r=register();r.decisions.push({...r.decisions[0]});r.decision_count=2;assert.throws(()=>api.validate(r));});
test('source URLs are restricted to public HTTPS syntax',()=>{const r=register();r.decisions[0].evidence[0].source_url='javascript:alert(1)';assert.throws(()=>api.validate(r));});
test('qualification never opens predictive or first-entry flags',()=>{for(const k of ['first_entry_confirmed','predictive_score_allowed','independent_holdout']){const r=register();r.decisions[0][k]=true;assert.throws(()=>api.validate(r));}});
test('future review cannot qualify an item today',()=>{const d=register().decisions[0];d.decision='QUALIFIED_FOR_INVESTIGATION';for(const k of api.checks)d.checks[k]='SUPPORTED';d.current_status_date='2026-09-20';d.review_date='2027-01-01';assert.equal(api.qualified(d,now),false);});
test('historical and current filters cannot relabel records',()=>{const q=api.queue(feed(),{projects:[project()]},null,now);assert.equal(api.select(q,'current','Historical').length,0);assert.equal(api.select(q,'history','Halifax').length,1);assert.equal(api.select(q,'qualified').length,0);});
test('unsafe current source cannot create an actionable link',()=>{const s=signal();s.source_url='http://example.org';assert.equal(api.queue(feed([s]),null,null,now).current.length,0);});
test('input source evidence remains unchanged',()=>{const f=feed(),c={projects:[project()]},r=register(),before=JSON.stringify([f,c,r]);api.queue(f,c,r,now);assert.equal(JSON.stringify([f,c,r]),before);});

function completeReview(projectId=id){
  const data=register(),r=data.decisions[0];r.project_id=projectId;r.decision='QUALIFIED_FOR_INVESTIGATION';
  for(const k of api.checks){r.checks[k]='SUPPORTED';r.check_sources[k]=['fixture'];}
  r.current_status_date='2026-09-20';r.current_status_source_id='fixture';return data;
}
test('REGRESSION company-only qualification creates a stable opportunity and dossier identity',()=>{
  const r=completeReview(null),q=api.queue(null,{projects:[]},r,now);
  assert.equal(q.qualified.length,1);assert.equal(q.qualified[0].id,'review:'+sid);assert.equal(q.qualified[0].company_id,sid);
  assert.equal(api.reviewGroups(r).get(sid).review_only,true);assert.equal(q.qualification_count,1);
});
test('REGRESSION old project with recent qualification appears without redating history',()=>{
  const r=completeReview(),p=project('2020-01-01'),before=JSON.stringify(p),q=api.queue(null,{projects:[p]},r,now);
  assert.equal(q.current.length,0);assert.equal(q.qualified.length,1);assert.equal(q.history.length,1);
  assert.equal(q.qualified[0].day,'2020-01-01');assert.equal(q.qualified[0].qualification_evidence.source_publication_date,'2026-09-20');
  assert.equal(JSON.stringify(p),before);assert.equal(q.qualified[0].source_url,p.source.source_url);
});
test('company-only unqualified records stay held and are never legal-parent merged by label',()=>{
  const r=register();r.decisions[0].project_id=null;
  r.decisions.push({...r.decisions[0],id:'d'.repeat(64)});r.decision_count=2;
  const q=api.queue(null,{projects:[]},r,now);assert.equal(q.qualified.length,0);assert.equal(q.current.length,2);
  assert.equal(new Set(q.current.map(x=>x.company_id)).size,2);
});
test('undated company-only evidence does not create a public date or recent item',()=>{
  const r=register();r.decisions[0].project_id=null;r.decisions[0].evidence[0].source_publication_date=null;
  const q=api.queue(null,{projects:[]},r,now);assert.equal(q.current.length,0);assert.equal(q.qualified.length,0);
  assert.equal(api.reviewGroups(r).get(sid).latest_public_date,'');
});
test('company-only qualification expires independently of original publication',()=>{
  const r=completeReview(null),q=api.queue(null,{projects:[]},r,Date.parse('2027-01-01'));assert.equal(q.qualified.length,0);
  assert.equal(api.reviewGroups(r).size,1);
});
test('two reviews cannot silently overwrite one project qualification',()=>{
  const r=register();r.decisions.push({...r.decisions[0],id:'d'.repeat(64)});r.decision_count=2;
  assert.throws(()=>api.validate(r),/duplicate source-local project/);
});
test('qualification never depends on a procurement refresh and never duplicates a recent project',()=>{
  const r=completeReview(),q=api.queue({status:'UNAVAILABLE'}, {projects:[project('2026-09-20')]},r,now);
  assert.equal(q.qualified.length,1);assert.equal(q.current.length,1);assert.equal(q.qualified[0].id,q.current[0].id);
});
test('company-only publication and observation clocks remain separately bound',()=>{
  const r=completeReview(null),d=r.decisions[0];d.evidence.push({...d.evidence[0],source_id:'undated',source_publication_date:null,observed_at:'2026-09-22T21:00:00Z'});
  const before=JSON.stringify(r),q=api.queue(null,{projects:[]},r,now);
  assert.equal(q.current[0].day,'2026-09-20');assert.equal(q.current[0].observed_at,'2026-09-22T00:00:00Z');assert.equal(JSON.stringify(r),before);
});
