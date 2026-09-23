/* A decision queue, not a new source collector or a probability model. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ABOpportunities=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const DAY=86400000, HEX=/^[a-f0-9]{64}$/;
  const date=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
  const text=(v,max=4000)=>typeof v==='string'&&v.trim().length>0&&v.length<=max;
  const https=v=>{try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password;}catch(_){return false;}};
  const age=(day,now)=>date(day)?Math.floor((Date.parse(new Date(now).toISOString().slice(0,10))-Date.parse(day))/DAY):null;
  const checks=['legal_identity','corporate_group','civilian_scope','canadian_relevance','current_status','source_reuse'];
  function validate(data){
    if(data?.schema_version!==1||data.status!=='REVIEW_REGISTER_NOT_PREDICTIONS'||!Array.isArray(data.decisions)||data.decisions.length>200||data.decision_count!==data.decisions.length)throw Error('Invalid company review register');
    const ids=new Set(), projects=new Set();
    for(const r of data.decisions){
      if(!HEX.test(r.id)||ids.has(r.id))throw Error('Invalid or duplicate review identity');ids.add(r.id);
      if(!['HOLD','QUALIFIED_FOR_INVESTIGATION','OUT_OF_SCOPE'].includes(r.decision)||!text(r.company_name,1000)||!text(r.reason)||!text(r.next_action)||!text(r.reviewer,100)||!date(r.review_date))throw Error('Invalid review decision');
      for(const k of checks)if(!['SUPPORTED','UNKNOWN','CONTRADICTED'].includes(r.checks?.[k]))throw Error('Unreviewed qualification check');
      if(r.decision==='QUALIFIED_FOR_INVESTIGATION'&&checks.some(k=>r.checks[k]!=='SUPPORTED'))throw Error('A held check cannot be qualified');
      if(r.decision==='OUT_OF_SCOPE'&&r.checks.civilian_scope!=='CONTRADICTED'&&r.checks.canadian_relevance!=='CONTRADICTED')throw Error('Exclusion lacks an explicit scope decision');
      if(!Array.isArray(r.evidence)||r.evidence.length===0)throw Error('Decision lacks retained evidence');
      const refs=new Map();
      for(const e of r.evidence){if(!text(e.source_id,200)||refs.has(e.source_id)||!https(e.source_url)||!HEX.test(e.raw_sha256)||!Number.isFinite(Date.parse(e.observed_at))||(e.source_publication_date!==null&&!date(e.source_publication_date)))throw Error('Invalid decision provenance');refs.set(e.source_id,e);}
      for(const k of checks){const ids=r.check_sources?.[k];if(!Array.isArray(ids)||new Set(ids).size!==ids.length||ids.some(id=>!refs.has(id))||(r.checks[k]==='SUPPORTED'&&!ids.length))throw Error('Qualification check lacks source binding');}
      if(r.project_id!==null){if(!HEX.test(r.project_id)||projects.has(r.project_id))throw Error('Invalid or duplicate source-local project link');projects.add(r.project_id);}
      if(r.first_entry_confirmed!==false||r.predictive_score_allowed!==false||r.independent_holdout!==false)throw Error('Qualification is not prediction or independent holdout approval');
      if(r.decision==='QUALIFIED_FOR_INVESTIGATION'&&(!date(r.current_status_date)||!text(r.current_status_source_id,200)||!r.check_sources.current_status.includes(r.current_status_source_id)||refs.get(r.current_status_source_id)?.source_publication_date!==r.current_status_date||r.current_status_date>r.review_date))throw Error('Qualification needs a bound dated current-status source');
    }
    return data;
  }
  function qualified(r,now){
    // Even a once-qualified decision becomes review-only when its current-status evidence ages.
    const a=age(r.current_status_date,now), reviewed=age(r.review_date,now);
    return r.decision==='QUALIFIED_FOR_INVESTIGATION'&&checks.every(k=>r.checks[k]==='SUPPORTED')&&a!==null&&a>=0&&a<=90&&reviewed!==null&&reviewed>=0&&reviewed<=90;
  }
  function latestEvidence(r,now=Date.now()){
    // Publication and observation are independent clocks. Undated pages stay undated.
    const refs=r.evidence.filter(e=>date(e.source_publication_date)&&age(e.source_publication_date,now)>=0);
    return [...(refs.length?refs:r.evidence)].sort((a,b)=>String(b.source_publication_date||'').localeCompare(String(a.source_publication_date||''))||a.source_id.localeCompare(b.source_id))[0];
  }
  function reviewGroups(data,now=Date.now()){
    const groups=new Map();
    for(const r of data?.decisions||[]){
      if(r.project_id!==null)continue;
      const ref=latestEvidence(r,now);
      groups.set(r.id,{id:r.id,company_name:r.company_name,country:'',review_only:true,signals:r.evidence,
        latest_public_date:date(ref.source_publication_date)?ref.source_publication_date:'',
        source:{source_url:ref.source_url,source_sha256:ref.raw_sha256,observed_at:ref.observed_at},decision:r});
    }
    return groups;
  }
  function queue(live,catalog,register,now=Date.now()){
    if(!Number.isFinite(now))throw Error('Invalid queue clock');
    if(register)validate(register);
    const decisions=new Map((register?.decisions||[]).filter(r=>r.project_id!==null).map(r=>[r.project_id,r]));
    const current=[],history=[],qualifiedRows=[];
    const active=live?.status==='ACTIVE'&&Array.isArray(live.signals);
    const statusEvidence=r=>r?.evidence.find(e=>e.source_id===r.current_status_source_id)||null;
    if(active)for(const s of live.signals){
      const a=age(s.publicly_available_date,now);if(a===null||a<0||a>90)continue;
      if(!HEX.test(s.id)||!HEX.test(s.company_id)||!https(s.source_url))continue;
      current.push({id:'notice:'+s.id,company_id:s.company_id,company_name:s.company_name,title:s.title||s.award_description||'Canadian federal award notice',day:s.publicly_available_date,
        location:s.regions_of_delivery||'Delivery location unverified',kind:'Procurement evidence',what:s.signal_kind==='FEDERAL_AWARD_AMENDED'?'A federal award notice was amended.':'A federal award notice was published.',
        why:s.why_surfaced||'A named supplier has a Canadian-buyer relationship. This does not establish a Canadian office or a new market entry.',
        next_action:s.scope_review?.state==='INCLUDED_CANADIAN_DELIVERY'?'Check the supplier identity, award amendments and whether the Canadian delivery creates a relevant follow-on opportunity.':'Confirm Canadian delivery or activity before treating the buyer relationship as a Canadian expansion opportunity.',
        source_url:s.source_url,observed_at:live.source?.observed_at||null,raw_sha256:s.source_sha256||live.source?.source_sha256||null,qualified:false,decision:null});
    }
    if(catalog)for(const p of catalog.projects||[]){
      const r=decisions.get(p.id),a=age(p.latest_public_date,now);
      const row={id:'project:'+p.id,company_id:p.id,company_name:p.company_name,title:p.title,day:p.latest_public_date,location:p.location,kind:'Reviewed documentary evidence',what:p.summary,
        why:'A source-local Canadian project merits an explicit current-status and identity review. Documentary history is not a new automated alert.',next_action:r?.next_action||p.next_action,
        source_url:p.source.source_url,observed_at:p.source.observed_at,raw_sha256:p.source.source_sha256,qualified:r?qualified(r,now):false,decision:r||null,qualification_evidence:statusEvidence(r)};
      history.push(row);
      if(a!==null&&a>=0&&a<=90)current.push(row);
      // Current qualification is independent of the original announcement's age.
      // Keep the original date/source unchanged instead of manufacturing a new event.
      if(row.qualified)qualifiedRows.push(row);
    }
    for(const c of reviewGroups(register,now).values()){
      const r=c.decision,ref=latestEvidence(r,now),a=age(ref.source_publication_date,now);
      const row={id:'review:'+r.id,company_id:r.id,company_name:r.company_name,title:'Company evidence review',day:ref.source_publication_date,
        location:'Canadian location requires source-specific review',kind:'Company review evidence',what:r.reason,
        why:'A source-bound company review, not an automatic legal-parent join or first-entry finding.',next_action:r.next_action,
        source_url:ref.source_url,observed_at:ref.observed_at,raw_sha256:ref.raw_sha256,qualified:qualified(r,now),decision:r,qualification_evidence:statusEvidence(r)};
      if(a!==null&&a>=0&&a<=90)current.push(row);
      if(row.qualified)qualifiedRows.push(row);
    }
    const sort=(a,b)=>String(b.day||'').localeCompare(String(a.day||''))||a.id.localeCompare(b.id);
    current.sort(sort);history.sort(sort);
    qualifiedRows.sort((a,b)=>b.decision.current_status_date.localeCompare(a.decision.current_status_date)||a.id.localeCompare(b.id));
    return {current,history,qualified:qualifiedRows,source_available:active,history_available:Boolean(catalog),review_available:Boolean(register),reviewed_decisions:register?.decisions.length??null,qualification_count:register&&catalog?qualifiedRows.length:null};
  }
  function select(model,view,query=''){
    const rows=view==='history'?model.history:view==='qualified'?model.qualified:model.current;
    const q=String(query).trim().toLocaleLowerCase();return rows.filter(r=>!q||[r.company_name,r.title,r.location,r.what,r.next_action].join(' ').toLocaleLowerCase().includes(q));
  }
  return {validate,qualified,queue,select,checks,latestEvidence,reviewGroups};
});

let opportunityRegister=null;
function renderOpportunityQueue(params=new URLSearchParams(location.hash.split('?')[1]||'')){
  const model=ABOpportunities.queue(state.live,reviewedCatalog,opportunityRegister),view=['qualified','history'].includes(params.get('view'))?params.get('view'):'current',query=params.get('q')||'';
  const rows=ABOpportunities.select(model,view,query);
  $('opportunity-search').value=query;
  document.querySelectorAll('[data-opportunity-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.opportunityView===view)));
  $('opportunity-current-count').textContent=model.source_available||model.history_available?String(model.current.length):'Unverified';
  $('opportunity-qualified-count').textContent=model.qualification_count!==null?String(model.qualification_count):'Unverified';
  $('opportunity-history-count').textContent=model.history_available?String(model.history.length):'Unverified';
  const missing=[];if(!model.source_available)missing.push('Current procurement source unavailable');if(!model.history_available)missing.push('Project histories unavailable');if(!model.review_available)missing.push('Company review register unavailable');
  $('opportunity-coverage').textContent=missing.length?missing.join(' · ')+'. Missing coverage is not zero activity. Saved work is unchanged.':'Public dates determine recency. A new source check does not make an old event new. Qualification is for investigation—not expansion prediction.';
  $('opportunity-count').textContent=`${rows.length} evidence item${rows.length===1?'':'s'} in this view · ${new Set(rows.map(r=>r.company_id)).size} source-local compan${new Set(rows.map(r=>r.company_id)).size===1?'y':'ies'}`;
  $('opportunity-list').innerHTML=rows.length?rows.map(r=>`<article class="company-notice" data-opportunity-id="${escapeHtml(r.id)}"><div class="work-row-heading"><h3><a class="company-dossier-link" href="${companyHash(r.company_id)}">${escapeHtml(r.company_name)}</a></h3><span class="status-chip ${r.qualified?'status-establishment':'status-unresolved'}">${r.qualified?'Qualified for investigation':view==='history'?'Historical context':'Needs review'}</span></div><p><strong>${escapeHtml(r.title)}</strong> · ${escapeHtml(r.location)}</p><p class="small muted">${escapeHtml(r.kind)} · Public document: ${escapeHtml(formatDate(r.day))}</p>${view==='qualified'&&r.qualification_evidence?`<p class="small">Qualification status evidence: ${escapeHtml(formatDate(r.decision.current_status_date))} · <a class="source-link" href="${escapeHtml(r.qualification_evidence.source_url)}" target="_blank" rel="noopener noreferrer">Read status source ↗</a>. The original document date is unchanged.</p>`:''}<p><strong>What changed or was documented:</strong> ${escapeHtml(r.what)}</p><p><strong>Why investigate:</strong> ${escapeHtml(r.why)}</p><p><strong>Next action:</strong> ${escapeHtml(r.next_action)}</p><div class="work-actions"><a class="button" href="${companyHash(r.company_id)}">Open dossier and record action →</a><a class="source-link" href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a></div><details><summary>Evidence and qualification details</summary><dl class="notice-facts"><dt>Source observation</dt><dd>${escapeHtml(r.observed_at||'Unverified')}</dd><dt>Retained source SHA-256</dt><dd>${escapeHtml(r.raw_sha256||'Unverified')}</dd><dt>First Canadian entry</dt><dd>Not established by this queue</dd></dl>${r.decision?`<p>${escapeHtml(r.decision.reason)}</p><dl class="notice-facts">${ABOpportunities.checks.map(k=>`<dt>${escapeHtml(k.replaceAll('_',' '))}</dt><dd>${escapeHtml(r.decision.checks[k].toLowerCase())}</dd>`).join('')}</dl>`:'<p>Full legal identity, ownership, scope, current status and source-reuse review has not been completed for this item.</p>'}</details></article>`).join(''):`<div class="empty-state"><h3>${query?'No evidence matches this search.':view==='qualified'?(model.qualification_count!==null?'No loaded current item has passed every qualification check.':'Qualification coverage is unavailable.'):'No evidence is available in this view.'}</h3><p>${view==='qualified'?'Review-held records remain in the recent-evidence or historical-context views. This is not a finding of no Canadian activity.':'Try the other views. Missing or unavailable coverage remains unknown.'}</p></div>`;
  const register=$('opportunity-review-register');
  register.innerHTML=!opportunityRegister?'<p>The company-review register could not be loaded; no decisions are inferred.</p>':`<p>${opportunityRegister.decisions.length} documented review decisions. A hold is not a rejection and is not a qualified opportunity.</p>`+opportunityRegister.decisions.map(r=>`<article class="company-notice" data-review-decision="${escapeHtml(r.id)}"><h3><a class="company-dossier-link" href="${companyHash(r.project_id||r.id)}">${escapeHtml(r.company_name)}</a> · ${escapeHtml(r.decision.replaceAll('_',' ').toLowerCase())}</h3><p>${escapeHtml(r.reason)}</p><p><strong>Next action:</strong> ${escapeHtml(r.next_action)}</p><details><summary>Decision evidence and checks</summary><p>Reviewed ${escapeHtml(r.review_date)} by ${escapeHtml(r.reviewer)}.</p><dl class="notice-facts">${ABOpportunities.checks.map(k=>`<dt>${escapeHtml(k.replaceAll('_',' '))}</dt><dd>${escapeHtml(r.checks[k].toLowerCase())}</dd>`).join('')}</dl>${r.evidence.map(e=>`<p><a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a> · Observed ${escapeHtml(e.observed_at)}</p>`).join('')}</details></article>`).join('');
}
function bindOpportunityQueue(){
  const change=(view,query)=>{const p=new URLSearchParams();if(view!=='current')p.set('view',view);if(query)p.set('q',query);history.replaceState(null,'',`#opportunities${p.size?'?'+p:''}`);renderOpportunityQueue(p);};
  $('opportunity-search').addEventListener('input',()=>{const p=new URLSearchParams(location.hash.split('?')[1]||'');change(p.get('view')||'current',$('opportunity-search').value);});
  document.querySelectorAll('[data-opportunity-view]').forEach(b=>b.addEventListener('click',()=>change(b.dataset.opportunityView,$('opportunity-search').value)));
  $('opportunity-reset').addEventListener('click',()=>change('current',''));
}

function companyOnlyReview(id){return opportunityRegister?.decisions.find(r=>r.project_id===null&&r.id===id)||null;}
function renderCompanyReview(r){
  const company=ABOpportunities.reviewGroups(opportunityRegister).get(r.id);
  const saved=workEntry(r.id),entry=saved||ABWorkspace.blankEntry(r.id,company,workFeedFor(r.id));
  const isQualified=ABOpportunities.qualified(r,Date.now());
  document.title=`${r.company_name} — Company review — AtlanticBridge Signals`;
  $('company-content').innerHTML=`<div class="page-heading"><div><p class="eyebrow">Company dossier / Source-bound company review</p><h1 id="company-title">${escapeHtml(r.company_name)}</h1><p>Source-local review identity. Not a procurement supplier or automatic corporate-group join.</p></div></div>
  <div class="research-banner"><strong>${isQualified?'Qualified for investigation':'Needs review'}</strong><span>First Canadian entry and expansion probability are not established. A qualified investigation is not proof of commercial demand.</span></div>
  <div class="dossier-columns"><section class="panel dossier-evidence"><div class="panel-header"><div><p class="eyebrow">What is supported</p><h2>The company review</h2></div></div><div class="coverage-stack"><p>${escapeHtml(r.reason)}</p><p><strong>What to investigate next:</strong> ${escapeHtml(r.next_action)}</p><dl class="notice-facts"><dt>Review date</dt><dd>${escapeHtml(r.review_date)}</dd><dt>Dated current-status evidence</dt><dd>${escapeHtml(r.current_status_date||'Not established; observation is not publication')}</dd>${ABOpportunities.checks.map(k=>`<dt>${escapeHtml(k.replaceAll('_',' '))}</dt><dd>${escapeHtml(r.checks[k].toLowerCase())}</dd>`).join('')}</dl></div></section>
  <section class="panel dossier-work"><div class="panel-header"><div><p class="eyebrow">Your work / Browser-local</p><h2>Decide the next action</h2></div></div><form id="company-work-form" class="work-form"><p class="small muted">Your notes are stored in this browser only. Saving an action does not approve the company, source rights or a prediction. Export a backup to preserve them.</p>
  <label>Research status<select id="work-status">${Object.entries(ABWorkspace.STATUSES).map(([k,v])=>`<option value="${k}"${k===entry.status?' selected':''}>${v}</option>`).join('')}</select></label>
  <label>Next action<input id="work-action" maxlength="500" value="${escapeHtml(entry.next_action)}" placeholder="Record the next verification step"></label>
  <label>Follow-up date<input id="work-date" type="date" value="${escapeHtml(entry.due_date)}"><span class="small muted">Worklist only; no automatic reminder.</span></label>
  <label>Research notes<textarea id="work-notes" rows="5" maxlength="4000">${escapeHtml(entry.notes)}</textarea></label>
  <div class="work-actions"><button class="button primary" id="work-save" type="submit"${workError?' disabled':''}>Save to worklist</button><button class="button" id="work-reload" type="button">Reload saved version</button></div><p id="work-save-state" role="status" aria-live="polite">${saved?'Saved locally.':'Not yet saved to your worklist.'}</p></form></section></div>
  <section class="panel dossier-timeline"><div class="panel-header"><div><p class="eyebrow">Original sources / Separate clocks</p><h2>Review evidence and provenance</h2></div></div><div class="coverage-stack">${r.evidence.map(e=>`<article class="company-notice" data-company-review-evidence="${escapeHtml(e.source_id)}"><h3>${escapeHtml(e.source_id)}</h3><p>Public document: ${escapeHtml(formatDate(e.source_publication_date))} · Observed: ${escapeHtml(e.observed_at)}</p><a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener noreferrer">Read original source ↗</a><details><summary>Provenance and supported checks</summary><dl class="notice-facts"><dt>Retained source SHA-256</dt><dd>${escapeHtml(e.raw_sha256)}</dd><dt>Bound review checks</dt><dd>${escapeHtml(ABOpportunities.checks.filter(k=>r.check_sources[k].includes(e.source_id)).join(', ')||'Context only; no check cleared')}</dd></dl></details></article>`).join('')}</div></section>`;
  $('company-work-form').addEventListener('input',()=>{workDirty=true;$('work-save-state').textContent='Unsaved changes.';});
  $('company-work-form').addEventListener('submit',saveCompanyWork);
  $('work-reload').addEventListener('click',()=>{if(workDirty&&!confirm('Discard this draft and reload the saved version?'))return;initializeWorklist();renderCompany(r.id);});
}
