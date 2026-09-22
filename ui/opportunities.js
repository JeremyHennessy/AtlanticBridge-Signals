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
    const ids=new Set();
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
      if(r.project_id!==null&&!HEX.test(r.project_id))throw Error('Invalid source-local project link');
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
  function queue(live,catalog,register,now=Date.now()){
    if(!Number.isFinite(now))throw Error('Invalid queue clock');
    if(register)validate(register);
    const decisions=new Map((register?.decisions||[]).map(r=>[r.project_id,r]));
    const current=[],history=[];
    const active=live?.status==='ACTIVE'&&Array.isArray(live.signals);
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
        source_url:p.source.source_url,observed_at:p.source.observed_at,raw_sha256:p.source.source_sha256,qualified:r?qualified(r,now):false,decision:r||null};
      history.push(row);
      // A recent public document can be surfaced for review without relabelling old events as new.
      if(a!==null&&a>=0&&a<=90)current.push(row);
    }
    const sort=(a,b)=>b.day.localeCompare(a.day)||a.id.localeCompare(b.id);
    current.sort(sort);history.sort(sort);
    return {current,history,qualified:current.filter(r=>r.qualified),source_available:active,history_available:Boolean(catalog),review_available:Boolean(register),reviewed_decisions:register?.decisions.length??null,qualification_count:register&&catalog?current.filter(r=>r.qualified).length:null};
  }
  function select(model,view,query=''){
    const rows=view==='history'?model.history:view==='qualified'?model.qualified:model.current;
    const q=String(query).trim().toLocaleLowerCase();return rows.filter(r=>!q||[r.company_name,r.title,r.location,r.what,r.next_action].join(' ').toLocaleLowerCase().includes(q));
  }
  return {validate,qualified,queue,select,checks};
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
  $('opportunity-list').innerHTML=rows.length?rows.map(r=>`<article class="company-notice" data-opportunity-id="${escapeHtml(r.id)}"><div class="work-row-heading"><h3><a class="company-dossier-link" href="${companyHash(r.company_id)}">${escapeHtml(r.company_name)}</a></h3><span class="status-chip ${r.qualified?'status-establishment':'status-unresolved'}">${r.qualified?'Qualified for investigation':view==='history'?'Historical context':'Needs review'}</span></div><p><strong>${escapeHtml(r.title)}</strong> · ${escapeHtml(r.location)}</p><p class="small muted">${escapeHtml(r.kind)} · Public document: ${escapeHtml(formatDate(r.day))}</p><p><strong>What changed or was documented:</strong> ${escapeHtml(r.what)}</p><p><strong>Why investigate:</strong> ${escapeHtml(r.why)}</p><p><strong>Next action:</strong> ${escapeHtml(r.next_action)}</p><div class="work-actions"><a class="button" href="${companyHash(r.company_id)}">Open dossier and record action →</a><a class="source-link" href="${escapeHtml(r.source_url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a></div><details><summary>Evidence and qualification details</summary><dl class="notice-facts"><dt>Source observation</dt><dd>${escapeHtml(r.observed_at||'Unverified')}</dd><dt>Retained source SHA-256</dt><dd>${escapeHtml(r.raw_sha256||'Unverified')}</dd><dt>First Canadian entry</dt><dd>Not established by this queue</dd></dl>${r.decision?`<p>${escapeHtml(r.decision.reason)}</p><dl class="notice-facts">${ABOpportunities.checks.map(k=>`<dt>${escapeHtml(k.replaceAll('_',' '))}</dt><dd>${escapeHtml(r.decision.checks[k].toLowerCase())}</dd>`).join('')}</dl>`:'<p>Full legal identity, ownership, scope, current status and source-reuse review has not been completed for this item.</p>'}</details></article>`).join(''):`<div class="empty-state"><h3>${query?'No evidence matches this search.':view==='qualified'?(model.qualification_count!==null?'No loaded current item has passed every qualification check.':'Qualification coverage is unavailable.'):'No evidence is available in this view.'}</h3><p>${view==='qualified'?'Review-held records remain in the recent-evidence or historical-context views. This is not a finding of no Canadian activity.':'Try the other views. Missing or unavailable coverage remains unknown.'}</p></div>`;
  const register=$('opportunity-review-register');
  register.innerHTML=!opportunityRegister?'<p>The company-review register could not be loaded; no decisions are inferred.</p>':`<p>${opportunityRegister.decisions.length} documented review decisions. A hold is not a rejection and is not a qualified opportunity.</p>`+opportunityRegister.decisions.map(r=>`<article class="company-notice" data-review-decision="${escapeHtml(r.id)}"><h3>${escapeHtml(r.company_name)} · ${escapeHtml(r.decision.replaceAll('_',' ').toLowerCase())}</h3><p>${escapeHtml(r.reason)}</p><p><strong>Next action:</strong> ${escapeHtml(r.next_action)}</p><details><summary>Decision evidence and checks</summary><p>Reviewed ${escapeHtml(r.review_date)} by ${escapeHtml(r.reviewer)}.</p><dl class="notice-facts">${ABOpportunities.checks.map(k=>`<dt>${escapeHtml(k.replaceAll('_',' '))}</dt><dd>${escapeHtml(r.checks[k].toLowerCase())}</dd>`).join('')}</dl>${r.evidence.map(e=>`<p><a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener noreferrer">Original source ↗</a> · Observed ${escapeHtml(e.observed_at)}</p>`).join('')}</details></article>`).join('');
}
function bindOpportunityQueue(){
  const change=(view,query)=>{const p=new URLSearchParams();if(view!=='current')p.set('view',view);if(query)p.set('q',query);history.replaceState(null,'',`#opportunities${p.size?'?'+p:''}`);renderOpportunityQueue(p);};
  $('opportunity-search').addEventListener('input',()=>{const p=new URLSearchParams(location.hash.split('?')[1]||'');change(p.get('view')||'current',$('opportunity-search').value);});
  document.querySelectorAll('[data-opportunity-view]').forEach(b=>b.addEventListener('click',()=>change(b.dataset.opportunityView,$('opportunity-search').value)));
  $('opportunity-reset').addEventListener('click',()=>change('current',''));
}
