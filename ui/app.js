(() => {
  "use strict";

  const DATA_CANDIDATES = [
    "./data/outcome-audit.json",
    "../reviews/outcome_audit/2026-09-20-cases.json",
    "https://raw.githubusercontent.com/JeremyHennessy/AtlanticBridge-Signals/main/reviews/outcome_audit/2026-09-20-cases.json",
  ];

  const VIEW_TITLES = {
    overview: "Evidence overview",
    cases: "Audited cases",
    evidence: "Evidence ledger",
    sources: "Source coverage",
  };

  const STATUS_LABELS = {
    VERIFIED_BEFORE_NOTIFICATION_MONTH: "Verified before notification",
    VERIFIED_DURING_NOTIFICATION_MONTH: "Verified during notification month",
    VERIFIED_AFTER_NOTIFICATION_MONTH: "Verified after notification",
    OVERLAPS_NOTIFICATION_MONTH: "Overlaps notification month",
    UNVERIFIED: "Historical availability unverified",
  };

  const SOURCE_FAMILIES = [
    ["Investment Canada", "Historical outcome labels", "Federal notification and review decisions anchor the outcome cohort."],
    ["Corporations Canada", "Entity and change detection", "Federal corporation baselines, changes and certificate timing support Canadian-entry evidence."],
    ["CORDIS / Horizon Europe", "Relationship graph", "EU organizations sharing funded projects with Canadian organizations provide relationship signals."],
    ["GLEIF", "Legal-entity identity", "Candidate LEIs and accounting-parent relationships support conservative identity resolution."],
    ["TED", "Commercial maturity", "EU procurement contract-award notices provide source-backed winner and market evidence."],
    ["CIPO", "Canada-specific IP", "Trademark records provide market-intent evidence with publication timing separated from filing timing."],
    ["CanadaBuys", "Canadian procurement", "Federal award notices provide supplier evidence without assuming absent awards are negative signals."],
    ["Statistics Canada", "Market context", "Nova Scotia and Canada trade context supports market interpretation, not company-level outcome labels."],
  ];

  const state = {
    payload: null,
    cases: [],
    evidence: [],
    currentView: "overview",
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function safeUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch {
      return null;
    }
  }

  function monthBounds(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
    if (!match) throw new Error(`Invalid notification month: ${value}`);
    const year = Number(match[1]);
    const monthIndex = Number(match[2]) - 1;
    return [new Date(Date.UTC(year, monthIndex, 1)), new Date(Date.UTC(year, monthIndex + 1, 0))];
  }

  function datedBounds(value, precision) {
    const p = String(precision || "").toUpperCase();
    if (p === "DAY") {
      const d = new Date(`${value}T00:00:00Z`);
      if (Number.isNaN(d.valueOf())) throw new Error(`Invalid day: ${value}`);
      return [d, d];
    }
    if (p === "MONTH") return monthBounds(value);
    if (p === "YEAR") {
      const year = Number(value);
      if (!Number.isInteger(year)) throw new Error(`Invalid year: ${value}`);
      return [new Date(Date.UTC(year, 0, 1)), new Date(Date.UTC(year, 11, 31))];
    }
    throw new Error(`Invalid publication precision: ${precision}`);
  }

  function publicationStatus(evidence, notificationMonth) {
    const value = String(evidence.publicly_available_date || "").trim();
    const precision = String(evidence.publicly_available_date_precision || "").trim().toUpperCase();
    if (!value || !precision) return "UNVERIFIED";

    try {
      const [eStart, eEnd] = datedBounds(value, precision);
      const [nStart, nEnd] = monthBounds(notificationMonth);
      if (eEnd < nStart) return "VERIFIED_BEFORE_NOTIFICATION_MONTH";
      if (eStart > nEnd) return "VERIFIED_AFTER_NOTIFICATION_MONTH";
      if (eStart >= nStart && eEnd <= nEnd) return "VERIFIED_DURING_NOTIFICATION_MONTH";
      return "OVERLAPS_NOTIFICATION_MONTH";
    } catch {
      return "UNVERIFIED";
    }
  }

  function statusBadgeClass(status) {
    if (status === "VERIFIED_BEFORE_NOTIFICATION_MONTH") return "badge badge-positive";
    if (status === "VERIFIED_DURING_NOTIFICATION_MONTH") return "badge badge-blue";
    if (status === "VERIFIED_AFTER_NOTIFICATION_MONTH") return "badge badge-warning";
    if (status === "OVERLAPS_NOTIFICATION_MONTH") return "badge badge-warning";
    return "badge badge-neutral";
  }

  function classificationLabel(value) {
    const known = {
      EXISTING_CANADIAN_PRESENCE: "Existing Canadian presence",
      ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED: "Establishment corroborated; operations unresolved",
      UNRESOLVED: "Unresolved",
    };
    return known[value] || String(value || "Unclassified").toLowerCase().replaceAll("_", " ").replace(/^./, c => c.toUpperCase());
  }

  function compactStatus(value) {
    return STATUS_LABELS[value] || value;
  }

  function formatMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value || ""));
    if (!match) return value || "—";
    return new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "short", timeZone: "UTC" })
      .format(new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1)));
  }

  function normalizeData(payload) {
    if (!payload || !Array.isArray(payload.cases)) throw new Error("Outcome audit payload does not contain a cases array.");

    const cases = payload.cases.map((item) => {
      const evidence = Array.isArray(item.additional_evidence) ? item.additional_evidence : [];
      const statuses = evidence.map((entry) => publicationStatus(entry, item.notification_month));
      return {
        ...item,
        _evidenceStatuses: statuses,
        _verifiedBefore: statuses.filter((status) => status === "VERIFIED_BEFORE_NOTIFICATION_MONTH").length,
      };
    });

    const evidence = [];
    cases.forEach((caseItem) => {
      (caseItem.additional_evidence || []).forEach((entry, index) => {
        evidence.push({
          ...entry,
          _caseId: caseItem.outcome_record_id,
          _investorName: caseItem.investor_name,
          _businessName: caseItem.canadian_business_name,
          _notificationMonth: caseItem.notification_month,
          _status: caseItem._evidenceStatuses[index],
        });
      });
    });

    return { cases, evidence };
  }

  function summarize() {
    const statuses = {};
    state.evidence.forEach((entry) => { statuses[entry._status] = (statuses[entry._status] || 0) + 1; });
    return {
      caseCount: state.cases.length,
      evidenceCount: state.evidence.length,
      verifiedCaseCount: state.cases.filter((item) => item._verifiedBefore > 0).length,
      modelEligibleCount: state.cases.filter((item) => Boolean(item.model_eligible)).length,
      firstOperationCount: state.cases.filter((item) => Boolean(item.first_canadian_operations_date)).length,
      beforeMonth: state.cases.filter((item) => item.notification_timing === "BEFORE_NOTIFICATION_MONTH").length,
      sameMonth: state.cases.filter((item) => item.notification_timing === "SAME_MONTH").length,
      statuses,
    };
  }

  function metricCard(label, value, note) {
    const card = el("div", "metric-card");
    card.append(el("span", "metric-label", label), el("strong", "metric-value", value), el("span", "metric-note", note));
    return card;
  }

  function renderOverview() {
    const summary = summarize();
    $("#guardrail-model-count").textContent = summary.modelEligibleCount;

    const metrics = $("#metric-grid");
    metrics.replaceChildren(
      metricCard("Audited outcomes", summary.caseCount, "Current targeted audit cohort"),
      metricCard("Evidence rows", summary.evidenceCount, "Additional source-backed evidence"),
      metricCard("Pre-notification proof", summary.verifiedCaseCount, "Cases with ≥1 verified public source before notification"),
      metricCard("First operations dated", summary.firstOperationCount, "Required for true first-entry timing"),
      metricCard("Model eligible", summary.modelEligibleCount, "Fail-closed until timing gates are met"),
      metricCard("Federal timing", `${summary.beforeMonth}/${summary.sameMonth}`, "Before month / same month"),
    );

    const funnelRows = [
      ["Audited outcomes", summary.caseCount],
      ["Verified pre-notification evidence", summary.verifiedCaseCount],
      ["First Canadian operations established", summary.firstOperationCount],
      ["Model eligible", summary.modelEligibleCount],
    ];
    const max = Math.max(summary.caseCount, 1);
    const funnel = $("#funnel");
    funnel.replaceChildren(...funnelRows.map(([label, value]) => {
      const row = el("div", "funnel-row");
      const track = el("div", "funnel-track");
      const fill = el("div", "funnel-fill");
      fill.style.width = `${Math.max((Number(value) / max) * 100, Number(value) > 0 ? 2 : 0)}%`;
      track.append(fill);
      row.append(el("span", "funnel-label", label), track, el("strong", "funnel-value", value));
      return row;
    }));

    const classCounts = new Map();
    state.cases.forEach((item) => classCounts.set(item.outcome_classification || "UNCLASSIFIED", (classCounts.get(item.outcome_classification || "UNCLASSIFIED") || 0) + 1));
    const mix = $("#classification-mix");
    mix.replaceChildren(...[...classCounts.entries()].sort((a, b) => b[1] - a[1]).map(([code, count]) => {
      const row = el("div", "classification-row");
      const name = el("div");
      name.append(el("span", "classification-name", classificationLabel(code)), el("span", "classification-code", code));
      row.append(name, el("strong", "classification-count", count));
      return row;
    }));

    const publication = $("#publication-summary");
    const ordered = [
      "VERIFIED_BEFORE_NOTIFICATION_MONTH",
      "VERIFIED_DURING_NOTIFICATION_MONTH",
      "VERIFIED_AFTER_NOTIFICATION_MONTH",
      "OVERLAPS_NOTIFICATION_MONTH",
      "UNVERIFIED",
    ];
    publication.replaceChildren(...ordered.map((status) => {
      const card = el("div", "publication-card");
      card.append(el("strong", "", summary.statuses[status] || 0), el("span", "", compactStatus(status)));
      return card;
    }));
  }

  function populateCaseFilters() {
    const countries = [...new Set(state.cases.map((item) => item.ultimate_control_country).filter(Boolean))].sort();
    const classifications = [...new Set(state.cases.map((item) => item.outcome_classification).filter(Boolean))].sort();
    const country = $("#country-filter");
    countries.forEach((value) => country.append(new Option(value, value)));
    const classification = $("#classification-filter");
    classifications.forEach((value) => classification.append(new Option(classificationLabel(value), value)));
  }

  function filteredCases() {
    const query = $("#case-search").value.trim().toLowerCase();
    const country = $("#country-filter").value;
    const classification = $("#classification-filter").value;
    const publication = $("#publication-filter").value;
    return state.cases.filter((item) => {
      const haystack = `${item.investor_name || ""} ${item.canadian_business_name || ""} ${item.canadian_business_activity || ""}`.toLowerCase();
      if (query && !haystack.includes(query)) return false;
      if (country && item.ultimate_control_country !== country) return false;
      if (classification && item.outcome_classification !== classification) return false;
      if (publication === "verified" && item._verifiedBefore === 0) return false;
      if (publication === "unverified" && item._verifiedBefore > 0) return false;
      return true;
    });
  }

  function caseRow(item) {
    const tr = document.createElement("tr");
    tr.tabIndex = 0;
    tr.setAttribute("role", "button");
    tr.setAttribute("aria-label", `Open ${item.canadian_business_name || item.investor_name}`);
    tr.addEventListener("click", () => openCase(item));
    tr.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); openCase(item); }
    });

    const company = el("td");
    company.append(el("span", "company-primary", item.canadian_business_name || "—"), el("span", "company-secondary", item.investor_name || "—"));
    tr.append(company);
    tr.append(el("td", "", item.ultimate_control_country || "—"));
    tr.append(el("td", "", formatMonth(item.notification_month)));

    const event = el("td");
    event.append(el("span", "company-primary", item.federal_event_date || "—"), el("span", "company-secondary", item.federal_event_type || "Federal event unavailable"));
    tr.append(event);

    const classification = el("td");
    classification.append(el("span", item.outcome_classification === "UNRESOLVED" ? "badge badge-warning" : "badge badge-neutral", classificationLabel(item.outcome_classification)));
    tr.append(classification);

    const evidence = el("td");
    evidence.append(el("span", item._verifiedBefore > 0 ? "badge badge-positive" : "badge badge-neutral", `${item._verifiedBefore} verified`));
    tr.append(evidence);
    return tr;
  }

  function renderCases() {
    const rows = filteredCases();
    $("#case-result-count").textContent = `${rows.length} of ${state.cases.length} cases`;
    const body = $("#case-table-body");
    body.replaceChildren(...rows.map(caseRow));
    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = el("td", "cell-muted", "No cases match the current filters.");
      td.colSpan = 6;
      tr.append(td);
      body.append(tr);
    }
  }

  function evidenceCard(item, compact = false) {
    const card = el("article", "evidence-card");
    const top = el("div", "evidence-card-top");
    const main = el("div");
    main.append(el("div", "evidence-company", `${item._businessName || ""}${item._investorName ? ` · ${item._investorName}` : ""}`), el("div", "evidence-claim", item.claim || "No claim text recorded."));
    top.append(main, el("span", statusBadgeClass(item._status), compactStatus(item._status)));
    card.append(top);

    const meta = el("div", "evidence-meta");
    const fields = [
      ["Source type", item.source_type || "—"],
      ["Notification", formatMonth(item._notificationMonth)],
      ["Source date", item.source_date || "—"],
      ["Public date", item.publicly_available_date || "Unverified"],
    ];
    if (!compact && item.supports) fields.push(["Supports", item.supports]);
    fields.forEach(([label, value]) => {
      const span = el("span");
      span.append(el("strong", "", `${label}: `), document.createTextNode(value));
      meta.append(span);
    });
    card.append(meta);

    const href = safeUrl(item.source_url);
    if (href) {
      const link = el("a", "source-link", "Open source ↗");
      link.href = href;
      link.target = "_blank";
      link.rel = "noreferrer noopener";
      card.append(link);
    }
    return card;
  }

  function populateEvidenceFilters() {
    const statuses = [...new Set(state.evidence.map((item) => item._status))].sort();
    const sourceTypes = [...new Set(state.evidence.map((item) => item.source_type).filter(Boolean))].sort();
    const statusSelect = $("#evidence-status-filter");
    statuses.forEach((value) => statusSelect.append(new Option(compactStatus(value), value)));
    const sourceSelect = $("#source-type-filter");
    sourceTypes.forEach((value) => sourceSelect.append(new Option(value.replaceAll("_", " "), value)));
  }

  function filteredEvidence() {
    const query = $("#evidence-search").value.trim().toLowerCase();
    const status = $("#evidence-status-filter").value;
    const source = $("#source-type-filter").value;
    return state.evidence.filter((item) => {
      const haystack = `${item.claim || ""} ${item._businessName || ""} ${item._investorName || ""} ${item.source_type || ""} ${item.supports || ""}`.toLowerCase();
      if (query && !haystack.includes(query)) return false;
      if (status && item._status !== status) return false;
      if (source && item.source_type !== source) return false;
      return true;
    });
  }

  function renderEvidence() {
    const rows = filteredEvidence();
    $("#evidence-result-count").textContent = `${rows.length} of ${state.evidence.length} evidence records`;
    const list = $("#evidence-list");
    if (!rows.length) {
      list.replaceChildren(el("div", "empty-state", "No evidence records match the current filters."));
      return;
    }
    list.replaceChildren(...rows.map((item) => evidenceCard(item)));
  }

  function renderSources() {
    const grid = $("#source-grid");
    grid.replaceChildren(...SOURCE_FAMILIES.map(([name, kind, description]) => {
      const card = el("article", "source-card");
      card.append(el("span", "source-kind", kind), el("h3", "", name), el("p", "", description));
      return card;
    }));
  }

  function detailItem(label, value) {
    const item = el("div", "detail-item");
    item.append(el("span", "", label), el("strong", "", value || "—"));
    return item;
  }

  function openCase(item) {
    $("#drawer-title").textContent = item.canadian_business_name || item.investor_name || "Case detail";
    const body = $("#drawer-body");
    body.replaceChildren();

    const summary = el("div", "detail-summary");
    summary.append(
      detailItem("Investor", item.investor_name),
      detailItem("Ultimate control", item.ultimate_control_country),
      detailItem("Notification", formatMonth(item.notification_month)),
      detailItem("Corporation", item.corporation_number),
      detailItem("Federal event", `${item.federal_event_type || "—"} · ${item.federal_event_date || "—"}`),
      detailItem("Model eligible", item.model_eligible ? "Yes" : "No"),
    );
    body.append(summary);

    const activity = el("section", "detail-section");
    activity.append(el("h3", "", "Canadian business activity"), el("p", "", item.canadian_business_activity || "No activity description recorded."));
    body.append(activity);

    const classification = el("section", "detail-section");
    classification.append(el("h3", "", "Audit classification"));
    classification.append(el("span", item.outcome_classification === "UNRESOLVED" ? "badge badge-warning" : "badge badge-neutral", classificationLabel(item.outcome_classification)));
    body.append(classification);

    const note = el("section", "detail-section");
    note.append(el("h3", "", "Audit note"), el("p", "", item.audit_note || "No audit note recorded."));
    body.append(note);

    const exclusion = el("section", "detail-section");
    exclusion.append(el("h3", "", "Why this case is not model-ready"), el("p", "", item.exclusion_reason || "No exclusion reason recorded."));
    body.append(exclusion);

    const evidenceSection = el("section", "detail-section");
    evidenceSection.append(el("h3", "", `Evidence (${(item.additional_evidence || []).length})`));
    const list = el("div", "detail-evidence");
    (item.additional_evidence || []).forEach((entry, index) => {
      list.append(evidenceCard({
        ...entry,
        _businessName: item.canadian_business_name,
        _investorName: item.investor_name,
        _notificationMonth: item.notification_month,
        _status: item._evidenceStatuses[index],
      }, true));
    });
    if (!(item.additional_evidence || []).length) list.append(el("div", "empty-state", "No additional evidence has been recorded for this case."));
    evidenceSection.append(list);
    body.append(evidenceSection);

    $("#drawer-backdrop").hidden = false;
    $("#detail-drawer").classList.add("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "false");
    $("#drawer-close").focus();
  }

  function closeDrawer() {
    $("#detail-drawer").classList.remove("is-open");
    $("#detail-drawer").setAttribute("aria-hidden", "true");
    $("#drawer-backdrop").hidden = true;
  }

  function switchView(view) {
    if (!VIEW_TITLES[view]) return;
    state.currentView = view;
    $("#view-title").textContent = VIEW_TITLES[view];
    $$("[data-view-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.viewPanel === view));
    $$("[data-view]").forEach((button) => button.classList.toggle("is-active", button.dataset.view === view));
    $(".sidebar").classList.remove("is-open");
    history.replaceState(null, "", `#${view}`);
  }

  async function loadAudit() {
    let lastError;
    for (const url of DATA_CANDIDATES) {
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        const payload = await response.json();
        const normalized = normalizeData(payload);
        state.payload = payload;
        state.cases = normalized.cases;
        state.evidence = normalized.evidence;
        return { url };
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("No audit data source was available.");
  }

  function bindEvents() {
    $$("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
    $$("[data-go-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.goView)));
    ["#case-search", "#country-filter", "#classification-filter", "#publication-filter"].forEach((selector) => $(selector).addEventListener("input", renderCases));
    ["#evidence-search", "#evidence-status-filter", "#source-type-filter"].forEach((selector) => $(selector).addEventListener("input", renderEvidence));
    $("#drawer-close").addEventListener("click", closeDrawer);
    $("#drawer-backdrop").addEventListener("click", closeDrawer);
    $("#mobile-menu").addEventListener("click", () => $(".sidebar").classList.toggle("is-open"));
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeDrawer(); });
  }

  async function init() {
    bindEvents();
    const initialHash = location.hash.replace("#", "");
    if (VIEW_TITLES[initialHash]) switchView(initialHash);

    try {
      const loaded = await loadAudit();
      populateCaseFilters();
      populateEvidenceFilters();
      renderOverview();
      renderCases();
      renderEvidence();
      renderSources();
      const dataState = $("#data-state");
      dataState.replaceChildren(el("span", "state-dot"), el("span", "", `${state.cases.length} audited cases · ${state.evidence.length} evidence rows`));
      dataState.title = `Loaded from ${loaded.url}`;
    } catch (error) {
      $("#load-error").hidden = false;
      $("#load-error-message").textContent = error instanceof Error ? error.message : String(error);
      $("#data-state").textContent = "Audit unavailable";
    }
  }

  init();
})();
