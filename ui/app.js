// Evidence workspace. Local filters/watchlists never change source records.
const state = {data:null, live:null, query:"", classification:"", evidence:"", country:"", sort:"name", view:"all", signalQuery:"", signalCountry:"", signalWindow:"90", signalView:"all", researchQuery:"", researchRole:"", researchCipo:"", researchSort:"signal", route:"overview", caseId:null, saved:new Set(), watched:new Set()};
const $ = (id) => document.getElementById(id);
const els = {auditDate:$("audit-date"), metricCases:$("metric-cases"), metricEvidence:$("metric-evidence"), metricIdentity:$("metric-identity"), metricModel:$("metric-model"), caseSearch:$("case-search"), classificationFilter:$("classification-filter"), evidenceFilter:$("evidence-filter"), caseCountLabel:$("case-count-label"), casesBody:$("cases-body"), emptyRowTemplate:$("empty-row-template"), coverageBefore:$("coverage-before"), coverageBeforeBar:$("coverage-before-bar"), coverageSame:$("coverage-same"), coverageSameBar:$("coverage-same-bar"), coveragePublication:$("coverage-publication"), coveragePublicationBar:$("coverage-publication-bar"), medianLead:$("median-lead"), sourceTypes:$("source-types"), drawer:$("case-drawer"), drawerTitle:$("drawer-title"), drawerContent:$("drawer-content"), drawerClose:$("drawer-close"), drawerBackdrop:$("drawer-backdrop")};
const SAVE_KEY = "atlanticbridge.saved-cases.v1";
const WATCH_KEY = "atlanticbridge.watched-companies.v1";
let returnFocus = null;
let toastTimer;
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "https:" || url.protocol === "http:") {
      return url.href;
    }
  } catch (_) {
    return null;
  }
  return null;
}

function formatClassification(value) {
  const labels = {
    EXISTING_CANADIAN_PRESENCE: "Already present in Canada",
    ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED: "Business setup supported",
    UNRESOLVED: "Still unresolved",
  };
  return labels[value] || value || "Unknown";
}

function classificationClass(value) {
  if (value === "EXISTING_CANADIAN_PRESENCE") return "status-existing";
  if (value === "ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED") {
    return "status-establishment";
  }
  return "status-unresolved";
}

function formatResearchStatus(value) {
  const labels = {
    ACCEPTED_BACKTEST_CONTROL: "Accepted control",
    IDENTITY_QUALIFIED_RESEARCH_CONTROL: "Identity-qualified",
  };
  return labels[value] || value || "Research";
}

function formatResearchSignal(value) {
  const labels = {
    CIPO_CANADIAN_TRADEMARK: "CIPO trademark",
    TED_CONTRACT_AWARD: "TED award",
    CANADABUYS_AWARD: "CanadaBuys award",
  };
  return labels[value] || formatSourceType(value);
}

function formatResearchSignalState(value) {
  const labels = {
    PRESENT: "Present before cutoff",
    ABSENT_WITH_PROVEN_COVERAGE: "No exact hit · coverage proven",
    UNKNOWN_UNVERIFIED_COVERAGE: "Unknown · coverage not sufficient",
    MIXED_BY_CUTOFF: "Changes by cutoff",
  };
  return labels[value] || value || "Unknown";
}

function researchSignalClass(value) {
  if (value === "PRESENT") return "signal-present";
  if (value === "ABSENT_WITH_PROVEN_COVERAGE") return "signal-absent";
  return "signal-unknown";
}

function formatPublicationStatus(value) {
  const labels = {
    VERIFIED_BEFORE_NOTIFICATION_MONTH: "Public before notification",
    VERIFIED_DURING_NOTIFICATION_MONTH: "Public during notification month",
    VERIFIED_AFTER_NOTIFICATION_MONTH: "Public after notification",
    OVERLAPS_NOTIFICATION_MONTH: "Publication window overlaps notification",
    UNVERIFIED: "Historical availability unverified",
  };
  return labels[value] || value || "Historical availability unverified";
}

function publicationStatusClass(value) {
  if (value === "VERIFIED_BEFORE_NOTIFICATION_MONTH") return "publication-before";
  if (value === "VERIFIED_DURING_NOTIFICATION_MONTH") return "publication-during";
  if (value === "VERIFIED_AFTER_NOTIFICATION_MONTH") return "publication-after";
  if (value === "OVERLAPS_NOTIFICATION_MONTH") return "publication-overlaps";
  return "publication-unverified";
}

function formatSourceType(value) {
  return String(value || "Unknown")
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

function formatDate(value) {
  if (!value) return "Unknown";
  if (/^\d{4}-\d{2}$/.test(value)) {
    const [year, month] = value.split("-");
    const date = new Date(Date.UTC(Number(year), Number(month) - 1, 1));
    return date.toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      timeZone: "UTC",
    });
  }
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const date = new Date(value + "T00:00:00Z");
    return date.toLocaleDateString("en-CA", {
      year: "numeric",
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });
  }
  return value;
}

function leadLabel(days) {
  if (days === null || days === undefined) return "—";
  if (days < 0) return "Same month";
  if (days === 0) return "Same day";
  return `${days} d`;
}

function timelineDate(value, precision = null) {
  if (!value) return null;
  const text = String(value);
  let sortValue = Number.POSITIVE_INFINITY;
  let label = formatDate(text);
  let precisionLabel = "";

  if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
    sortValue = Date.parse(text + "T00:00:00Z");
    precisionLabel = precision === "YEAR" ? "year only" : precision === "MONTH" ? "month only" : "";
  } else if (/^\d{4}-\d{2}$/.test(text)) {
    const [year, month] = text.split("-").map(Number);
    sortValue = Date.UTC(year, month - 1, 1);
    precisionLabel = "month only";
  } else if (/^\d{4}$/.test(text)) {
    sortValue = Date.UTC(Number(text), 0, 1);
    label = text;
    precisionLabel = "year only";
  }

  return {
    raw: text,
    sortValue,
    label: precisionLabel ? `${label} · ${precisionLabel}` : label,
  };
}

function buildCaseTimeline(item) {
  const events = [];

  const incorporation = timelineDate(item.incorporation_date, "DAY");
  if (incorporation) {
    events.push({
      kind: "registry",
      date: incorporation,
      title: "Federal corporation event",
      detail: `${item.canadian_business_name} incorporated or entered the federal registry.`,
      meta: "Corporations Canada",
    });
  }

  (item.evidence || []).forEach((evidence, index) => {
    const eventDate = timelineDate(
      evidence.event_date || evidence.source_date,
      evidence.event_date ? evidence.event_date_precision : null,
    );
    if (eventDate) {
      events.push({
        kind: "evidence",
        date: eventDate,
        title: formatSourceType(evidence.source_type),
        detail: evidence.claim || "Source-backed evidence milestone.",
        meta: evidence.supports || "Evidence role unclassified",
        evidenceIndex: index,
      });
    }

    const publicDate = timelineDate(
      evidence.publicly_available_date,
      evidence.publicly_available_date_precision,
    );
    const primaryRaw = eventDate?.raw || null;
    if (publicDate && publicDate.raw !== primaryRaw) {
      events.push({
        kind: "publication",
        date: publicDate,
        title: "Evidence publicly available",
        detail: evidence.claim || formatSourceType(evidence.source_type),
        meta: formatPublicationStatus(evidence.publication_status),
        evidenceIndex: index,
      });
    }
  });

  const notification = timelineDate(item.notification_month, "MONTH");
  if (notification) {
    events.push({
      kind: "notification",
      date: notification,
      title: "Investment Canada notification",
      detail: `${item.canadian_business_name} appears in the audited new-business notification cohort.`,
      meta: "Investment Canada Act",
    });
  }

  const firstOperations = timelineDate(item.first_canadian_operations_date, "DAY");
  if (firstOperations) {
    events.push({
      kind: "operations",
      date: firstOperations,
      title: "Verified first Canadian operations",
      detail: "Audited first-operation date.",
      meta: "Outcome timing",
    });
  }

  events.sort((left, right) => {
    if (left.date.sortValue !== right.date.sortValue) {
      return left.date.sortValue - right.date.sortValue;
    }
    const order = {
      evidence: 0,
      publication: 1,
      registry: 2,
      notification: 3,
      operations: 4,
    };
    return (order[left.kind] ?? 9) - (order[right.kind] ?? 9);
  });

  return events;
}

function renderCaseTimeline(item) {
  const events = buildCaseTimeline(item);
  const investor = `${item.investor_name || "Unknown investor"} · ${item.ultimate_control_country || "control country unresolved"}`;

  return `
    <div class="timeline-context">
      <span>EU / foreign investor context</span>
      <strong>${escapeHtml(investor)}</strong>
    </div>
    <div class="case-timeline">
      ${events.length
        ? events.map((event) => `
            <article class="timeline-item timeline-${escapeHtml(event.kind)}">
              <div class="timeline-marker" aria-hidden="true"></div>
              <div class="timeline-content">
                <div class="timeline-topline">
                  <time>${escapeHtml(event.date.label)}</time>
                  <span>${escapeHtml(formatSourceType(event.meta))}</span>
                </div>
                <h4>${escapeHtml(event.title)}</h4>
                <p>${escapeHtml(event.detail)}</p>
              </div>
            </article>
          `).join("")
        : '<div class="no-evidence">No dated milestones are available for this case.</div>'}
    </div>
    <p class="timeline-caveat">
      Timeline order follows the recorded date precision. Month-only and year-only milestones do not imply an exact sequence within that period.
    </p>
  `;
}

function renderEvidence(evidence) {
  if (!evidence.length) {
    return `
      <div class="no-evidence">
        No additional evidence is attached to this audited case yet. Registry timing is
        preserved, but absence of additional evidence is not treated as a negative signal.
      </div>
    `;
  }

  return `
    <div class="evidence-stack">
      ${evidence
        .map((item) => {
          const url = safeUrl(item.source_url);
          const primaryDate = item.event_date || item.source_date;
          const publicDate = item.publicly_available_date
            ? formatDate(item.publicly_available_date)
            : "Unverified";
          return `
            <article class="evidence-card">
              <div class="evidence-topline">
                <span class="evidence-type">${escapeHtml(formatSourceType(item.source_type))}</span>
                <span class="evidence-date">${escapeHtml(formatDate(primaryDate))}</span>
              </div>
              <p class="evidence-claim">${escapeHtml(item.claim || "No claim text recorded.")}</p>
              <div class="evidence-publication">
                <span class="publication-chip ${publicationStatusClass(item.publication_status)}">
                  ${escapeHtml(formatPublicationStatus(item.publication_status))}
                </span>
                <span class="publication-date">Public date: ${escapeHtml(publicDate)}</span>
              </div>
              <div class="evidence-support">${escapeHtml(formatSourceType(item.supports || "Evidence role unclassified"))}</div>
              ${
                url
                  ? `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Open source ↗</a>`
                  : ""
              }
            </article>
          `;
        })
        .join("")}
    </div>
  `;
}


function earlyEvidence(item) { return (item.verified_pre_notification_evidence_count || 0) > 0; }
function filteredCases() {
  if (!state.data) return [];
  const query = state.query.trim().toLocaleLowerCase();
  return state.data.cases.filter((item) => {
    const text = [item.canadian_business_name, item.investor_name, item.ultimate_control_country, item.canadian_business_activity, item.corporation_number].filter(Boolean).join(" ").toLocaleLowerCase();
    return (!query || text.includes(query)) && (!state.classification || item.outcome_classification === state.classification) && (!state.country || item.ultimate_control_country === state.country) && (state.evidence !== "with" || item.evidence_count > 0) && (state.evidence !== "without" || item.evidence_count === 0) && (state.view !== "early" || earlyEvidence(item)) && (state.view !== "registry" || item.evidence_count === 0) && (state.view !== "saved" || state.saved.has(item.id));
  }).sort((a,b) => {
    const nameOrder = String(a.canadian_business_name).localeCompare(String(b.canadian_business_name), "en");
    if (state.sort === "newest") return String(b.notification_month || "").localeCompare(String(a.notification_month || "")) || nameOrder;
    if (state.sort === "evidence") return b.evidence_count - a.evidence_count || nameOrder;
    return nameOrder;
  });
}
function formatMoney(value, currency) { return ABWorkspace.money(value,currency); }

function formatTimestamp(value) {
  if (!value) return "Unknown";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("en-CA",{year:"numeric",month:"short",day:"numeric",hour:"numeric",minute:"2-digit"});
}

function unavailableLivePayload(reason="Current signal feed unavailable.") {
  return {schema_version:1,status:"UNAVAILABLE",generated_at:null,reason,source:{family:"CANADABUYS_AWARD",label:"CanadaBuys federal award notice",observed_at:null,source_url:null},summary:{signal_count:0,company_count:0,country_count:0,latest_public_date:null,earliest_public_date:null,cad_contract_amount:"0",lookback_days:null},signals:[]};
}

function activeLiveSignals() {
  return state.live?.status === "ACTIVE" && Array.isArray(state.live.signals) ? state.live.signals : [];
}

function liveSignalsForWindow(days=90) {
  return activeLiveSignals().filter(signal => {const age=ABWorkspace.signalAge(signal);return age!==null && age>=0 && age<=days;});
}

function filteredSignals() {
  const q=state.signalQuery.trim().toLocaleLowerCase();
  const maxDays=state.signalWindow === "all" ? null : Number(state.signalWindow);
  return activeLiveSignals().filter(signal => {
    const age=ABWorkspace.signalAge(signal);
    if(maxDays != null && (age===null || age<0 || age>maxDays))return false;
    if(state.signalCountry && signal.country !== state.signalCountry)return false;
    if(state.signalView === "watched" && !state.watched.has(signal.company_id))return false;
    if(!q)return true;
    const text=[signal.company_name,signal.country,signal.title,signal.contracting_entity,signal.reference_number,signal.award_description].filter(Boolean).join(" ").toLocaleLowerCase();
    return text.includes(q);
  }).sort((a,b)=>String(b.publicly_available_date||"").localeCompare(String(a.publicly_available_date||"")) || String(a.company_name||"").localeCompare(String(b.company_name||"")));
}

function loadWatched() { initializeWorklist(); }
function toggleWatched(companyId) { return toggleWorkCompany(companyId); }

function populateSignalCountries() {
  const select=$("signal-country-filter");
  if(!select)return;
  const countries=[...new Set(activeLiveSignals().map(x=>x.country).filter(Boolean))].sort();
  const current=state.signalCountry;
  select.innerHTML='<option value="">All countries</option>'+countries.map(x=>`<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join("");
  if(current && countries.includes(current))select.value=current;
}

function syncSignalControls() {
  $("signal-search").value=state.signalQuery;
  $("signal-country-filter").value=state.signalCountry;
  $("signal-window").value=state.signalWindow;
  document.querySelectorAll("[data-signal-view]").forEach(button=>button.setAttribute("aria-pressed",String(button.dataset.signalView===state.signalView)));
}

function syncSignalUrl() {
  if(state.route!=="signals")return;
  const p=new URLSearchParams();
  if(state.signalQuery)p.set("q",state.signalQuery);
  if(state.signalCountry)p.set("country",state.signalCountry);
  if(state.signalWindow!=="90")p.set("window",state.signalWindow);
  if(state.signalView!=="all")p.set("view",state.signalView);
  history.replaceState(null,"",`#signals${p.size?"?"+p:""}`);
}

function resetSignalFilters() {
  state.signalQuery="";state.signalCountry="";state.signalWindow="90";state.signalView="all";
  syncSignalControls();renderSignals();syncSignalUrl();$("signal-search").focus();
}

function renderSignals() {
  const active=state.live?.status==="ACTIVE";
  const root=$("signals-list");
  $("watched-count").textContent=state.watched.size;
  if(!active){
    $("signal-freshness").innerHTML=`<strong>Current feed unavailable.</strong><span>${escapeHtml(state.live?.reason || "No current source snapshot is available.")}</span>`;
    for(const id of ["signal-metric-count","signal-metric-companies","signal-metric-countries","signal-metric-latest"])$(id).textContent="—";
    $("signal-count-label").textContent="Current signal feed unavailable—not zero signals";
    root.innerHTML='<div class="empty-state signal-empty"><h3>Current signals are unavailable.</h3><p>The historical evidence workspace remains available. No zero-signal conclusion has been inferred.</p></div>';
    return;
  }

  const rows=filteredSignals();
  const companyIds=new Set(rows.map(x=>x.company_id));
  const countries=new Set(rows.map(x=>x.country).filter(Boolean));
  const latest=rows.map(x=>x.publicly_available_date).filter(Boolean).sort().at(-1)||null;
  $("signal-metric-count").textContent=rows.length;
  $("signal-metric-companies").textContent=companyIds.size;
  $("signal-metric-countries").textContent=countries.size;
  $("signal-metric-latest").textContent=latest?formatDate(latest):"—";
  $("signal-count-label").textContent=`${rows.length} signal${rows.length===1?"":"s"} · ${companyIds.size} compan${companyIds.size===1?"y":"ies"}`;
  $("signal-freshness").innerHTML=`<strong>${escapeHtml(liveFreshnessText())}</strong><span>${escapeHtml(workSourceCoverage())}</span>`;
  $("signal-freshness").dataset.freshness=ABWorkspace.feedHealth(state.live).state;

  if(!rows.length){
    root.innerHTML='<div class="empty-state signal-empty"><h3>No signals match these filters.</h3><p>The underlying current feed is unchanged.</p><button class="button button-secondary" type="button" data-signal-reset>Reset signal filters</button></div>';
    return;
  }

  root.innerHTML=rows.map(signal=>{
    const watched=state.watched.has(signal.company_id);
    const source=safeUrl(signal.source_url);
    const kind=signal.signal_kind==="FEDERAL_AWARD_AMENDED"?"Award amended":"Award published";
    const amount=formatMoney(signal.contract_amount,signal.contract_currency);
    return `<article class="live-signal-item" data-live-signal-id="${escapeHtml(signal.id)}" data-company-id="${escapeHtml(signal.company_id)}">
      <div class="live-signal-main">
        <div class="live-signal-date"><span class="eyebrow">${escapeHtml(kind)}</span><strong>${escapeHtml(formatDate(signal.publicly_available_date))}</strong><span>${ABWorkspace.signalAge(signal)===null || ABWorkspace.signalAge(signal)<0 ? "Public date unverified" : escapeHtml(ABWorkspace.signalAge(signal))+"d ago"}</span></div>
        <div class="live-signal-company"><div class="live-signal-company-line"><h3><a class="company-dossier-link" href="${companyHash(signal.company_id)}">${escapeHtml(signal.company_name)}</a></h3><span class="status-chip status-existing">${escapeHtml(signal.country)}</span></div><p>${escapeHtml(signal.title || signal.award_description || "Federal award notice")}</p><span class="live-signal-buyer">${escapeHtml(signal.contracting_entity || "Canadian federal contracting entity not stated")}</span></div>
        <div class="live-signal-value"><strong>${escapeHtml(amount)}</strong><span>${escapeHtml(signal.reference_number || "No reference")}</span></div>
        <button class="save-button signal-watch" type="button" data-watch-company="${escapeHtml(signal.company_id)}" aria-pressed="${watched}" aria-label="${watched?"Unwatch":"Watch"} ${escapeHtml(signal.company_name)}" title="${watched?"Remove company from watchlist":"Watch company in this browser"}">${watched?"★":"☆"}</button>
      </div>
      <div class="live-signal-context"><p><strong>Why surfaced:</strong> ${escapeHtml(signal.why_surfaced)}</p><div class="live-signal-meta"><span>Stage · ${escapeHtml(String(signal.signal_stage||"").replaceAll("_"," ").toLowerCase())}</span><span>Identity · ${escapeHtml(String(signal.identity_scope||"").replaceAll("_"," ").toLowerCase())}</span>${signal.regions_of_delivery?`<span>Delivery · ${escapeHtml(signal.regions_of_delivery)}</span>`:""}</div>${source?`<a class="source-link" href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer">Official CanadaBuys source ↗</a>`:""}</div>
    </article>`;
  }).join("");
}

function renderMetrics() {
  const s = state.data?.summary;
  const live90=liveSignalsForWindow(90);
  const liveCompanies90=new Set(live90.map(x=>x.company_id));
  els.auditDate.textContent = `Source checked: ${formatDate(state.live?.source?.observed_at?.slice(0,10))} · Case audit: ${formatDate(state.data?.audit_date)}`;
  if(s){els.metricCases.textContent=s.case_count;els.metricEvidence.textContent=s.research_cohort_count;}
  $("metric-live-signals").textContent = state.live?.status==="ACTIVE" ? live90.length : "—";
  $("metric-live-companies").textContent = state.live?.status==="ACTIVE" ? liveCompanies90.size : "—";
  $("signal-nav-count").textContent = state.live?.status==="ACTIVE" ? live90.length : "—";
  $("overview-live-status").textContent = state.live?.status==="ACTIVE"
    ? `${live90.length} signal${live90.length===1?"":"s"} dated within 90 days. ${liveFreshnessText()}`
    : "Current signal feed unavailable. Historical evidence remains available.";
  if(!s){$("data-note").textContent="Audited cases unavailable; current signals and saved work are independent.";populateSignalCountries();return;}
  els.metricIdentity.textContent = s.identity_supported;
  els.metricModel.textContent = s.model_eligible_count;
  for (const [label,bar,count] of [[els.coverageBefore,els.coverageBeforeBar,s.before_notification_month],[els.coverageSame,els.coverageSameBar,s.same_notification_month],[els.coveragePublication,els.coveragePublicationBar,s.cases_with_verified_pre_notification_evidence]]) {
    label.textContent = `${count} / ${s.case_count}`;
    bar.style.width = `${s.case_count ? Math.min(100,100*count/s.case_count) : 0}%`;
  }
  els.medianLead.textContent = s.median_days_before_notification_month == null ? "Unknown" : `${s.median_days_before_notification_month} days`;
  $("data-note").textContent = `Live feed: ${state.live?.status==="ACTIVE"?formatTimestamp(state.live.source?.observed_at || state.live.generated_at):"unavailable"} · Case audit: ${formatDate(state.data.audit_date)} · ${s.case_count} audited cases · ${s.research_cohort_count} research companies · UI: 22 September 2026.`;
  const countries = [...new Set(state.data.cases.map(x => x.ultimate_control_country).filter(Boolean))].sort();
  $("country-filter").innerHTML = '<option value="">All countries</option>' + countries.map(x => `<option value="${escapeHtml(x)}">${escapeHtml(x)}</option>`).join("");
  populateSignalCountries();
}
function renderSources() {
  els.sourceTypes.innerHTML = Object.entries(state.data.summary.source_type_counts).map(([type,count]) => `<div class="source-row"><span>${escapeHtml(formatSourceType(type))}</span><span class="source-count">${escapeHtml(count)}</span></div>`).join("");
}
function researchSignalFor(item, family) {
  return (item.signal_analysis || []).find(signal => signal.signal_family === family) || null;
}

function compactResearchSignalState(value) {
  const labels = {
    PRESENT: "Present",
    ABSENT_WITH_PROVEN_COVERAGE: "Proven absent",
    UNKNOWN_UNVERIFIED_COVERAGE: "Unknown",
    MIXED_BY_CUTOFF: "Mixed",
  };
  return labels[value] || "Unknown";
}

function filteredResearch() {
  if (!state.data) return [];
  const q = state.researchQuery.trim().toLocaleLowerCase();
  const rows = state.data.research_cohort.filter(item => {
    if (state.researchRole && item.research_status !== state.researchRole) return false;
    const cipo = researchSignalFor(item, "CIPO_CANADIAN_TRADEMARK");
    if (state.researchCipo && cipo?.state !== state.researchCipo) return false;
    if (!q) return true;
    const haystack = [
      item.display_name,
      item.investor_name,
      item.ultimate_control_country,
      item.foreign_legal_identifier,
      item.investor_locality,
    ].filter(Boolean).join(" ").toLocaleLowerCase();
    return haystack.includes(q);
  });
  const signalRank = {PRESENT:0, UNKNOWN_UNVERIFIED_COVERAGE:1, MIXED_BY_CUTOFF:2, ABSENT_WITH_PROVEN_COVERAGE:3};
  rows.sort((a,b) => {
    if (state.researchSort === "entry") {
      return String(b.later_new_business_month || "").localeCompare(String(a.later_new_business_month || "")) || String(a.display_name).localeCompare(String(b.display_name));
    }
    if (state.researchSort === "name") return String(a.display_name).localeCompare(String(b.display_name));
    const ac = researchSignalFor(a,"CIPO_CANADIAN_TRADEMARK")?.state || "UNKNOWN_UNVERIFIED_COVERAGE";
    const bc = researchSignalFor(b,"CIPO_CANADIAN_TRADEMARK")?.state || "UNKNOWN_UNVERIFIED_COVERAGE";
    return (signalRank[ac] ?? 9) - (signalRank[bc] ?? 9)
      || Number(b.research_status === "ACCEPTED_BACKTEST_CONTROL") - Number(a.research_status === "ACCEPTED_BACKTEST_CONTROL")
      || String(a.display_name).localeCompare(String(b.display_name));
  });
  return rows;
}

function syncResearchControls() {
  $("research-search").value = state.researchQuery;
  $("research-role-filter").value = state.researchRole;
  $("research-cipo-filter").value = state.researchCipo;
  $("research-sort").value = state.researchSort;
}

function syncResearchUrl() {
  if (state.route !== "research") return;
  const params = new URLSearchParams();
  if (state.researchQuery) params.set("q",state.researchQuery);
  if (state.researchRole) params.set("role",state.researchRole);
  if (state.researchCipo) params.set("cipo",state.researchCipo);
  if (state.researchSort !== "signal") params.set("sort",state.researchSort);
  history.replaceState(null,"",`#research${params.size ? "?" + params : ""}`);
}

function resetResearchFilters() {
  state.researchQuery="";
  state.researchRole="";
  state.researchCipo="";
  state.researchSort="signal";
  syncResearchControls();
  renderResearch();
  syncResearchUrl();
  $("research-search").focus();
}

function renderResearch() {
  if(!state.data)return;
  const allRows = state.data.research_cohort || [];
  const rows = filteredResearch();
  $("research-count").textContent = allRows.length;
  $("research-accepted-count").textContent = allRows.filter(x => x.research_status === "ACCEPTED_BACKTEST_CONTROL").length;
  $("research-qualified-count").textContent = allRows.filter(x => x.research_status === "IDENTITY_QUALIFIED_RESEARCH_CONTROL").length;
  $("research-cipo-present-count").textContent = allRows.filter(x => researchSignalFor(x,"CIPO_CANADIAN_TRADEMARK")?.state === "PRESENT").length;
  $("research-cipo-unknown-count").textContent = allRows.filter(x => researchSignalFor(x,"CIPO_CANADIAN_TRADEMARK")?.state === "UNKNOWN_UNVERIFIED_COVERAGE").length;
  $("research-result-count").textContent = `${rows.length} of ${allRows.length} companies`;
  const root = $("research-companies");
  if (!rows.length) {
    root.innerHTML = '<div class="empty-state research-empty"><h3>No research companies match these filters.</h3><p>The underlying cohort is unchanged.</p><button class="button button-secondary" type="button" data-research-reset>Reset research filters</button></div>';
    return;
  }
  root.innerHTML = rows.map(item => {
    const sources = (item.identity_evidence || []).map(source => {
      const url = safeUrl(source.source_url);
      const label = formatSourceType(source.source_type);
      return url
        ? `<li><a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(label)} ↗</a><span>${escapeHtml(source.claim || "Primary-source identity evidence")}</span></li>`
        : `<li><strong>${escapeHtml(label)}</strong><span>${escapeHtml(source.claim || "Primary-source identity evidence")}</span></li>`;
    }).join("");
    const matched = (item.matched_candidates || []).map(candidate => {
      const name = candidate.canadian_business_name || candidate.investor_name || "Audited candidate";
      return `${escapeHtml(name)} · ${escapeHtml(formatDate(candidate.notification_month))}`;
    }).join("; ");
    const statusClass = item.research_status === "ACCEPTED_BACKTEST_CONTROL" ? "status-existing" : "status-establishment";
    const signalCell = family => {
      const signal = researchSignalFor(item,family);
      const stateValue = signal?.state || "UNKNOWN_UNVERIFIED_COVERAGE";
      const detail = signal?.state === "PRESENT" && signal.earliest_public_date
        ? `Earliest public evidence ${formatDate(signal.earliest_public_date)}`
        : formatResearchSignalState(stateValue);
      return `<span class="research-signal-pill ${researchSignalClass(stateValue)}" title="${escapeHtml(detail)}"><span class="signal-dot" aria-hidden="true"></span>${escapeHtml(compactResearchSignalState(stateValue))}</span>`;
    };
    const signalDetails = (item.signal_analysis || []).map(signal => {
      const cutoffs = (signal.cutoffs || []).map(cutoff => `${cutoff.offset_months}m: ${compactResearchSignalState(cutoff.state)}`).join(" · ");
      return `<div class="research-detail-signal"><strong>${escapeHtml(formatResearchSignal(signal.signal_family))}</strong><span>${escapeHtml(formatResearchSignalState(signal.state))}</span><small>${escapeHtml(cutoffs || "No cutoff detail")} · ${escapeHtml(signal.coverage_status || "Coverage unverified")}</small></div>`;
    }).join("");
    return `<article class="research-list-item" data-research-id="${escapeHtml(item.id)}">
      <div class="research-row-main">
        <div class="research-company-cell"><span class="eyebrow">${escapeHtml(item.ultimate_control_country || "Country unknown")}</span><h3>${escapeHtml(item.display_name)}</h3><span class="research-legal-id">${escapeHtml(item.foreign_legal_identifier || "Legal identifier not recorded")}</span></div>
        <div class="research-role-cell"><span class="status-chip ${statusClass}">${escapeHtml(formatResearchStatus(item.research_status))}</span></div>
        <div class="research-entry-cell"><strong>${escapeHtml(formatDate(item.later_new_business_month))}</strong><span>later new-business record</span></div>
        <div class="research-signal-cell" data-label="CIPO">${signalCell("CIPO_CANADIAN_TRADEMARK")}</div>
        <div class="research-signal-cell" data-label="TED">${signalCell("TED_CONTRACT_AWARD")}</div>
        <div class="research-signal-cell" data-label="CanadaBuys">${signalCell("CANADABUYS_AWARD")}</div>
      </div>
      <details class="research-detail">
        <summary>View identity & source evidence</summary>
        <div class="research-detail-body">
          <div class="research-detail-column">
            <h4>Research context</h4>
            <dl class="research-detail-facts"><div><dt>Identity confidence</dt><dd>${escapeHtml(item.identity_confidence || "Unknown")}</dd></div><div><dt>Matched stratum</dt><dd>${matched || "Not recorded"}</dd></div><div><dt>Investor locality</dt><dd>${escapeHtml(item.investor_locality || "Not recorded")}</dd></div></dl>
            <p>${escapeHtml(item.rationale || "Identity-qualified historical research entity.")}</p>
          </div>
          <div class="research-detail-column"><h4>Historical signal analysis</h4><div class="research-detail-signals">${signalDetails}</div></div>
          <div class="research-detail-column research-detail-evidence"><h4>Primary identity evidence</h4><ul>${sources}</ul></div>
        </div>
        <p class="small muted research-boundary-note">Historical research entity · not a current expansion prediction · not a permanent negative.</p>
      </details>
    </article>`;
  }).join("");
}

function savedButton(item) {
  const saved = state.saved.has(item.id);
  return `<button class="save-button" type="button" data-save="${escapeHtml(item.id)}" aria-pressed="${saved}" aria-label="${saved ? "Unsave" : "Save"} ${escapeHtml(item.canadian_business_name)}" title="${saved ? "Remove from saved cases" : "Save in this browser"}">${saved ? "★" : "☆"}</button>`;
}
function renderCases() {
  if(!state.data){els.caseCountLabel.textContent="Data unavailable—not zero cases";return;}
  const cases = filteredCases();
  els.caseCountLabel.textContent = `${cases.length} of ${state.data.cases.length} historical cases${state.view === "saved" ? " · saved in this browser" : ""}`;
  document.querySelectorAll("[data-view]").forEach(button => button.setAttribute("aria-pressed",String(button.dataset.view === state.view)));
  $("saved-count").textContent = state.saved.size;
  if (!cases.length) {
    els.casesBody.replaceChildren(els.emptyRowTemplate.content.cloneNode(true));
    if (state.view === "saved" && !state.saved.size) {
      els.casesBody.querySelector("h3").textContent = "No saved cases yet.";
      els.casesBody.querySelector("p").textContent = "Use the star beside a company to save its case in this browser. Your saved list is not shared or synced.";
      els.casesBody.querySelector("[data-reset]").textContent = "Browse all cases";
    }
    return;
  }
  els.casesBody.innerHTML = cases.map(item => { const mobileEvidence = earlyEvidence(item) ? `${item.verified_pre_notification_evidence_count} early public` : item.evidence_count ? `${item.evidence_count} source item${item.evidence_count === 1 ? "" : "s"}` : "Registry only"; return `<tr class="case-row" tabindex="0" data-case-id="${escapeHtml(item.id)}" aria-label="Open evidence for ${escapeHtml(item.canadian_business_name)}"><td data-label="Canadian business"><a class="company-name" href="${escapeHtml(caseHash(item.id))}">${escapeHtml(item.canadian_business_name)}</a><div class="company-meta">${escapeHtml(item.canadian_business_activity || "Business activity not recorded")}</div><div class="mobile-case-scan"><span>${escapeHtml(item.ultimate_control_country || "Control unknown")}</span><span>${escapeHtml(formatDate(item.notification_month))}</span><span>${escapeHtml(mobileEvidence)}</span><span class="status-chip ${classificationClass(item.outcome_classification)}">${escapeHtml(formatClassification(item.outcome_classification))}</span></div></td><td data-label="Named investor / control"><div class="investor-name">${escapeHtml(item.investor_name || "Investor unresolved")}</div><div class="investor-meta">${escapeHtml(item.ultimate_control_country || "Control country unknown")}</div></td><td data-label="Notification month">${escapeHtml(formatDate(item.notification_month))}</td><td class="evidence-value" data-label="Evidence to explore"><strong>${escapeHtml(item.evidence_count)}</strong> additional source item${item.evidence_count === 1 ? "" : "s"}<span class="early-hint">${earlyEvidence(item) ? `${item.verified_pre_notification_evidence_count} public before notification` : item.evidence_count ? "No verified earlier public evidence attached" : "Registry only · needs research"}</span></td><td data-label="What we know"><span class="status-chip ${classificationClass(item.outcome_classification)}">${escapeHtml(formatClassification(item.outcome_classification))}</span></td><td>${savedButton(item)}</td></tr>`; }).join("");
}
function caseHash(id) {
  const params = filterParams();
  params.set("case",id);
  return `#companies?${params}`;
}
function filterParams() {
  const params = new URLSearchParams();
  for (const [key,value] of [["q",state.query],["country",state.country],["finding",state.classification],["evidence",state.evidence],["sort",state.sort === "name" ? "" : state.sort],["view",state.view === "all" ? "" : state.view]]) if(value) params.set(key,value);
  return params;
}
function syncFilterUrl() { const p=filterParams(); history.replaceState(null,"",`#companies${p.size ? "?"+p : ""}`); }
function resetFilters() {
  state.query="";state.classification="";state.evidence="";state.country="";state.sort="name";state.view="all";
  syncControls();renderCases();syncFilterUrl();els.caseSearch.focus();
}
function syncControls() {
  els.caseSearch.value=state.query;els.classificationFilter.value=state.classification;els.evidenceFilter.value=state.evidence;$("country-filter").value=state.country;$("sort-order").value=state.sort;
}
function showToast(message) { clearTimeout(toastTimer);$("toast").textContent=message;$("toast").hidden=false;toastTimer=setTimeout(()=>{$("toast").hidden=true;},5000); }
function loadSaved() {
  if(!state.data)return;
  try {
    const value=JSON.parse(localStorage.getItem(SAVE_KEY)||"[]");
    if (!Array.isArray(value)) throw new Error("Invalid saved list");
    const valid=new Set(state.data.cases.map(x=>x.id));state.saved=new Set(value.filter(x=>typeof x === "string" && valid.has(x)));
  } catch (_) {state.saved=new Set();showToast("Saved cases could not be loaded. You can still explore all the evidence.");}
}
function toggleSaved(id) {
  if(!state.data)return;
  if (!state.data.cases.some(x=>x.id===id)) return;
  const next=new Set(state.saved);next.has(id)?next.delete(id):next.add(id);
  try {localStorage.setItem(SAVE_KEY,JSON.stringify([...next]));} catch (_) {showToast("This browser could not save the case. Nothing was saved; use the case link instead.");return;}
  state.saved=next;renderCases();
  if(!state.caseId){const replacement=[...els.casesBody.querySelectorAll("[data-save]")].find(x=>x.dataset.save===id);(replacement || els.caseSearch).focus();}
  const detailSave=$("detail-save");if(detailSave && state.caseId === id){detailSave.textContent=next.has(id)?"★ Saved in this browser":"☆ Save this case";detailSave.setAttribute("aria-pressed",String(next.has(id)));}
  showToast(next.has(id)?"Case saved in this browser only.":"Case removed from your saved list.");
}
function caseSummary(item) {
  const found=formatClassification(item.outcome_classification);
  let known=item.audit_note || "This historical case is recorded in the audited Investment Canada new-business cohort.";
  let unknown="The exact first Canadian operations date is not established. Expansion likelihood is not validated, and Canadian market fit is not assessed here.";
  let next="Establish the first operating window and verify when each supporting source became public. Do not treat the filing month as the opening date.";
  if(item.outcome_classification === "EXISTING_CANADIAN_PRESENCE") next="Separate prior Canadian activity from the notified business event, and verify the parent-to-business identity link before treating this as a new-entry case.";
  if(!item.evidence_count) next="Locate original company or government evidence beyond the registry, confirm the investor identity, and establish what the Canadian business actually did.";
  if(item.first_canadian_operations_date) unknown="A first-operations date is recorded below. That alone does not validate a predictive score or establish Canadian market fit.";
  return `<div class="case-summary"><article class="summary-block"><h3>What we know · ${escapeHtml(found)}</h3><p>${escapeHtml(known)}</p></article><article class="summary-block unknown"><h3>What remains unknown</h3><p>${escapeHtml(unknown)}</p></article><article class="summary-block next"><h3>Next research step</h3><p>${escapeHtml(next)}</p></article></div>`;
}
function openCase(id) {
  const item=state.data.cases.find(x=>x.id===id);if(!item)return;
  if(!state.caseId) returnFocus=document.activeElement;
  state.caseId=id;els.drawerTitle.textContent=item.canadian_business_name;
  els.drawerContent.innerHTML=`<div class="drawer-tools"><button class="button" id="detail-save" type="button" data-save="${escapeHtml(id)}" aria-pressed="${state.saved.has(id)}">${state.saved.has(id)?"★ Saved in this browser":"☆ Save this case"}</button><button class="button" id="copy-case-link" type="button">Copy case link</button><span class="small muted">Historical case · not a prediction</span></div><div id="case-link-fallback" hidden></div><section class="detail-hero" id="detail-summary"><h3 class="detail-business">${escapeHtml(item.canadian_business_name)}</h3><p class="detail-activity">${escapeHtml(item.canadian_business_activity || "No activity description recorded.")}</p><div class="detail-grid"><div class="detail-stat"><span>Named investor (not necessarily the foreign parent)</span><strong>${escapeHtml(item.investor_name || "Unknown")}</strong></div><div class="detail-stat"><span>Country of ultimate control</span><strong>${escapeHtml(item.ultimate_control_country || "Unknown")}</strong></div><div class="detail-stat"><span>Federal incorporation</span><strong>${escapeHtml(formatDate(item.incorporation_date))}</strong></div><div class="detail-stat"><span>Investment Canada notification month</span><strong>${escapeHtml(formatDate(item.notification_month))}</strong></div><div class="detail-stat"><span>Exact first-operation model label</span><strong>${item.model_eligible?"Eligible under the recorded audit gate":"Not eligible"}</strong></div><div class="detail-stat"><span>First Canadian operations</span><strong>${escapeHtml(formatDate(item.first_canadian_operations_date))}</strong></div><div class="detail-stat"><span>Corporation number / registry status</span><strong>${escapeHtml(item.corporation_number || "Unknown")} · ${escapeHtml(item.registry_status || "Unknown")}</strong></div><div class="detail-stat"><span>Registry lead (not an operating lead)</span><strong>${escapeHtml(leadLabel(item.days_before_notification_month))}</strong></div></div></section>${caseSummary(item)}<nav class="detail-jumps" aria-label="Case sections"><button class="text-button" data-jump="detail-summary">Case summary</button><button class="text-button" data-jump="detail-timeline">Timeline</button><button class="text-button" data-jump="detail-sources">Original sources</button></nav><section class="detail-section" id="detail-timeline"><h3>Evidence timeline</h3>${renderCaseTimeline(item)}</section><section class="detail-section" id="detail-sources"><h3>Original sources · Evidence ledger</h3>${renderEvidence(item.evidence || [])}</section>`;
  els.drawerBackdrop.hidden=false;els.drawer.inert=false;els.drawer.classList.add("open");els.drawer.setAttribute("aria-hidden","false");$("app-shell").inert=true;document.body.style.overflow="hidden";els.drawerContent.scrollTop=0;els.drawerClose.focus();
}
function hideDrawer() {
  const wasOpen=state.caseId;state.caseId=null;els.drawer.classList.remove("open");els.drawer.setAttribute("aria-hidden","true");els.drawer.inert=true;els.drawerBackdrop.hidden=true;$("app-shell").inert=false;document.body.style.overflow="";
  if(wasOpen && returnFocus?.isConnected) returnFocus.focus();
  else if(wasOpen) els.caseSearch.focus();
}
function closeDrawer() {hideDrawer();const p=filterParams();history.replaceState(null,"",`#companies${p.size?"?"+p:""}`);}
async function copyCaseLink() {
  const url=new URL(location.href);url.hash=`#companies?case=${encodeURIComponent(state.caseId)}`;
  try {if(!navigator.clipboard?.writeText)throw new Error("Clipboard unavailable");await navigator.clipboard.writeText(url.href);showToast("Case link copied. Your saved list is not included.");}
  catch(_){const fallback=$("case-link-fallback");fallback.hidden=false;fallback.innerHTML='<label class="small">Copy this case link<input class="copied-link" readonly aria-label="Case link"></label>';const input=fallback.querySelector("input");input.value=url.href;input.focus();input.select();showToast("Clipboard unavailable. Select and copy the case link shown here.");}
}
function route() {
  if(!state.data && !state.live)return;
  const [raw="overview",search=""]=location.hash.slice(1).split("?");
  if(raw === "main-content"){$("main-content").focus();return;}
  if(!workCanNavigate(location.hash))return;
  const valid=["overview","signals","companies","research","markets","coverage","guide","company","worklist"];
  const previousRoute=state.route;
  const requested=raw||"overview";state.route=valid.includes(requested)?requested:"overview";
  const p=new URLSearchParams(search);
  if(previousRoute!==state.route){$("main-content").focus({preventScroll:true});window.scrollTo(0,0);}
  document.title=`AtlanticBridge Signals — ${{overview:"Overview",signals:"Current signals",companies:"Company cases",research:"Research cohort",markets:"Canadian markets",coverage:"Evidence coverage",guide:"How to use",company:"Company dossier",worklist:"Company worklist"}[state.route]}`;
  $("route-notice").hidden=valid.includes(requested);
  if(!valid.includes(requested))$("route-notice").textContent="That view was not found. Showing the overview instead.";
  document.querySelectorAll("[data-route]").forEach(section=>{section.hidden=section.dataset.route!==state.route;});
  document.querySelectorAll("[data-nav]").forEach(link=>{if(link.dataset.nav===state.route)link.setAttribute("aria-current","page");else link.removeAttribute("aria-current");});
  if(state.route === "signals") {
    state.signalQuery=p.get("q")||"";
    state.signalCountry=p.get("country")||"";
    state.signalWindow=["30","90","180","all"].includes(p.get("window"))?p.get("window"):"90";
    state.signalView=p.get("view")==="watched"?"watched":"all";
    if(state.signalCountry && ![...$("signal-country-filter").options].some(o=>o.value===state.signalCountry)){const o=new Option(`Not in current feed: ${state.signalCountry}`,state.signalCountry);$("signal-country-filter").add(o);}
    syncSignalControls();renderSignals();
  }
  if(state.route === "companies" && state.data) {
    state.query=p.get("q")||"";state.country=p.get("country")||"";state.classification=p.get("finding")||"";state.evidence=["with","without"].includes(p.get("evidence"))?p.get("evidence"):"";state.sort=["newest","evidence"].includes(p.get("sort"))?p.get("sort"):"name";state.view=["early","registry","saved"].includes(p.get("view"))?p.get("view"):"all";
    // Keep unsupported filters visible as a recoverable empty state, not silently broader results.
    for(const [id,value] of [["country-filter",state.country],["classification-filter",state.classification]])if(value && ![...$(id).options].some(o=>o.value===value)){const o=new Option(`Not in this audit: ${value}`,value);$(id).add(o);}
    syncControls();renderCases();
    const id=p.get("case");if(id && state.data.cases.some(x=>x.id===id)){openCase(id);return;}
    if(id){$("route-notice").textContent="That case is not in this audited dataset. Search the available cases below.";$("route-notice").hidden=false;}
  }
  if(state.route === "research" && state.data) {
    state.researchQuery=p.get("q")||"";
    state.researchRole=["ACCEPTED_BACKTEST_CONTROL","IDENTITY_QUALIFIED_RESEARCH_CONTROL"].includes(p.get("role"))?p.get("role"):"";
    state.researchCipo=["PRESENT","ABSENT_WITH_PROVEN_COVERAGE","UNKNOWN_UNVERIFIED_COVERAGE"].includes(p.get("cipo"))?p.get("cipo"):"";
    state.researchSort=["name","entry"].includes(p.get("sort"))?p.get("sort"):"signal";
    syncResearchControls();
    renderResearch();
  }
  if(["companies","research","coverage"].includes(state.route) && !state.data){$("route-notice").hidden=false;$("route-notice").textContent="Audited case evidence is unavailable—not zero cases. Your worklist remains available.";}
  if(state.route === "worklist") {workQuery=p.get("q")||"";workStatus=Object.hasOwn(ABWorkspace.STATUSES,p.get("status"))?p.get("status"):"";workDue=p.get("due")==="1";renderWorklist();}
  if(state.route === "company") renderCompany(p.get("id") || "");
  hideDrawer();if(state.route!=="company")document.title=`AtlanticBridge Signals — ${{overview:"Overview",signals:"Current signals",companies:"Company cases",research:"Research cohort",markets:"Canadian markets",coverage:"Evidence coverage",guide:"How to use",company:"Company dossier",worklist:"Company worklist"}[state.route]}`;
}
function bindEvents() {
  bindWorkEvents();
  const mobileFilters=window.matchMedia("(max-width:760px)");
  if(mobileFilters.matches)$("advanced-filters").open=false;
  mobileFilters.addEventListener("change",event=>{if(!event.matches)$("advanced-filters").open=true;});
  for(const [node,key,event] of [[els.caseSearch,"query","input"],[els.classificationFilter,"classification","change"],[els.evidenceFilter,"evidence","change"],[$("country-filter"),"country","change"],[$("sort-order"),"sort","change"]])node.addEventListener(event,()=>{state[key]=node.value;renderCases();syncFilterUrl();});
  document.querySelectorAll("[data-view]").forEach(button=>button.addEventListener("click",()=>{state.view=button.dataset.view;renderCases();syncFilterUrl();}));
  $("reset-filters").addEventListener("click",resetFilters);
  for(const [node,key,event] of [[$("signal-search"),"signalQuery","input"],[$("signal-country-filter"),"signalCountry","change"],[$("signal-window"),"signalWindow","change"]])node.addEventListener(event,()=>{state[key]=node.value;renderSignals();syncSignalUrl();});
  document.querySelectorAll("[data-signal-view]").forEach(button=>button.addEventListener("click",()=>{state.signalView=button.dataset.signalView;renderSignals();syncSignalUrl();}));
  $("signal-reset").addEventListener("click",resetSignalFilters);
  $("signals-list").addEventListener("click",event=>{const watch=event.target.closest("[data-watch-company]");if(watch){toggleWatched(watch.dataset.watchCompany);return;}if(event.target.closest("[data-signal-reset]"))resetSignalFilters();});
  for(const [node,key,event] of [[$("research-search"),"researchQuery","input"],[$("research-role-filter"),"researchRole","change"],[$("research-cipo-filter"),"researchCipo","change"],[$("research-sort"),"researchSort","change"]])node.addEventListener(event,()=>{state[key]=node.value;renderResearch();syncResearchUrl();});
  $("research-reset").addEventListener("click",resetResearchFilters);
  $("research-companies").addEventListener("click",event=>{if(event.target.closest("[data-research-reset]"))resetResearchFilters();});
  els.casesBody.addEventListener("click",event=>{
    if(event.target.closest("[data-reset]")){resetFilters();return;}
    const save=event.target.closest("[data-save]");if(save){toggleSaved(save.dataset.save);return;}
    const row=event.target.closest("[data-case-id]");if(row){if(event.target.closest("a"))return;location.hash=caseHash(row.dataset.caseId);}
  });
  els.casesBody.addEventListener("keydown",event=>{if(event.target.matches(".case-row") && ["Enter"," "].includes(event.key)){event.preventDefault();location.hash=caseHash(event.target.dataset.caseId);}});
  els.drawerContent.addEventListener("click",event=>{const save=event.target.closest("[data-save]");if(save)toggleSaved(save.dataset.save);if(event.target.closest("#copy-case-link"))copyCaseLink();const jump=event.target.closest("[data-jump]");if(jump)$(jump.dataset.jump).scrollIntoView({behavior:"auto",block:"start"});});
  els.drawerClose.addEventListener("click",closeDrawer);els.drawerBackdrop.addEventListener("click",closeDrawer);
  document.addEventListener("keydown",event=>{if(!state.caseId)return;if(event.key==="Escape"){event.preventDefault();closeDrawer();}if(event.key==="Tab"){const focusable=[...els.drawer.querySelectorAll('button:not(:disabled),a[href],input,select,[tabindex="0"]')].filter(x=>x.getClientRects().length);const first=focusable[0],last=focusable.at(-1);if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}}});
  window.addEventListener("hashchange",route);
  window.addEventListener("storage",event=>{if(event.key===SAVE_KEY){loadSaved();renderCases();if(state.caseId){const button=$("detail-save");const saved=state.saved.has(state.caseId);button.textContent=saved?"★ Saved in this browser":"☆ Save this case";button.setAttribute("aria-pressed",String(saved));}}if(event.key===WATCH_KEY){loadWatched();renderSignals();}});
}
function validatePayload(data) {
  if(!data || !data.summary || !Array.isArray(data.cases) || data.summary.case_count!==data.cases.length || !Array.isArray(data.research_cohort) || data.summary.research_cohort_count!==data.research_cohort.length)throw new Error("Invalid case payload");
  if(new Set(data.cases.map(x=>x.id)).size!==data.cases.length)throw new Error("Duplicate case IDs");
  if(new Set(data.research_cohort.map(x=>x.id)).size!==data.research_cohort.length)throw new Error("Duplicate research IDs");
  for(const x of data.research_cohort)if(!Array.isArray(x.signal_analysis) || x.signal_analysis.length!==3)throw new Error("Invalid research signal analysis");
  if(data.summary.browsable_company_count!==data.cases.length+data.research_cohort.length)throw new Error("Invalid browsable company count");
  for(const x of data.cases)if(typeof x.id!=="string" || !x.id || !Array.isArray(x.evidence) || x.evidence_count!==x.evidence.length || typeof x.model_eligible!=="boolean")throw new Error("Invalid case record");
  return data;
}
function validateLivePayload(data) {
  if(!data || data.schema_version!==1 || !["ACTIVE","UNAVAILABLE"].includes(data.status) || !data.summary || !Array.isArray(data.signals))throw new Error("Invalid live signal payload");
  if(data.status==="ACTIVE"){
    if(data.summary.signal_count!==data.signals.length)throw new Error("Invalid live signal count");
    if(new Set(data.signals.map(x=>x.id)).size!==data.signals.length)throw new Error("Duplicate live signal IDs");
    for(const x of data.signals)if(typeof x.id!=="string" || !x.company_id || !x.company_name || x.signal_family!=="CANADABUYS_AWARD" || x.source_confidence!=="SOURCE_CONFIRMED")throw new Error("Invalid live signal record");
    if(data.summary.company_count!==new Set(data.signals.map(x=>x.company_id)).size)throw new Error("Invalid live company count");
  }
  return data;
}

async function init() {
  bindEvents();
  async function fetchEvidence(path, validate) {
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),15000);
    try {const response=await fetch(path,{cache:"no-store",signal:controller.signal});if(!response.ok)throw new Error(`Evidence HTTP ${response.status}`);return validate(await response.json());}
    finally {clearTimeout(timer);}
  }
  const results=await Promise.allSettled([
    fetchEvidence("data/dashboard.json",validatePayload),
    fetchEvidence("data/live-signals.json",validateLivePayload),
  ]);
  state.data=results[0].status==="fulfilled"?results[0].value:null;
  state.live=results[1].status==="fulfilled"?results[1].value:unavailableLivePayload("The current signal source could not be loaded. Saved work and available historical evidence remain accessible.");
  loadWatched();renderMetrics();renderSignals();
  if(state.data){loadSaved();renderSources();renderResearch();renderCases();$("load-status").hidden=true;}
  else {
    $("load-status").setAttribute("role","alert");$("load-status").innerHTML='Audited case evidence could not be loaded. No results or scores have been inferred. Current signals and your saved worklist remain independent. <button class="button" id="retry-load" type="button">Try again</button>';
    $("retry-load").addEventListener("click",()=>location.reload());els.caseCountLabel.textContent="Data unavailable—not zero cases";
  }
  route();
}
init();
