/* Read-only projection of the existing metadata checkpoint. Never a collector. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ABMonitorReview=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const HEX=/^[a-f0-9]{64}$/,DAY=86400000,MAX=16*1024*1024;
  const facts=new Set(['id','source_id','source_record_id','source_url','source_publication_date','publication_precision','publication_clock','source_updated_at','first_observed_at','last_observed_at','raw_sha256','canada_relevance','scope_exclusion','backtest_eligible','public_alert_allowed']);
  function keys(o,wanted){return o&&typeof o==='object'&&!Array.isArray(o)&&Object.keys(o).sort().join('|')===[...wanted].sort().join('|');}
  function stamp(v){if(typeof v!=='string'||!/(Z|[+-]\d\d:\d\d)$/.test(v)||!Number.isFinite(Date.parse(v)))throw Error('Invalid source clock');return Date.parse(v);}
  function https(v){try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password;}catch(_){return false;}}
  function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
  function project(c,register,now=Date.now()){
    if(!Number.isFinite(now)||!keys(c,['schema_version','tables','runs','raw_retention_days','historical_backtest_eligible','checksum'])||c.schema_version!==1||!HEX.test(c.checksum)||c.historical_backtest_eligible!==false||c.raw_retention_days!==90)throw Error('Unsupported checkpoint');
    if(!keys(c.tables,['company_source_state','company_observations','company_observation_events'])||!Array.isArray(c.runs)||!c.runs.length||c.runs.length>10000)throw Error('Invalid retained history');
    for(const rows of Object.values(c.tables))if(!Array.isArray(rows)||rows.length>100000)throw Error('Oversized source state');
    const sources=new Map(),observations=new Set(),events=new Set(),runIds=new Set();
    for(const s of c.tables.company_source_state){if(!keys(s,['id','contract','last_success'])||!s.id||sources.has(s.id)||!HEX.test(s.contract)||stamp(s.last_success)>now+300000)throw Error('Invalid source identity');sources.set(s.id,s);}
    function record(r,sid){
      if(!r||Object.keys(r).some(k=>!facts.has(k))||!HEX.test(r.id)||!HEX.test(r.raw_sha256)||r.source_id!==sid||!sources.has(sid)||r.public_alert_allowed!==false||r.backtest_eligible!==false||!https(r.source_url))throw Error('Invalid review metadata');
      if(stamp(r.first_observed_at)>stamp(r.last_observed_at)||stamp(r.last_observed_at)>now+300000)throw Error('Invalid observation clocks');
      if(r.source_publication_date!==null){const v=r.source_publication_date;if(typeof v!=='string'||!Number.isFinite(Date.parse(v))||Date.parse(v)>now+300000)throw Error('Invalid publication clock');if(/^\d{4}-\d{2}-\d{2}$/.test(v)&&new Date(v).toISOString().slice(0,10)!==v)throw Error('Invalid publication day');}
    }
    for(const o of c.tables.company_observations){
      if(!keys(o,['id','source_id','first_seen','last_seen','fingerprint','payload'])||observations.has(o.id)||!HEX.test(o.fingerprint)||typeof o.payload!=='string')throw Error('Invalid observation');
      const r=JSON.parse(o.payload);record(r,o.source_id);if(o.id!==r.id||o.first_seen!==r.first_observed_at||o.last_seen!==r.last_observed_at)throw Error('Observation provenance mismatch');observations.add(o.id);
    }
    let latest=null;
    for(const run of c.runs){if(!run.id||runIds.has(run.id)||!Array.isArray(run.sources)||stamp(run.finished_at)>now+300000)throw Error('Invalid run history');runIds.add(run.id);if(!latest||stamp(run.finished_at)>stamp(latest.finished_at))latest=run;}
    const status=new Map(latest.sources.map(s=>[s.id,s.status]));
    const bindings=new Map();
    for(const r of register?.decisions||[]){if(!HEX.test(r.id)||!Array.isArray(r.evidence))throw Error('Invalid company review binding');for(const e of r.evidence){if(!bindings.has(e.source_id))bindings.set(e.source_id,new Map());bindings.get(e.source_id).set(r.id,r);}}
    const items=[],counts={total_events:0,scope_held:0,unbound:0,geography_unconfirmed:0,older_than_30_days:0};
    for(const e of c.tables.company_observation_events){
      if(!keys(e,['id','source_id','observed_at','kind','payload'])||!HEX.test(e.id)||events.has(e.id)||typeof e.payload!=='string')throw Error('Invalid event identity');events.add(e.id);
      const p=JSON.parse(e.payload),r=p.record;
      if(!keys(p,['id','kind','observed_at','public_alert_allowed','review_required','record'])||p.id!==e.id||p.kind!==e.kind||p.observed_at!==e.observed_at||!['NEWLY_OBSERVED_RECORD','RECORD_CHANGED'].includes(e.kind)||p.public_alert_allowed!==false||p.review_required!==true)throw Error('Invalid review-only event');
      record(r,e.source_id);if(!observations.has(r.id)||stamp(e.observed_at)!==stamp(r.last_observed_at)||stamp(e.observed_at)>stamp(latest.finished_at))throw Error('Orphan or mistimed event');
      counts.total_events++;
      // No suppressed record is deleted from the checkpoint. These are routing counts.
      if(r.scope_exclusion!==null){counts.scope_held++;continue;}
      if(r.canada_relevance!=='CANDIDATE_REQUIRES_REVIEW'){counts.geography_unconfirmed++;continue;}
      const matches=bindings.get(e.source_id);
      if(!matches||matches.size!==1){counts.unbound++;continue;}
      if(now-stamp(e.observed_at)>30*DAY){counts.older_than_30_days++;continue;}
      const review=[...matches.values()][0];
      items.push({id:e.id,record_id:r.id,source_id:e.source_id,company_id:review.project_id||review.id,company_name:review.company_name,
        event_kind:e.kind,observed_at:e.observed_at,first_observed_at:r.first_observed_at,source_publication_date:r.source_publication_date,publication_clock:r.publication_clock,
        source_url:r.source_url,raw_sha256:r.raw_sha256,source_status:status.get(e.source_id)||'UNVERIFIED',source_reuse:review.checks?.source_reuse||'UNKNOWN',qualified:false,public_alert_allowed:false});
    }
    items.sort((a,b)=>b.observed_at.localeCompare(a.observed_at)||a.id.localeCompare(b.id));
    return {checkpoint_checksum:c.checksum,last_collection_at:latest.finished_at,last_run_id:latest.id,stale:now-stamp(latest.finished_at)>2*DAY,
      failed_sources:latest.sources.filter(s=>s.status!=='OBSERVED').map(s=>s.id),counts,total_routable:items.length,items:items.slice(0,200),register_available:Boolean(register)};
  }
  async function parse(raw,register,now=Date.now()){
    if(typeof raw!=='string'||new TextEncoder().encode(raw).length>MAX)throw Error('Checkpoint download exceeds bound');
    const c=JSON.parse(raw),content={...c};delete content.checksum;
    const cryptoApi=typeof require==='function'?require('node:crypto').webcrypto:globalThis.crypto;
    const hash=[...new Uint8Array(await cryptoApi.subtle.digest('SHA-256',new TextEncoder().encode(canonical(content))))].map(b=>b.toString(16).padStart(2,'0')).join('');
    if(hash!==c.checksum)throw Error('Checkpoint checksum mismatch');
    return project(c,register,now);
  }
  const sourceLinkAllowed=item=>item?.source_reuse!=='CONTRADICTED';
  return {parse,project,canonical,sourceLinkAllowed};
});

async function loadMonitorReview(){
  const button=$('monitor-review-load'),status=$('monitor-review-status'),list=$('monitor-review-list');
  button.disabled=true;status.textContent='Reading the retained metadata checkpoint…';list.innerHTML='';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),15000);
  try{
    const response=await fetch('https://raw.githubusercontent.com/JeremyHennessy/AtlanticBridge-Signals/monitoring-state/checkpoint.json',{cache:'no-store',signal:controller.signal});
    if(!response.ok)throw Error('Checkpoint unavailable');
    const declared=Number(response.headers.get('Content-Length')||0);if(declared>16*1024*1024)throw Error('Checkpoint exceeds bound');
    const model=await ABMonitorReview.parse(await response.text(),opportunityRegister);
    status.textContent=`${model.stale?'Stale collection—review with caution. ':''}${model.failed_sources.length?'Latest run has source failures. ':''}Collected ${model.last_collection_at}. ${model.counts.total_events} retained changes; ${model.items.length} shown for source-bound review. ${model.counts.scope_held} scope-held; ${model.counts.geography_unconfirmed} without established Canadian relevance; ${model.counts.unbound} without one reviewed company binding; ${model.counts.older_than_30_days} older than 30 days. ${model.total_routable>200?'Only the latest 200 routable events are shown. ':''}${!model.register_available?'Company review register unavailable; no identity joins inferred. ':''}Observation time is not publication time. No change is a qualified opportunity.`;
    list.innerHTML=model.items.map(r=>`<article class="company-notice" data-monitor-review-item="${escapeHtml(r.id)}"><h3>${escapeHtml(r.company_name)} · ${r.event_kind==='RECORD_CHANGED'?'Retained record changed':'Record newly observed'}</h3><p class="small muted">${escapeHtml(r.source_id)} · Source state: ${escapeHtml(r.source_status)}</p><dl class="notice-facts"><dt>Change observed</dt><dd>${escapeHtml(r.observed_at)}</dd><dt>Record first observed</dt><dd>${escapeHtml(r.first_observed_at)}</dd><dt>Source publication value</dt><dd>${escapeHtml(r.source_publication_date||'Unknown; not replaced by observation time')}</dd><dt>Publication clock meaning</dt><dd>${escapeHtml(r.publication_clock)}</dd><dt>Retained raw SHA-256</dt><dd>${escapeHtml(r.raw_sha256)}</dd></dl><p>Metadata only. This is not proof that a vacancy is still open, a new Canadian entry, or a commercial requirement. Source reuse remains ${escapeHtml(r.source_reuse.toLowerCase())}.</p><p><strong>Next action:</strong> Check the original record, confirm current Canadian activity and civilian scope, then record the decision in the company worklist.</p><div class="work-actions"><a class="button" href="${companyHash(r.company_id)}">Open company review and record action →</a>${ABMonitorReview.sourceLinkAllowed(r)?`<a class="source-link" href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener noreferrer">Original record ↗</a>`:`<span class="small muted">Corporate-source link withheld pending the recorded source-use review.</span>`}</div></article>`).join('')||'<p>No changes are routable under these review rules. This does not establish no company activity; held and unbound records remain in the retained checkpoint.</p>';
    list.dataset.checksum=model.checkpoint_checksum;
  }catch(error){status.textContent='Monitored changes unavailable or invalid. No zero-activity result is inferred. Other evidence and saved work are unchanged.';list.removeAttribute('data-checksum');}
  finally{clearTimeout(timer);button.disabled=false;}
}
