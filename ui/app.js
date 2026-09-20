const state = {
  data: null,
  query: "",
  classification: "",
  evidence: "",
};

const els = {
  auditDate: document.querySelector("#audit-date"),
  metricCases: document.querySelector("#metric-cases"),
  metricEvidence: document.querySelector("#metric-evidence"),
  metricIdentity: document.querySelector("#metric-identity"),
  metricModel: document.querySelector("#metric-model"),
  caseSearch: document.querySelector("#case-search"),
  classificationFilter: document.querySelector("#classification-filter"),
  evidenceFilter: document.querySelector("#evidence-filter"),
  caseCountLabel: document.querySelector("#case-count-label"),
  casesBody: document.querySelector("#cases-body"),
  emptyRowTemplate: document.querySelector("#empty-row-template"),
  coverageBefore: document.querySelector("#coverage-before"),
  coverageBeforeBar: document.querySelector("#coverage-before-bar"),
  coverageSame: document.querySelector("#coverage-same"),
  coverageSameBar: document.querySelector("#coverage-same-bar"),
  medianLead: document.querySelector("#median-lead"),
  sourceTypes: document.querySelector("#source-types"),
  drawer: document.querySelector("#case-drawer"),
  drawerTitle: document.querySelector("#drawer-title"),
  drawerContent: document.querySelector("#drawer-content"),
  drawerClose: document.querySelector("#drawer-close"),
  drawerBackdrop: document.querySelector("#drawer-backdrop"),
};

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
    EXISTING_CANADIAN_PRESENCE: "Existing Canadian presence",
    ESTABLISHMENT_CORROBORATED_OPERATIONS_UNRESOLVED: "Establishment corroborated",
    UNRESOLVED: "Unresolved",
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

function filteredCases() {
  if (!state.data) return [];
  const query = state.query.trim().toLowerCase();

  return state.data.cases.filter((item) => {
    if (
      query &&
      ![
        item.canadian_business_name,
        item.investor_name,
        item.ultimate_control_country,
        item.canadian_business_activity,
        item.corporation_number,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase()
        .includes(query)
    ) {
      return false;
    }

    if (state.classification && item.outcome_classification !== state.classification) {
      return false;
    }

    if (state.evidence === "with" && item.evidence_count === 0) return false;
    if (state.evidence === "without" && item.evidence_count > 0) return false;

    return true;
  });
}

function renderMetrics() {
  const summary = state.data.summary;
  els.auditDate.textContent = `Audit date ${state.data.audit_date || "—"}`;
  els.metricCases.textContent = summary.case_count;
  els.metricEvidence.textContent = `${summary.evidence_case_count}/${summary.case_count}`;
  els.metricIdentity.textContent = summary.identity_requires_review
    ? `${summary.identity_supported} supported`
    : `${summary.identity_supported}/${summary.identity_supported}`;
  els.metricModel.textContent = summary.model_eligible_count;

  const beforePct = summary.case_count
    ? (summary.before_notification_month / summary.case_count) * 100
    : 0;
  const samePct = summary.case_count
    ? (summary.same_notification_month / summary.case_count) * 100
    : 0;

  els.coverageBefore.textContent =
    `${summary.before_notification_month}/${summary.case_count}`;
  els.coverageSame.textContent =
    `${summary.same_notification_month}/${summary.case_count}`;
  els.coverageBeforeBar.style.width = `${beforePct}%`;
  els.coverageSameBar.style.width = `${samePct}%`;
  els.medianLead.textContent =
    summary.median_days_before_notification_month === null
      ? "—"
      : `${summary.median_days_before_notification_month} days`;
}

function renderSources() {
  const rows = Object.entries(state.data.summary.source_type_counts).slice(0, 8);
  els.sourceTypes.innerHTML = rows
    .map(
      ([source, count]) => `
        <div class="source-row">
          <span>${escapeHtml(formatSourceType(source))}</span>
          <span class="source-count">${escapeHtml(count)}</span>
        </div>
      `,
    )
    .join("");
}

function renderCases() {
  const cases = filteredCases();
  els.caseCountLabel.textContent = `${cases.length} of ${state.data.cases.length} cases`;

  if (!cases.length) {
    els.casesBody.replaceChildren(els.emptyRowTemplate.content.cloneNode(true));
    return;
  }

  els.casesBody.innerHTML = cases
    .map(
      (item) => `
        <tr
          class="case-row"
          tabindex="0"
          data-case-id="${escapeHtml(item.id)}"
          aria-label="Open evidence for ${escapeHtml(item.canadian_business_name)}"
        >
          <td>
            <div class="company-name">${escapeHtml(item.canadian_business_name)}</div>
            <div class="company-meta">
              Corp ${escapeHtml(item.corporation_number || "—")} ·
              ${escapeHtml(item.registry_status || "status unknown")}
            </div>
          </td>
          <td>
            <div class="investor-name">${escapeHtml(item.investor_name)}</div>
            <div class="investor-meta">${escapeHtml(item.ultimate_control_country || "control unknown")}</div>
          </td>
          <td class="date-value">${escapeHtml(formatDate(item.notification_month))}</td>
          <td class="lead-value">${escapeHtml(leadLabel(item.days_before_notification_month))}</td>
          <td class="evidence-value"><strong>${escapeHtml(item.evidence_count)}</strong> source item${item.evidence_count === 1 ? "" : "s"}</td>
          <td>
            <span class="status-chip ${classificationClass(item.outcome_classification)}">
              ${escapeHtml(formatClassification(item.outcome_classification))}
            </span>
          </td>
        </tr>
      `,
    )
    .join("");

  els.casesBody.querySelectorAll(".case-row").forEach((row) => {
    row.addEventListener("click", () => openCase(row.dataset.caseId));
    row.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openCase(row.dataset.caseId);
      }
    });
  });
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
          return `
            <article class="evidence-card">
              <div class="evidence-topline">
                <span class="evidence-type">${escapeHtml(formatSourceType(item.source_type))}</span>
                <span class="evidence-date">${escapeHtml(formatDate(primaryDate))}</span>
              </div>
              <p class="evidence-claim">${escapeHtml(item.claim || "No claim text recorded.")}</p>
              <div class="evidence-support">${escapeHtml(item.supports || "Evidence role unclassified")}</div>
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

function openCase(id) {
  const item = state.data.cases.find((caseItem) => caseItem.id === id);
  if (!item) return;

  els.drawerTitle.textContent = item.canadian_business_name;
  els.drawerContent.innerHTML = `
    <section class="detail-hero">
      <h3 class="detail-business">${escapeHtml(item.canadian_business_name)}</h3>
      <p class="detail-activity">${escapeHtml(item.canadian_business_activity || "No activity description recorded.")}</p>
      <div class="detail-grid">
        <div class="detail-stat">
          <span>Investor</span>
          <strong>${escapeHtml(item.investor_name)}</strong>
        </div>
        <div class="detail-stat">
          <span>Ultimate control</span>
          <strong>${escapeHtml(item.ultimate_control_country || "Unknown")}</strong>
        </div>
        <div class="detail-stat">
          <span>Incorporation</span>
          <strong>${escapeHtml(formatDate(item.incorporation_date))}</strong>
        </div>
        <div class="detail-stat">
          <span>Notification</span>
          <strong>${escapeHtml(formatDate(item.notification_month))}</strong>
        </div>
        <div class="detail-stat">
          <span>Model eligibility</span>
          <strong>${item.model_eligible ? "Eligible" : "Not eligible"}</strong>
        </div>
        <div class="detail-stat">
          <span>First operations</span>
          <strong>${escapeHtml(formatDate(item.first_canadian_operations_date))}</strong>
        </div>
      </div>
    </section>

    <section class="detail-section">
      <h3>Audit disposition</h3>
      <div class="status-chip ${classificationClass(item.outcome_classification)}">
        ${escapeHtml(formatClassification(item.outcome_classification))}
      </div>
      <div class="audit-note" style="margin-top: 10px;">
        ${escapeHtml(item.audit_note || "No audit note recorded.")}
      </div>
    </section>

    <section class="detail-section">
      <h3>Evidence</h3>
      ${renderEvidence(item.evidence)}
    </section>
  `;

  els.drawerBackdrop.hidden = false;
  els.drawer.classList.add("open");
  els.drawer.setAttribute("aria-hidden", "false");
  document.body.style.overflow = "hidden";
  els.drawerClose.focus();
}

function closeDrawer() {
  els.drawer.classList.remove("open");
  els.drawer.setAttribute("aria-hidden", "true");
  els.drawerBackdrop.hidden = true;
  document.body.style.overflow = "";
}

function bindEvents() {
  els.caseSearch.addEventListener("input", (event) => {
    state.query = event.target.value;
    renderCases();
  });
  els.classificationFilter.addEventListener("change", (event) => {
    state.classification = event.target.value;
    renderCases();
  });
  els.evidenceFilter.addEventListener("change", (event) => {
    state.evidence = event.target.value;
    renderCases();
  });
  els.drawerClose.addEventListener("click", closeDrawer);
  els.drawerBackdrop.addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && els.drawer.classList.contains("open")) {
      closeDrawer();
    }
  });
}

async function init() {
  bindEvents();

  try {
    const response = await fetch("data/dashboard.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Dashboard payload returned HTTP ${response.status}`);
    }
    state.data = await response.json();
    renderMetrics();
    renderSources();
    renderCases();
  } catch (error) {
    console.error(error);
    els.caseCountLabel.textContent = "Data unavailable";
    els.casesBody.innerHTML = `
      <tr>
        <td colspan="6">
          <div class="empty-state">
            The evidence payload could not be loaded. Serve the <code>ui/</code> directory
            over HTTP so <code>data/dashboard.json</code> is available.
          </div>
        </td>
      </tr>
    `;
  }
}

init();
