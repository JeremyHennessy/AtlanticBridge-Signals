/* Dated case dispositions supplement immutable historical dossiers; never qualification. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.ABCaseBriefs=api;})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const HEX=/^[a-f0-9]{64}$/,states=new Set(['MEMBERSHIP_NOT_ENTRY','PRESENCE_WITH_UNRESOLVED_DEMAND','DIFFERENT_PROJECT_EVIDENCE','INAUGURATED_PRODUCTION_PENDING','PARTNER_WITHDRAWAL_PROJECT_CONTINUATION']);
 const day=v=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v;
 const text=v=>typeof v==='string'&&v.trim()&&v.length<=4000;
 const https=v=>{try{const u=new URL(v);return u.protocol==='https:'&&!u.username&&!u.password;}catch(_){return false;}};
 function validate(d){
  if(d?.schema_version!==1||d.status!=='REVIEWED_DISPOSITIONS_NOT_QUALIFIED_LEADS'||!Array.isArray(d.briefs)||d.briefs.length!==d.brief_count||d.brief_count>50)throw Error('Invalid case dispositions');
  const ids=new Set(),companies=new Set();
  for(const b of d.briefs){
   if(!HEX.test(b.id)||!HEX.test(b.company_id)||ids.has(b.id)||companies.has(b.company_id)||!states.has(b.disposition))throw Error('Invalid case identity/disposition');ids.add(b.id);companies.add(b.company_id);
   for(const key of ['company_name','title','summary','next_action','documented_location','market_context','event_time_basis'])if(!text(b[key]))throw Error('Missing bounded case field');
   if(!day(b.reviewed_on)||b.reviewed_on>new Date().toISOString().slice(0,10)||(b.latest_source_publication_date!==null&&!day(b.latest_source_publication_date))||b.qualified!==false||b.public_alert_allowed!==false||b.predictive_score_allowed!==false||b.market_fit_score!==null)throw Error('Disposition cannot approve a score or qualification');
   if(!['UNKNOWN','CONTRADICTED','SUPPORTED'].includes(b.source_use_state)||!Array.isArray(b.remaining_checks)||!Array.isArray(b.evidence)||!b.evidence.length||b.evidence.length>30)throw Error('Missing case uncertainty/provenance');
   const refs=new Set();
   for(const e of b.evidence){if(!text(e.source_id)||refs.has(e.source_id)||!https(e.source_url)||!HEX.test(e.raw_sha256)||!Number.isFinite(Date.parse(e.observed_at))||(e.source_publication_date!==null&&!day(e.source_publication_date))||(e.page!==undefined&&(!Number.isInteger(e.page)||e.page<1)))throw Error('Invalid disposition evidence');refs.add(e.source_id);}
   if(b.evidence.some(e=>e.source_publication_date&&e.source_publication_date>b.reviewed_on))throw Error('Evidence postdates review');
   if(b.latest_source_publication_date!==null&&!b.evidence.some(e=>e.source_publication_date===b.latest_source_publication_date))throw Error('Unbound publication day');
  }
  return d;
 }
 function get(d,id){return d?.briefs.find(b=>b.company_id===id)||null;}
 function linkAllowed(b,e){return !(b.source_use_state==='CONTRADICTED'&&new URL(e.source_url).hostname==='www.roquette.com');}
 return {validate,get,linkAllowed};
});
let caseBriefs=null;
function caseBriefEvidence(b){return b.evidence.map(e=>`<article class="company-notice"><h3>${escapeHtml(e.source_id)}</h3><p>Public document: ${escapeHtml(e.source_publication_date||'Exact day unknown')} · Observed: ${escapeHtml(e.observed_at)}${e.page?` · PDF page ${e.page}`:''}</p>${ABCaseBriefs.linkAllowed(b,e)?`<a class="source-link" href="${escapeHtml(e.source_url+(e.page?'#page='+e.page:''))}" target="_blank" rel="noopener noreferrer">Original evidence ↗</a>`:'<p>Corporate-source link withheld pending the recorded source-use review. The original source identity and hash remain retained.</p>'}<p class="small muted">Retained SHA-256: ${escapeHtml(e.raw_sha256)}</p></article>`).join('');}
function renderCaseBrief(id){
 const b=ABCaseBriefs.get(caseBriefs,id);if(!b)return;
 const root=$('company-content'),columns=root.querySelector('.dossier-columns');if(!columns)return;
 root.querySelector('.case-disposition-panel')?.remove();
 columns.insertAdjacentHTML('beforebegin',`<section class="panel case-disposition-panel" data-case-disposition="${escapeHtml(b.id)}"><div class="panel-header"><div><p class="eyebrow">Reviewed case status / Not a qualified opportunity</p><h2>${escapeHtml(b.title)}</h2></div></div><div class="coverage-stack"><p>${escapeHtml(b.summary)}</p><p><strong>Next action:</strong> ${escapeHtml(b.next_action)}</p><dl class="notice-facts"><dt>Assessment reviewed</dt><dd>${escapeHtml(b.reviewed_on)}</dd><dt>Source/event time basis</dt><dd>${escapeHtml(b.event_time_basis)}</dd><dt>Documented Canadian context</dt><dd>${escapeHtml(b.documented_location)}</dd><dt>Context, not a fit score</dt><dd>${escapeHtml(b.market_context)}</dd><dt>Remaining qualification checks</dt><dd>${escapeHtml(b.remaining_checks.join(', ')||'See review register')}</dd></dl><details><summary>Assessment sources and separate clocks</summary>${caseBriefEvidence(b)}</details></div></section>`);
}
function renderCaseBriefIndex(){
 const root=$('case-brief-index');if(!root)return;
 root.innerHTML=!caseBriefs?'<p>Focused case assessments are unavailable. This is not zero company activity; other evidence and saved work remain accessible.</p>':`<p>${caseBriefs.brief_count} completed case dispositions. These are not five qualified leads or five customer reviews. Original histories remain intact.</p>`+caseBriefs.briefs.map(b=>`<article class="company-notice" data-brief-id="${escapeHtml(b.id)}"><h3><a class="company-dossier-link" href="${companyHash(b.company_id)}">${escapeHtml(b.company_name)}</a></h3><p><strong>${escapeHtml(b.title)}</strong></p><p>${escapeHtml(b.summary)}</p><p><strong>Next action:</strong> ${escapeHtml(b.next_action)}</p></article>`).join('');
}
