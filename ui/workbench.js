/* Additive company dossier/worklist views. Existing audited case views stay unchanged. */
let workStore = null, workDirty = false, workHash = "", workCompanyId = "", workImport = null;
let workQuery = "", workStatus = "", workDue = false, workError = "", workConflict = false;

function workCompanies() { const groups=ABWorkspace.groupCompanies(state.live);for(const [id,p] of ABReviewed.groups(reviewedCatalog)){if(!groups.has(id))groups.set(id,p);}if(typeof ABOpportunities!=='undefined')for(const [id,c] of ABOpportunities.reviewGroups(typeof opportunityRegister==='undefined'?null:opportunityRegister)){if(!groups.has(id))groups.set(id,c);}return groups; }
function workEntry(id) { return workStore?.get(id) || null; }
function workMessage(message, failed = false) {
  const notice = $("workspace-storage-notice");
  notice.textContent=message;notice.hidden=!message;notice.setAttribute("role",failed?"alert":"status");
}
function initializeWorklist() {
  try {
    if (!workStore) workStore=new ABWorkspace.Store(window.localStorage);
    workStore.load(workCompanies(),state.live);
    state.watched=new Set(workStore.entries().map(e=>e.id));
    workError="";
  } catch (error) {
    workError=error.message;state.watched=new Set();
    workMessage("Local worklist unavailable. Existing saved data was not overwritten. "+workError,true);
  }
}
function workLocked(action) {
  // Serialize cooperating tabs where Web Locks is supported, plus optimistic revision checks in Store.
  return navigator.locks?.request ? navigator.locks.request("atlanticbridge-analyst-workspace",action) : Promise.resolve().then(action);
}
async function toggleWorkCompany(id) {
  if (workError) {workMessage(workError,true);return;}
  const old=workEntry(id);
  if (old && (old.notes || old.next_action || old.due_date) && !window.confirm("Remove this company and its local notes from the worklist? Export a backup first to keep a copy.")) return;
  try {
    await workLocked(()=>old ? workStore.remove(id) : workStore.put(ABWorkspace.blankEntry(id,workCompanies().get(id),state.live)));
    state.watched=new Set(workStore.entries().map(e=>e.id));renderSignals();
    if (state.route==="worklist") renderWorklist();
    showToast(old?"Company removed from this local worklist.":"Company added to your local worklist.");
    const button=[...document.querySelectorAll("#signals-list [data-watch-company]")].find(n=>n.dataset.watchCompany===id);
    if(state.route==="signals") (button || $("signal-search")).focus();
  } catch (error) {workMessage("Not saved. "+error.message,true);}
}
function workCanNavigate(hash) {
  if (workDirty && hash!==workHash) {
    if (!window.confirm("Discard unsaved changes to your company notes?")) {
      history.replaceState(null,"",workHash);return false;
    }
    workDirty=false;workConflict=false;
  }
  workHash=hash;return true;
}
function companyHash(id) { return `#company?id=${encodeURIComponent(id)}`; }
function workSourceCoverage() {
  const url=state.live?.source?.source_url || "";
  const fiscal=url.match(/\/(\d{4}-\d{4})-awardNotice/);
  return fiscal ? `Source coverage: CanadaBuys fiscal year ${fiscal[1]}. Date filters narrow this inventory; they do not establish complete coverage of earlier years.`
    : "Source coverage is limited to the accepted CanadaBuys inventory. A date filter is not proof of complete source coverage.";
}
function liveFreshnessText() {
  const health=ABWorkspace.feedHealth(state.live);
  const observed=state.live?.source?.observed_at;
  const latest=state.live?.summary?.latest_public_date;
  const check=health.state==="stale" ? "Source check is stale (over 48 hours)." : health.state==="recent" ? "Source checked" : "Source check time unverified.";
  return `${check} ${observed ? formatTimestamp(observed) : ""} · Latest public record: ${formatDate(latest)}. Retrieval is not a new event.`;
}
function renderCompany(id) {
  workCompanyId=id;workDirty=false;workConflict=false;
  const reviewed=reviewedProject(id);if(reviewed){renderReviewedCompany(reviewed);return;}
  const review=typeof companyOnlyReview==='function'?companyOnlyReview(id):null;if(review){renderCompanyReview(review);return;}
  const company=workCompanies().get(id), saved=workEntry(id);
  const root=$("company-content");
  if (!company && !saved) {
    root.innerHTML='<div class="panel empty-state"><h2>Company not found in this feed or worklist.</h2><p>A missing company is not evidence of no Canadian activity.</p><a class="button" href="#signals">Browse available signals</a></div>';
    return;
  }
  const entry=saved || ABWorkspace.blankEntry(id,company,state.live);
  const name=company?.company_name || entry.company_name || "Saved company identity";
  const country=company?.country || entry.country || "Not resolved";
  const signals=company?.signals || [];
  const canadian=signals.filter(s=>s.scope_review?.state==="INCLUDED_CANADIAN_DELIVERY").length;
  const buyerOnly=signals.filter(s=>s.scope_review?.state==="INCLUDED_BUYER_ONLY").length;
  document.title=`${name} — AtlanticBridge Signals`;
  root.innerHTML=`<div class="page-heading"><div><p class="eyebrow">Company dossier / ${company?"Current supplier evidence":"Saved investigation; source unavailable"}</p><h1 id="company-title">${escapeHtml(name)}</h1><p>${company?"Supplier address country":"Saved country label"}: <strong>${escapeHtml(country)}</strong>. ${company?"Grouped by published supplier name and country—not a verified parent or corporate group.":"The saved name and country do not establish a supplier, legal entity, or corporate group. Source evidence is currently unavailable."}</p></div><button class="button" id="company-share" type="button">Copy company link</button></div>
    <div id="company-share-fallback" hidden></div>
    <div class="research-banner"><strong>${company ? escapeHtml(liveFreshnessText()) : "Not present in the currently available feed."}</strong><span>${company ? escapeHtml(workSourceCoverage()) : "Your saved notes remain available. This may reflect feed coverage or availability; it is not an absence finding."}</span></div>
    <div class="dossier-columns">
      <section class="panel dossier-evidence"><div class="panel-header"><div><p class="eyebrow">What the source supports</p><h2>Canadian commercial evidence</h2></div></div><div class="coverage-stack">
        <div class="coverage-row"><span>Available notices</span><strong>${company ? signals.length : "Unverified"}</strong></div>
        <div class="coverage-row"><span>Explicit Canadian delivery</span><strong>${company ? canadian : "Unverified"}</strong></div>
        <div class="coverage-row"><span>Buyer relationship, location unverified</span><strong>${company ? buyerOnly : "Unverified"}</strong></div>
        <p>Notices may include amendments to the same award. Counts are not distinct contracts, and amounts are not added into an unverified revenue total.</p>
        <div class="notice">First Canadian entry: not established. Expansion likelihood: not validated. Regional market fit: not assessed. A buyer address or delivery location is not the supplier's office.</div>
        <a class="text-link" href="#markets">Review the separate Canadian market lens →</a>
      </div></section>
      <section class="panel dossier-work"><div class="panel-header"><div><p class="eyebrow">Your work / Browser-local</p><h2>Decide the next action</h2></div></div>
        <form id="company-work-form" class="work-form"><p class="small muted">These are your notes, not source facts. They are stored in this browser only. Back up important work; there is no team sync or automatic reminder.</p>
          <label>Research status<select id="work-status">${Object.entries(ABWorkspace.STATUSES).map(([key,value])=>`<option value="${key}"${key===entry.status?" selected":""}>${value}</option>`).join("")}</select></label>
          <label>Next action<input id="work-action" maxlength="500" value="${escapeHtml(entry.next_action)}" placeholder="For example: verify the supplier's Canadian footprint"></label>
          <label>Follow-up date<input id="work-date" type="date" value="${escapeHtml(entry.due_date)}"><span class="small muted">Tracked in the worklist; no notification is sent.</span></label>
          <label>Research notes<textarea id="work-notes" rows="5" maxlength="4000" placeholder="What should be checked before outreach?">${escapeHtml(entry.notes)}</textarea></label>
          <div class="work-actions"><button class="button primary" id="work-save" type="submit"${workError?" disabled":""}>Save to worklist</button><button class="button" id="work-reload" type="button">Reload saved version</button></div>
          <p id="work-save-state" class="small" role="status" aria-live="polite">${saved?"Saved locally on "+escapeHtml(formatTimestamp(saved.updated_at)):"Not yet saved to your worklist."}</p>
        </form>
      </section>
    </div>
    <section class="panel dossier-timeline"><div class="panel-header"><div><p class="eyebrow">Original source / All available dates</p><h2>Notices and evidence timeline</h2></div></div><div class="coverage-stack" id="company-notices">${signals.length?signals.map(s=>`<article class="company-notice" data-company-notice="${escapeHtml(s.id)}"><div class="work-row-heading"><h3>${escapeHtml(s.title || "Federal award notice")}</h3><span>${escapeHtml(formatDate(s.publicly_available_date))}</span></div><p><strong>${escapeHtml(s.signal_kind==="FEDERAL_AWARD_AMENDED"?"Amendment published":"Notice published")}</strong> · Reference ${escapeHtml(s.reference_number || "not stated")} · ${escapeHtml(formatMoney(s.contract_amount,s.contract_currency))}</p><p>${escapeHtml(s.why_surfaced)}</p><details><summary>View published fields and provenance</summary><dl class="notice-facts"><dt>Named buyer</dt><dd>${escapeHtml(s.contracting_entity || "Not stated")}</dd><dt>Delivery regions, as published</dt><dd>${escapeHtml(s.regions_of_delivery || "Not stated; location unverified")}</dd><dt>Award / event date</dt><dd>${escapeHtml(formatDate(s.event_date))}</dd><dt>Publication / amendment date</dt><dd>${escapeHtml(formatDate(s.publicly_available_date))}</dd><dt>Amount / currency, as published</dt><dd>${escapeHtml(s.contract_amount || "Not stated")} / ${escapeHtml(s.contract_currency || "Not stated")}</dd><dt>Source checked</dt><dd>${escapeHtml(formatTimestamp(state.live.source?.observed_at))}</dd><dt>Source SHA-256</dt><dd>${escapeHtml(state.live.source?.source_sha256 || "Not available")}</dd></dl><p>${escapeHtml(s.award_description || "No additional description recorded.")}</p></details>${safeUrl(s.source_url)?`<a class="source-link" href="${escapeHtml(safeUrl(s.source_url))}" target="_blank" rel="noopener noreferrer">Original CanadaBuys dataset ↗</a>`:""}</article>`).join(""):'<p>No accepted current notices are available for this saved identity. Your notes are not affected.</p>'}</div></section>`;
  $("company-work-form").addEventListener("input",()=>{workDirty=true;$("work-save-state").textContent="Unsaved changes.";});
  $("company-work-form").addEventListener("submit",saveCompanyWork);
  $("work-reload").addEventListener("click",()=>{
    if (workDirty && !window.confirm("Discard this draft and reload the saved version?")) return;
    initializeWorklist();workDirty=false;workMessage(workError,true);renderCompany(id);
  });
  $("company-share").addEventListener("click",async()=>{
    const url=new URL(location.href);url.hash=companyHash(id);
    try {await navigator.clipboard.writeText(url.href);showToast("Company link copied. Local notes are not included.");}
    catch (_) {const box=$("company-share-fallback");box.hidden=false;box.innerHTML='<label>Copy this public company link<input readonly id="work-share-value"></label>';$("work-share-value").value=url.href;$("work-share-value").select();}
  });
}
async function saveCompanyWork(event) {
  event.preventDefault();
  const id=workCompanyId;
  if (workError || workConflict) {$("work-save-state").textContent=workError || "Another tab changed the worklist. Your draft is retained; reload to compare before saving.";return;}
  const company=workCompanies().get(id);
  const feed=workFeedFor(id);
  const previous=workEntry(id) || ABWorkspace.blankEntry(id,company,feed);
  const entry={...previous,status:$("work-status").value,notes:$("work-notes").value,next_action:$("work-action").value,due_date:$("work-date").value,updated_at:new Date().toISOString()};
  if(company) Object.assign(entry,{company_name:company.company_name,country:company.country,latest_public_date:company.latest_public_date,
    snapshot_observed_at:feed.source?.observed_at || "",source_url:feed.source?.source_url || "",source_sha256:feed.source?.source_sha256 || ""});
  $("work-save").disabled=true;
  try {
    await workLocked(()=>workStore.put(entry));
    workDirty=false;state.watched=new Set(workStore.entries().map(e=>e.id));renderSignals();
    $("work-save-state").textContent="Saved in this browser. Export a backup to keep another copy.";workMessage("");
  } catch (error) {$("work-save-state").textContent="Not saved. "+error.message;workDirty=true;}
  finally {$("work-save").disabled=false;}
}
function workRows() {
  const query=workQuery.trim().toLowerCase();const today=ABWorkspace.utcToday();
  return (workStore?.entries() || []).filter(e=>(!workStatus || e.status===workStatus) && (!workDue || (e.status!=="closed" && e.due_date && e.due_date<=today)) &&
    (!query || [e.company_name,e.country,e.next_action,e.notes].join(" ").toLowerCase().includes(query)))
    .sort((a,b)=>(a.status==="closed")-(b.status==="closed") || (a.due_date || "9999").localeCompare(b.due_date || "9999") || a.company_name.localeCompare(b.company_name));
}
function renderWorklist() {
  const rows=workRows(), companies=workCompanies(), all=workStore?.entries() || [];
  $("worklist-count").textContent=`${rows.length} of ${all.length} saved companies`;
  $("worklist-search").value=workQuery;$("worklist-status").value=workStatus;$("worklist-due").checked=workDue;
  const today=ABWorkspace.utcToday();
  $("worklist-rows").innerHTML=rows.length?rows.map(entry=>{
    const company=companies.get(entry.id),name=company?.company_name || entry.company_name || "Unresolved saved supplier";
    const due=entry.due_date ? formatDate(entry.due_date) : "No date set";
    const overdue=entry.due_date && entry.due_date<today && entry.status!=="closed";
    return `<article class="worklist-row" data-worklist-id="${escapeHtml(entry.id)}"><div><a class="work-company-link" href="${companyHash(entry.id)}">${escapeHtml(name)}</a><p class="small muted">${escapeHtml(company?.country || entry.country || "Address country unverified")}</p><p class="small">${company ? `${company.signals.length} ${company.review_only?"review evidence references":company.reviewed?"reviewed historical events":"available source notices"}` : "Not in the available feed; saved work retained"}</p></div><div><span class="status-chip">${escapeHtml(ABWorkspace.STATUSES[entry.status])}</span><p class="small${overdue?" work-overdue":""}">${overdue?"Overdue · ":""}${escapeHtml(due)}</p></div><div><p class="small"><strong>Next action</strong></p><p>${escapeHtml(entry.next_action || "No next action recorded")}</p><p class="small muted">Your workflow—not a source or confidence label.</p></div><button class="text-button" type="button" data-remove-work="${escapeHtml(entry.id)}">Remove<span class="sr-only"> ${escapeHtml(name)}</span></button></article>`;
  }).join(""):`<div class="empty-state"><h2>${all.length?"No saved companies match these filters.":"Start a company investigation."}</h2><p>${all.length?"Reset the worklist filters to see your saved work.":"Open a company from Signals, record a next action, and save it here. Existing watch stars are preserved."}</p><a class="button" href="#signals">Explore signals</a><button class="button" type="button" id="worklist-empty-reset">Reset worklist filters</button></div>`;
  $("worklist-empty-reset")?.addEventListener("click",resetWorklist);
  $("work-export").disabled=!!workError;$("work-backup").disabled=!!workError;
}
function resetWorklist() {workQuery="";workStatus="";workDue=false;renderWorklist();syncWorklistUrl();}
function syncWorklistUrl() {
  const p=new URLSearchParams();if(workQuery)p.set("q",workQuery);if(workStatus)p.set("status",workStatus);if(workDue)p.set("due","1");
  workHash=`#worklist${p.size?"?"+p:""}`;history.replaceState(null,"",workHash);
}
function workDownload(name, text, type) {
  const url=URL.createObjectURL(new Blob([text],{type}));const link=document.createElement("a");link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function bindWorkEvents() {
  for(const id of ["worklist-search","worklist-status","worklist-due"]) $(id).addEventListener(id==="worklist-search"?"input":"change",()=>{
    workQuery=$("worklist-search").value;workStatus=$("worklist-status").value;workDue=$("worklist-due").checked;renderWorklist();syncWorklistUrl();
  });
  $("worklist-reset").addEventListener("click",resetWorklist);
  $("worklist-rows").addEventListener("click",event=>{const button=event.target.closest("[data-remove-work]");if(button)toggleWorkCompany(button.dataset.removeWork);});
  $("work-export").addEventListener("click",()=>{if(!workError)workDownload("AtlanticBridge-worklist.csv",ABWorkspace.worklistCSV(workRows()),"text/csv;charset=utf-8");});
  $("work-backup").addEventListener("click",()=>{if(!workError)workDownload("AtlanticBridge-worklist-backup.json",JSON.stringify(workStore.backup(),null,2),"application/json");});
  $("work-import-file").addEventListener("change",async event=>{
    workImport=null;$("work-import-confirm").hidden=true;
    try {
      const file=event.target.files[0];if(!file)return;
      if(file.size>ABWorkspace.MAX_BYTES)throw new Error("Backup exceeds the 2 MB limit.");
      const text=await file.text();const backup=ABWorkspace.validateBackup(text);
      workImport={format:"atlanticbridge-analyst-workspace",...backup};
      const existing=new Set(workStore?.entries().map(e=>e.id));const added=backup.entries.filter(e=>!existing.has(e.id)).length;
      $("work-import-state").textContent=`Ready to add ${added} saved companies. ${backup.entries.length-added} existing entries will be kept without overwriting their notes. Imported notes are user-supplied, not verified evidence.`;
      $("work-import-confirm").hidden=false;
    } catch(error) {$("work-import-state").textContent="Nothing imported. "+error.message;}
    finally {event.target.value="";}
  });
  $("work-import-confirm").addEventListener("click",async()=>{
    if(!workImport || workError)return;
    try {const result=await workLocked(()=>workStore.mergeNew(workImport));state.watched=new Set(workStore.entries().map(e=>e.id));renderSignals();renderWorklist();$("work-import-state").textContent=`Imported ${result.added} companies; ${result.kept} existing entries were left unchanged.`;workImport=null;$("work-import-confirm").hidden=true;}
    catch(error){$("work-import-state").textContent="Nothing imported. "+error.message;}
  });
  window.addEventListener("beforeunload",event=>{if(workDirty){event.preventDefault();event.returnValue="";}});
  window.addEventListener("storage",event=>{
    if(event.key!==ABWorkspace.KEY && event.key!==null)return;
    if(workDirty){workConflict=true;workMessage("Worklist changed in another tab. Your unsaved draft is retained. Reload the saved version to compare before saving.",true);return;}
    initializeWorklist();renderSignals();if(state.route==="worklist")renderWorklist();if(state.route==="company")renderCompany(workCompanyId);
  });
  document.addEventListener("visibilitychange",()=>{if(!document.hidden && state.live){renderSignals();renderMetrics();}});
}
