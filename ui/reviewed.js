/* Reviewed project histories are not procurement suppliers or predictive alerts. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ABReviewed=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const kinds={PROJECT_ANNOUNCED:'Project announced',OPENING_ANNOUNCED:'Opening announced',INAUGURATION_REPORTED:'Inauguration reported',IMPLEMENTATION_REPORTED:'Implementation reported',OPENING_REPORTED:'Opening reported',OPERATING_BY_DATE:'Operating by this date',PROJECT_COMPLETED_BY_DATE:'Completed by this date',SERVICE_AVAILABLE_BY_DATE:'Service available by this date',OFFICE_ESTABLISHED_BY_DATE:'Office established by this date'};
  const hex=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
  const day=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
  const https=v=>{try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password;}catch(_){return false;}};
  function validate(data){
    if(data?.schema_version!==1||data.status!=='REVIEWED_HISTORY_NOT_CURRENT_ALERTS'||!Array.isArray(data.projects)||data.project_count!==data.projects.length||data.projects.length>100)throw Error('Invalid reviewed evidence catalog');
    const ids=new Set();
    for(const p of data.projects){
      if(!hex(p.id)||ids.has(p.id)||p.status!=='DOCUMENTARY_HISTORY'||p.identity_scope!=='REVIEWED_PROJECT_SOURCE_LOCAL_NOT_LEGAL_PARENT_JOIN')throw Error('Invalid or duplicate reviewed identity');ids.add(p.id);
      for(const k of ['legal_identity_confirmed','first_entry_confirmed','backtest_eligible','public_alert_allowed','independent_holdout'])if(p[k]!==false)throw Error('Unapproved qualification or alert flag');
      for(const k of ['company_name','country','location','title','summary','next_action','reviewer'])if(typeof p[k]!=='string'||!p[k]||p[k].length>4000)throw Error('Missing reviewed field');
      if(!day(p.latest_public_date)||!Array.isArray(p.evidence)||!p.evidence.length||!Array.isArray(p.events)||!p.events.length)throw Error('Missing documentary provenance');
      const refs=new Map();
      for(const e of p.evidence){if(refs.has(e.source_id)||!https(e.source_url)||!day(e.source_publication_date)||!hex(e.raw_sha256)||!Number.isFinite(Date.parse(e.first_observed_at))||!Number.isFinite(Date.parse(e.last_observed_at))||Date.parse(e.first_observed_at)>Date.parse(e.last_observed_at))throw Error('Invalid evidence provenance');refs.set(e.source_id,e);}
      if(!p.evidence.some(e=>p.source?.source_url===e.source_url&&p.source?.source_sha256===e.raw_sha256&&p.source?.observed_at===e.last_observed_at)||p.latest_public_date!==p.evidence.map(e=>e.source_publication_date).sort().at(-1))throw Error('Invalid dossier source metadata');
      for(const e of p.events){const r=refs.get(e.source_id),basis=e.kind.endsWith('_BY_DATE')?'UPPER_BOUND_DAY':['IMPLEMENTATION_REPORTED','OPENING_REPORTED'].includes(e.kind)?'REPORTED_BY_DAY':'SOURCE_ASSERTED_DAY';if(!kinds[e.kind]||!day(e.date)||!r||e.date!==r.source_publication_date||e.date_basis!==basis||e.source_url!==r.source_url||e.raw_sha256!==r.raw_sha256)throw Error('Invalid event/source binding');}
    }
    return data;
  }
  function groups(data){const result=new Map();for(const p of data?.projects||[])result.set(p.id,{...p,reviewed:true,signals:p.events});return result;}
  function monitoringStatus(data,now=Date.now()){
    if(data?.schema_version!==1||!Array.isArray(data.sources)||!['OBSERVED','DEGRADED','BASELINE_ONLY'].includes(data.status))throw Error('Invalid monitoring health');
    const stamp=Date.parse(data.last_attempt_at||'');
    if(!Number.isFinite(stamp)||stamp>now+300000)return 'Monitoring time unverified';
    if(now-stamp>48*3600000)return 'Monitoring check is stale (over 48 hours)';
    return data.status==='DEGRADED'?'Latest monitoring run has source failures':'Latest monitoring run recorded';
  }
  function feedback(value){
    if(!Array.isArray(value)||value.length>1000)throw Error('Invalid local review file');
    const ids=new Set();for(const r of value){if(!hex(r.alert_id)||ids.has(r.alert_id)||typeof r.reviewer!=='string'||!r.reviewer.trim()||r.reviewer.length>100)throw Error('Invalid review identity');ids.add(r.alert_id);for(const k of ['identity_correct','source_supported','useful','already_known'])if(r[k]!==null&&typeof r[k]!=='boolean')throw Error('Invalid review judgment');if(!Number.isFinite(r.review_seconds)||r.review_seconds<0)throw Error('Invalid review duration');}return value;
  }
  return {validate,groups,kinds,monitoringStatus,feedback};
});

let reviewedCatalog=null;
function reviewedProject(id){return reviewedCatalog?.projects.find(p=>p.id===id)||null;}
function workFeedFor(id){const p=reviewedProject(id);if(p)return {source:p.source};const c=typeof ABOpportunities!=='undefined'?ABOpportunities.reviewGroups(typeof opportunityRegister==='undefined'?null:opportunityRegister).get(id):null;return c?{source:c.source}:state.live;}
function renderReviewedProjects(){
  const root=$('reviewed-project-list');if(!root)return;
  if(!reviewedCatalog){root.innerHTML='<p>Reviewed project history is unavailable. Existing procurement signals and saved notes are unaffected.</p>';return;}
  root.innerHTML=reviewedCatalog.projects.map(p=>`<article class="company-notice" data-reviewed-project="${escapeHtml(p.id)}"><div class="work-row-heading"><h3><a class="company-dossier-link" href="${companyHash(p.id)}">${escapeHtml(p.company_name)} — ${escapeHtml(p.location)}</a></h3><span>Latest documentary date: ${escapeHtml(formatDate(p.latest_public_date))}</span></div><p>${escapeHtml(p.title)}</p><p>${escapeHtml(p.summary)}</p><a class="text-link" href="${companyHash(p.id)}">Review evidence and record next action →</a></article>`).join('');
}
function renderReviewedCompany(p){
  const saved=workEntry(p.id),entry=saved||ABWorkspace.blankEntry(p.id,p,workFeedFor(p.id));
  document.title=`${p.company_name} — Reviewed project — AtlanticBridge Signals`;
  const root=$('company-content');
  root.innerHTML=`<div class="page-heading"><div><p class="eyebrow">Company dossier / Reviewed project history</p><h1 id="company-title">${escapeHtml(p.company_name)}</h1><p>${escapeHtml(p.title)} · ${escapeHtml(p.location)}</p></div></div>
  <div class="research-banner"><strong>Documentary history—not a new expansion alert.</strong><span>Country label as published: ${escapeHtml(p.country)}. This source-local project is not a verified legal entity, parent group, or first Canadian entry.</span></div>
  <div class="dossier-columns"><section class="panel dossier-evidence"><div class="panel-header"><div><p class="eyebrow">What is supported</p><h2>The reviewed evidence</h2></div></div><div class="coverage-stack"><p>${escapeHtml(p.summary)}</p><p><strong>What to investigate next:</strong> ${escapeHtml((typeof opportunityRegister!=='undefined'?opportunityRegister?.decisions.find(r=>r.project_id===p.id)?.next_action:null)||p.next_action)}</p><div class="notice">Current project status is not established by this historical review. Source publication dates, observation dates and operating-by bounds are different. Expansion likelihood remains unvalidated.</div></div></section>
  <section class="panel dossier-work"><div class="panel-header"><div><p class="eyebrow">Your work / Browser-local</p><h2>Decide the next action</h2></div></div><form id="company-work-form" class="work-form"><p class="small muted">Your notes are stored in this browser only, not shared with other users. Export a backup to preserve them.</p>
  <label>Research status<select id="work-status">${Object.entries(ABWorkspace.STATUSES).map(([k,v])=>`<option value="${k}"${k===entry.status?' selected':''}>${v}</option>`).join('')}</select></label>
  <label>Next action<input id="work-action" maxlength="500" value="${escapeHtml(entry.next_action)}" placeholder="Record the next verification step"></label>
  <label>Follow-up date<input id="work-date" type="date" value="${escapeHtml(entry.due_date)}"><span class="small muted">Worklist only; no automatic reminder.</span></label>
  <label>Research notes<textarea id="work-notes" rows="5" maxlength="4000">${escapeHtml(entry.notes)}</textarea></label>
  <div class="work-actions"><button class="button primary" id="work-save" type="submit"${workError?' disabled':''}>Save to worklist</button><button class="button" id="work-reload" type="button">Reload saved version</button></div><p id="work-save-state" role="status" aria-live="polite">${saved?'Saved locally.':'Not yet saved to your worklist.'}</p></form></section></div>
  <section class="panel dossier-timeline"><div class="panel-header"><div><p class="eyebrow">Dated primary documents</p><h2>Reviewed event timeline</h2></div></div><div class="coverage-stack">${p.events.map(e=>{const ref=p.evidence.find(r=>r.source_id===e.source_id);return `<article class="company-notice" data-reviewed-event><h3>${escapeHtml(ABReviewed.kinds[e.kind])}</h3><p>${escapeHtml(formatDate(e.date))} · ${escapeHtml(e.date_basis.replaceAll('_',' ').toLowerCase())}</p><a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener noreferrer">Read original source ↗</a><details><summary>Dates and provenance</summary><dl class="notice-facts"><dt>Source publication date</dt><dd>${escapeHtml(ref.source_publication_date)}</dd><dt>First observed in retained proof</dt><dd>${escapeHtml(ref.first_observed_at)}</dd><dt>Last observed in retained proof</dt><dd>${escapeHtml(ref.last_observed_at)}</dd><dt>Source SHA-256</dt><dd>${escapeHtml(ref.raw_sha256)}</dd></dl></details></article>`;}).join('')}</div></section>
  <section class="panel"><div class="panel-header"><div><p class="eyebrow">Pilot feedback / Local only</p><h2>Was this worth investigating?</h2></div></div><form id="review-feedback-form" class="work-form"><p>This records your assessment of the brief, not a validated prediction. No response is sent automatically. Recorded time is elapsed page-view time, including idle time.</p><label>Reviewer label<input id="reviewer-label" maxlength="100" required placeholder="Use a non-sensitive reviewer label"></label><label>Supported by the linked sources?<select id="review-supported"><option value="">Not assessed</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Useful for your work?<select id="review-useful"><option value="">Not assessed</option><option value="true">Yes</option><option value="false">No</option></select></label><label>Already known to you?<select id="review-known"><option value="">Not assessed</option><option value="true">Yes</option><option value="false">No</option></select></label><div class="work-actions"><button class="button" type="submit">Save local feedback</button><button class="button" id="review-export" type="button">Export feedback JSON</button></div><p id="review-feedback-state" role="status"></p></form></section>`;
  $('company-work-form').addEventListener('input',()=>{workDirty=true;$('work-save-state').textContent='Unsaved changes.';});
  $('company-work-form').addEventListener('submit',saveCompanyWork);
  $('work-reload').addEventListener('click',()=>{if(workDirty&&!confirm('Discard this draft and reload the saved version?'))return;initializeWorklist();renderCompany(p.id);});
  const started=Date.now(),key='atlanticbridge.pilot-feedback.v1';
  const read=()=>ABReviewed.feedback(JSON.parse(localStorage.getItem(key)||'[]'));
  $('review-feedback-form').addEventListener('submit',event=>{event.preventDefault();try{const raw=localStorage.getItem(key),old=ABReviewed.feedback(JSON.parse(raw||'[]'));const judgment=id=>$(id).value===''?null:$(id).value==='true';const record={alert_id:p.id,reviewer:$('reviewer-label').value.trim(),identity_correct:null,source_supported:judgment('review-supported'),useful:judgment('review-useful'),already_known:judgment('review-known'),review_seconds:Math.max(0,Math.round((Date.now()-started)/1000)),timing_basis:'ELAPSED_PAGE_VIEW_INCLUDES_IDLE'};const data=ABReviewed.feedback([...old.filter(r=>r.alert_id!==p.id),record]);if(localStorage.getItem(key)!==raw)throw Error('Feedback changed in another tab; reload before saving.');localStorage.setItem(key,JSON.stringify(data));$('review-feedback-state').textContent='Saved in this browser. Nothing was submitted to a server.';}catch(error){$('review-feedback-state').textContent='Not saved. '+error.message;}});
  $('review-export').addEventListener('click',()=>{try{const data=read();const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='atlanticbridge-pilot-feedback.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){$('review-feedback-state').textContent='Export unavailable. '+error.message;}});
}
async function loadMonitoringHealth(){
  const target=$('monitoring-status'),button=$('monitoring-refresh');button.disabled=true;target.textContent='Reading the retained monitoring history…';
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
  try{const response=await fetch('https://raw.githubusercontent.com/JeremyHennessy/AtlanticBridge-Signals/monitoring-state/health.json',{cache:'no-store',signal:controller.signal});if(!response.ok)throw Error('Monitoring state unavailable');const data=await response.json();const label=ABReviewed.monitoringStatus(data);target.innerHTML=`<p><strong>${escapeHtml(label)}</strong> · Last attempt: ${escapeHtml(data.last_attempt_at||'Not established')}</p><p>${escapeHtml(data.consecutive_successful_days)} consecutive successful UTC day(s) of the 14-day operational target. No prediction has been validated.</p>${data.sources.map(s=>`<p><a class="source-link" href="${escapeHtml(safeUrl(s.source_url)||'#')}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.id)}</a> · ${s.status==='OBSERVED'?`${escapeHtml(s.records)} records observed`:'Source failed; coverage unverified'} · Last success: ${escapeHtml(s.last_success_at||'Unknown')}</p>`).join('')}<p class="small muted">${escapeHtml(data.retention)}</p>`;}catch(_){target.textContent='Monitoring history could not be loaded. No zero-record or healthy-source result is inferred. Reviewed histories and saved notes remain available.';}finally{clearTimeout(timer);button.disabled=false;}
}
