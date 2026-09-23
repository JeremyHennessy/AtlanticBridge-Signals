"""Temporary branch-only editor. Removed before the release PR is opened."""
from pathlib import Path
import hashlib
import subprocess
ROOT=Path(__file__).resolve().parents[1]
assert subprocess.check_output(['git','branch','--show-current'],text=True).strip()=='fix/qualification-queue-paths-20260923'
def replace(s,old,new):
    assert s.count(old)==1,old[:120]
    return s.replace(old,new)
p=ROOT/'ui/opportunities.js';s=p.read_text()
s=replace(s,'    const ids=new Set();','    const ids=new Set(), projects=new Set();')
s=replace(s,"      if(r.project_id!==null&&!HEX.test(r.project_id))throw Error('Invalid source-local project link');","      if(r.project_id!==null){if(!HEX.test(r.project_id)||projects.has(r.project_id))throw Error('Invalid or duplicate source-local project link');projects.add(r.project_id);}")
a=s.index('  function queue(');b=s.index('  function select(',a)
s=s[:a]+'''  function latestEvidence(r,now=Date.now()){
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
'''+s[b:]
s=replace(s,'return {validate,qualified,queue,select,checks};','return {validate,qualified,queue,select,checks,latestEvidence,reviewGroups};')
s=replace(s,"<h3>${escapeHtml(r.company_name)} · ${escapeHtml(r.decision.replaceAll('_',' ').toLowerCase())}</h3>","<h3><a class=\"company-dossier-link\" href=\"${companyHash(r.project_id||r.id)}\">${escapeHtml(r.company_name)}</a> · ${escapeHtml(r.decision.replaceAll('_',' ').toLowerCase())}</h3>")
s=replace(s,'<p class="small muted">${escapeHtml(r.kind)} · Public document: ${escapeHtml(formatDate(r.day))}</p>','<p class="small muted">${escapeHtml(r.kind)} · Public document: ${escapeHtml(formatDate(r.day))}</p>${view===\'qualified\'&&r.qualification_evidence?`<p class="small">Qualification status evidence: ${escapeHtml(formatDate(r.decision.current_status_date))} · <a class="source-link" href="${escapeHtml(r.qualification_evidence.source_url)}" target="_blank" rel="noopener noreferrer">Read status source ↗</a>. The original document date is unchanged.</p>`:\'\'}')
s+=(ROOT/'reviews/delivery/queue-renderer.txt').read_text();p.write_text(s)
p=ROOT/'ui/workbench.js';s=p.read_text()
s=replace(s,'return groups; }',"if(typeof ABOpportunities!=='undefined')for(const [id,c] of ABOpportunities.reviewGroups(typeof opportunityRegister==='undefined'?null:opportunityRegister)){if(!groups.has(id))groups.set(id,c);}return groups; }")
a='  const company=workCompanies().get(id), saved=workEntry(id);'
s=replace(s,a,"  const review=typeof companyOnlyReview==='function'?companyOnlyReview(id):null;if(review){renderCompanyReview(review);return;}\n"+a)
s=replace(s,'company.reviewed?"reviewed historical events":"available source notices"','company.review_only?"review evidence references":company.reviewed?"reviewed historical events":"available source notices"');p.write_text(s)
p=ROOT/'ui/reviewed.js';s=p.read_text()
s=replace(s,'function workFeedFor(id){const p=reviewedProject(id);return p?{source:p.source}:state.live;}',"function workFeedFor(id){const p=reviewedProject(id);if(p)return {source:p.source};const c=typeof ABOpportunities!=='undefined'?ABOpportunities.reviewGroups(typeof opportunityRegister==='undefined'?null:opportunityRegister).get(id):null;return c?{source:c.source}:state.live;}");p.write_text(s)
p=ROOT/'tests/test_opportunities.cjs';p.write_text(p.read_text()+(ROOT/'reviews/delivery/queue-unit-tests.txt').read_text())
p=ROOT/'tests/opportunities_acceptance.mjs';s=p.read_text()
s=replace(s,"check(`${label}: register failure leaves current evidence`,await page.locator('[data-opportunity-id]').count()===model.current.length)","check(`${label}: register failure leaves independently available current evidence`,await page.locator('[data-opportunity-id]').count()===api.queue(live,catalog,null).current.length)")
s+=(ROOT/'reviews/delivery/queue-browser-tests.txt').read_text();p.write_text(s)
p=ROOT/'tests/ui_visual_acceptance.mjs';s=p.read_text()
s=replace(s,'import {verifyOpportunities}', 'import {verifyOpportunities,verifyOpportunityPaths}')
s=replace(s,'    await verifyOpportunities(browser,options,base,label,out,check);','    await verifyOpportunities(browser,options,base,label,out,check);\n    await verifyOpportunityPaths(browser,options,base,label,out,check);');p.write_text(s)
expected={'ui/opportunities.js':'f22c48ea6629883ae4ebf761b42ba363d5e1eadd5130601a144dd606d6e3a222','ui/workbench.js':'6790d4d446b2de25ea7b1d3ea5b9319e90e75101b9607dd54ba56566471447b8','ui/reviewed.js':'39c25ebde1bd7d00ae1e08f6c2500e7db5a8e74cf603087d1f50bf3f5ecfb5d5','tests/test_opportunities.cjs':'5a391a135bbbb835d00b98bc8b517b5e9de955ec245d79220c3e03aae813ad9f','tests/opportunities_acceptance.mjs':'b0a3924c310c9db563e574b2e6a3000ef9a913a3ae5cbd2285fe15d72b3fc283','tests/ui_visual_acceptance.mjs':'d82851f1d785c5821e6324f874d22a1c2217153e9b8972a794bfa1c31d6581c9'}
for path,sha in expected.items():
    actual=hashlib.sha256((ROOT/path).read_bytes()).hexdigest();print(path,actual)
    assert actual==sha,'Generated source differs from local tested candidate: '+path
