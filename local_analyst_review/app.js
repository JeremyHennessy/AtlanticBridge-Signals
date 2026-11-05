/* Standalone local evidence review. No network access or persistent storage. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { packet: null, decisions: new Map(), importGeneration: 0 };
  const allowedHosts = new Set(["www.bodacc.fr", "open.canada.ca", "data.novascotia.ca", "www.etalab.gouv.fr", "novascotia.ca"]);

  const DEMO_PACKET = {
    packet_version: 1,
    workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
    generated_at: "2026-11-04T00:00:00Z",
    lead_promotion_allowed: false,
    independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
    collections: [{
      source: "nova_scotia_awarded_public_tenders",
      evidence_class: "FIXTURE_DEMONSTRATION_NOT_LIVE",
      independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
      retrieved_at: null,
      records_returned: 1,
      coverage: "SYNTHETIC_EXAMPLE_ONLY",
      source_license: "Open Government Licence - Nova Scotia",
      attribution: "Contains information licensed under the Open Government Licence – Nova Scotia"
    }],
    findings: [{
      finding_id: "fixture-example-only-001",
      source: "nova_scotia_awarded_public_tenders",
      source_record_id: "SYNTHETIC-REF-001",
      entity_label: "Example Systems Ltd. (invented)",
      headline: "Synthetic awarded tender example",
      published_date: "2026-10-01",
      event_date: "2026-09-20",
      date_scope: "SYNTHETIC_EXAMPLE",
      retrieved_at: null,
      source_url: "https://data.novascotia.ca/Procurement-and-Contracts/Awarded-Public-Tenders/m6ps-8j6u",
      api_query_url: null,
      license: "Open Government Licence - Nova Scotia",
      license_url: "https://novascotia.ca/opendata/licence.asp",
      attribution: "Contains information licensed under the Open Government Licence – Nova Scotia",
      event_stage: "Synthetic supplier-award context, solely for layout demonstration",
      interpretation_limit: "This fixture is invented. It is not a source observation and does not evidence a real award or expansion.",
      source_facts: { "Tender ID": "SYNTHETIC-REF-001", "Reported amount": "Not real data" },
      evidence_class: "FIXTURE_DEMONSTRATION_NOT_LIVE",
      independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
      review_disposition: "UNREVIEWED_CONTEXT_ONLY",
      lead_eligible: false,
      lead_promotion_allowed: false
    }]
  };

  function setStatus(message, failed = false) {
    const node = $("packet-status");
    node.textContent = message;
    node.dataset.failed = failed ? "true" : "false";
  }

  function originLabel(value) {
    if (value === "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED") return "Collector envelope reports live query · not independently verified";
    if (value === "FIXTURE_DEMONSTRATION_NOT_LIVE") return "Collector envelope reports fixture · not live";
    return "Collector envelope origin unknown";
  }

  function yesNoUnknown(value) {
    return typeof value === "boolean" ? (value ? "Yes" : "No") : "Unknown";
  }

  function safeLink(value) {
    try {
      const u = new URL(value);
      if (u.protocol === "https:" && allowedHosts.has(u.hostname) && !u.username && !u.password && (u.port === "" || u.port === "443")) return u.href;
    } catch (_) {}
    return null;
  }

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) {
      node.textContent = ["string", "number", "boolean"].includes(typeof value) ? String(value) : "Unknown";
    }
    return node;
  }

  function addField(parent, label, value) {
    const wrapper = element("div", "field");
    wrapper.append(element("dt", "", label));
    wrapper.append(element("dd", "", value === undefined || value === null || value === "" ? "Unknown" : value));
    parent.append(wrapper);
  }

  function markdownText(value) {
    if (value === undefined || value === null || value === "") return "Unknown";
    if (!["string", "number", "boolean"].includes(typeof value)) return "Unknown";
    return String(value)
      .replace(/\\/g, "\\\\")
      .replace(/[\r\n]+/g, " ")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/([*_{}\[\]!#])/g, "\\$1")
      .split(String.fromCharCode(96)).join("&#96;");
  }

  function markdownBullet(label, value) {
    return "- **" + markdownText(label) + ":** " + markdownText(value);
  }

  function buildReviewBrief(packet, decisions) {
    const lines = [
      "# AtlanticBridge analyst evidence review",
      "",
      "> Context only — not a qualified lead, investment mandate, expansion prediction, or site-selection finding.",
      "",
      markdownBullet("Generated at", packet.generated_at),
      markdownBullet("Findings in packet", packet.findings.length),
      markdownBullet("Independent verification", "Not independently verified by this workflow"),
      markdownBullet("Lead promotion", "Not allowed"),
      "",
      "## Source coverage and provenance",
      ""
    ];

    for (const collection of packet.collections) {
      lines.push("### " + markdownText(collection.source || "Unknown source"));
      lines.push(markdownBullet("Collector origin", originLabel(collection.evidence_class)));
      lines.push(markdownBullet("Retrieved at", collection.retrieved_at));
      lines.push(markdownBullet("Coverage limit", collection.coverage));
      const coverage = collection.coverage_signals && typeof collection.coverage_signals === "object"
        ? collection.coverage_signals : {};
      lines.push(markdownBullet("Rows returned by API", coverage.records_returned_by_api));
      lines.push(markdownBullet("Exact identity matches reported by collector", coverage.records_matching_exact_query));
      lines.push(markdownBullet("More results beyond page", yesNoUnknown(coverage.api_query_has_more_results)));
      lines.push(markdownBullet("Page may be truncated", yesNoUnknown(coverage.page_may_be_truncated)));
      lines.push(markdownBullet("Freshness note", coverage.freshness_note));
      lines.push(markdownBullet("Licence", collection.source_license));
      lines.push(markdownBullet("Attribution", collection.attribution));
      lines.push(markdownBullet("Envelope response SHA-256 (reported, not authenticated)", collection.response_sha256));
      lines.push("");
    }

    lines.push("## Findings and analyst review");
    lines.push("");
    for (const finding of packet.findings) {
      const decision = decisions.get(finding.finding_id) || {};
      lines.push("### " + markdownText(finding.entity_label || "Entity unresolved") + " — " + markdownText(finding.headline || "Untitled evidence"));
      lines.push(markdownBullet("Finding origin", originLabel(finding.evidence_class)));
      lines.push(markdownBullet("Source", finding.source));
      lines.push(markdownBullet("Source record ID", finding.source_record_id));
      lines.push(markdownBullet("Expected identity filter", finding.expected_identity_filter));
      lines.push(markdownBullet("Requested identity criterion", finding.requested_identity_criterion));
      lines.push(markdownBullet("Identity match validation", finding.identity_match_verification === "NOT_VALIDATED_BY_PACKET" ? "Not validated by packet" : "Unknown"));
      lines.push(markdownBullet("Identity verification note", finding.identity_verification_note));
      lines.push(markdownBullet("Identity resolution limit", finding.identity_resolution_limit));
      lines.push(markdownBullet("Published / award date", finding.published_date));
      lines.push(markdownBullet("Event date", finding.event_date));
      lines.push(markdownBullet("Retrieved at", finding.retrieved_at));
      lines.push(markdownBullet("Event stage", finding.event_stage));
      lines.push(markdownBullet("Interpretation limit", finding.interpretation_limit));
      lines.push(markdownBullet("Source URL (approved host only)", safeLink(finding.source_url) || "Not supplied or unsupported"));
      lines.push(markdownBullet("Licence", finding.license));
      lines.push(markdownBullet("Attribution", finding.attribution));
      for (const [label, value] of Object.entries(finding.source_facts || {})) {
        if (value !== null && ["string", "number", "boolean"].includes(typeof value)) {
          lines.push(markdownBullet(label, value));
        }
      }
      lines.push(markdownBullet("Analyst disposition", decision.disposition || "UNREVIEWED_CONTEXT_ONLY"));
      lines.push(markdownBullet("Follow-up owner", decision.owner));
      lines.push(markdownBullet("Follow-up date", decision.follow_up_date));
      lines.push(markdownBullet("Counter-evidence / unresolved issue", decision.counter_evidence));
      lines.push(markdownBullet("Analyst note / next verification step", decision.note));
      lines.push(markdownBullet("Lead eligibility", "Not eligible; no automatic promotion"));
      lines.push("");
    }
    return lines.join("\n") + "\n";
  }

  function validatePacket(input) {
    if (!input || input.packet_version !== 1 || input.workflow_mode !== "LOCAL_ANALYST_REVIEW_ONLY") {
      throw new Error("Unsupported packet format. Build a local analyst review packet first.");
    }
    if (!Array.isArray(input.collections) || !Array.isArray(input.findings)) {
      throw new Error("Packet is missing collection or finding arrays.");
    }
    if (!input.collections.every((item) => item !== null && typeof item === "object" && !Array.isArray(item))) {
      throw new Error("Packet contains an invalid collection entry.");
    }
    const supportedSources = new Set([
      "bodacc_commercial_notices",
      "canada_federal_grants_contributions",
      "nova_scotia_awarded_public_tenders"
    ]);
    if (!input.collections.every((item) => typeof item.source === "string" && supportedSources.has(item.source))) {
      throw new Error("Packet contains an unsupported or invalid collection source.");
    }
    const findingIds = new Set();
    for (const finding of input.findings) {
      if (finding === null || typeof finding !== "object" || Array.isArray(finding)) {
        throw new Error("Packet contains an invalid finding entry.");
      }
      if (typeof finding.finding_id !== "string" || !finding.finding_id.trim() || finding.finding_id.length > 256 || findingIds.has(finding.finding_id)) {
        throw new Error("Each finding must have a unique stable identifier.");
      }
      findingIds.add(finding.finding_id);
      if (typeof finding.source !== "string" || !supportedSources.has(finding.source)) {
        throw new Error("Each finding must identify an approved source.");
      }
      if (finding.source_facts !== undefined && (finding.source_facts === null || typeof finding.source_facts !== "object" || Array.isArray(finding.source_facts))) {
        throw new Error("Packet contains invalid source facts.");
      }
    }
    return {
      ...input,
      lead_promotion_allowed: false,
      independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
      findings: input.findings.map((finding) => ({
        ...finding,
        evidence_class: ["LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED", "FIXTURE_DEMONSTRATION_NOT_LIVE"].includes(finding.evidence_class)
          ? finding.evidence_class : "LEGACY_ORIGIN_UNVERIFIED",
        independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
        lead_eligible: false,
        lead_promotion_allowed: false
      }))
    };
  }

  function render(packet, decisions = state.decisions) {
    const summaries = $("collection-summary");
    const findings = $("findings");
    const summaryCards = [];
    const findingCards = [];

    for (const collection of packet.collections) {
      const card = element("article", "collection-card");
      card.append(element("span", "origin", originLabel(collection.evidence_class)));
      card.append(element("h2", "", collection.source || "Unknown source"));
      const dl = element("dl", "compact");
      const coverage = collection.coverage_signals && typeof collection.coverage_signals === "object"
        ? collection.coverage_signals : {};
      addField(dl, "Retrieved", collection.retrieved_at || "Unknown");
      addField(dl, "Rows in packet", collection.records_returned ?? "Unknown");
      addField(dl, "Records returned by API", coverage.records_returned_by_api);
      addField(dl, "Exact identity matches", coverage.records_matching_exact_query);
      addField(dl, "Excluded by identity check", coverage.records_excluded_by_identity_check);
      addField(dl, "Total results for query", coverage.total_count_for_query);
      addField(dl, "More results beyond page", yesNoUnknown(coverage.api_query_has_more_results));
      addField(dl, "Page may be truncated", yesNoUnknown(coverage.page_may_be_truncated));
      addField(dl, "Source update frequency", coverage.source_update_frequency);
      addField(dl, "Freshness note", coverage.freshness_note);
      addField(dl, "Coverage limit", collection.coverage || "Unknown");
      addField(dl, "Envelope response SHA-256 (reported)", collection.response_sha256);
      addField(dl, "Licence", collection.source_license || "Unknown");
      card.append(dl);
      card.append(element("p", "attribution", collection.attribution || "Attribution not supplied"));
      card.append(element("p", "warning", "Independent review: not verified. Imported provenance labels are not authenticated."));
      summaryCards.push(card);
    }

    if (!packet.findings.length) {
      findingCards.push(element("div", "empty", "No source records were returned in this packet."));
    }

    for (const finding of packet.findings) {
      const card = element("article", "finding-card");
      const top = element("div", "finding-top");
      top.append(element("span", "origin", originLabel(finding.evidence_class)));
      top.append(element("span", "lock", "CONTEXT ONLY · NOT A LEAD"));
      card.append(top);
      card.append(element("p", "eyebrow", finding.source || "Source"));
      card.append(element("h2", "", finding.headline || "Untitled evidence"));
      card.append(element("p", "entity", finding.entity_label || "Entity unresolved"));

      if (finding.evidence_class === "FIXTURE_DEMONSTRATION_NOT_LIVE") {
        card.append(element("p", "fixture-warning", "Fixture demonstration: invented example only. No real source event is represented."));
      }

      const dl = element("dl", "facts");
      addField(dl, "Expected collector identity filter", finding.expected_identity_filter);
      addField(dl, "Requested identity criterion", finding.requested_identity_criterion);
      addField(dl, "Identity match validation", finding.identity_match_verification === "NOT_VALIDATED_BY_PACKET" ? "Not validated by packet" : "Unknown");
      addField(dl, "Identity verification note", finding.identity_verification_note);
      addField(dl, "Identity resolution limit", finding.identity_resolution_limit);
      addField(dl, "Source publication / award date", finding.published_date);
      addField(dl, "Event date", finding.event_date);
      addField(dl, "Collector retrieval time", finding.retrieved_at);
      addField(dl, "Source record ID", finding.source_record_id);
      addField(dl, "Event stage", finding.event_stage);
      addField(dl, "Interpretation limit", finding.interpretation_limit);
      addField(dl, "Licence", finding.license);
      addField(dl, "Attribution", finding.attribution);
      for (const [label, value] of Object.entries(finding.source_facts || {})) {
        if (value !== null && ["string", "number", "boolean"].includes(typeof value)) addField(dl, label, value);
      }
      card.append(dl);

      const links = element("div", "links");
      const sourceHref = safeLink(finding.source_url);
      if (sourceHref) {
        const a = element("a", "button", "Open source ↗");
        a.href = sourceHref;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.referrerPolicy = "no-referrer";
        links.append(a);
      }
      const licenseHref = safeLink(finding.license_url);
      if (licenseHref) {
        const a = element("a", "text-link", "Open licence");
        a.href = licenseHref;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.referrerPolicy = "no-referrer";
        links.append(a);
      }
      card.append(links);

      const review = element("div", "review");
      const disposition = element("label", "", "Local review disposition");
      const select = element("select");
      const choices = [
        ["UNREVIEWED_CONTEXT_ONLY", "Unreviewed context"],
        ["REVIEWED_CONTEXT_ONLY", "Reviewed · context only"],
        ["FOLLOW_UP_SOURCE_CHECK", "Follow up · verify source"],
        ["NOT_RELEVANT_OR_DUPLICATE", "Not relevant / duplicate"]
      ];
      for (const [value, label] of choices) {
        const option = element("option", "", label);
        option.value = value;
        select.append(option);
      }
      select.value = decisions.get(finding.finding_id)?.disposition || "UNREVIEWED_CONTEXT_ONLY";
      select.addEventListener("change", () => {
        const previous = decisions.get(finding.finding_id) || {};
        decisions.set(finding.finding_id, {...previous, disposition: select.value});
      });
      disposition.append(select);
      review.append(disposition);

      const updateDecision = (key, value) => {
        const previous = decisions.get(finding.finding_id) || {};
        decisions.set(finding.finding_id, {...previous, [key]: value});
      };

      const ownerField = element("label", "", "Follow-up owner (local)");
      const ownerInput = element("input");
      ownerInput.type = "text";
      ownerInput.name = "follow-up-owner";
      ownerInput.maxLength = 120;
      ownerInput.autocomplete = "off";
      ownerInput.value = decisions.get(finding.finding_id)?.owner || "";
      ownerInput.addEventListener("input", () => updateDecision("owner", ownerInput.value));
      ownerField.append(ownerInput);
      review.append(ownerField);

      const dateField = element("label", "", "Follow-up date");
      const dateInput = element("input");
      dateInput.type = "date";
      dateInput.name = "follow-up-date";
      dateInput.value = decisions.get(finding.finding_id)?.follow_up_date || "";
      dateInput.addEventListener("change", () => updateDecision("follow_up_date", dateInput.value));
      dateField.append(dateInput);
      review.append(dateField);

      const counterField = element("label", "", "Counter-evidence / unresolved issue");
      const counterInput = element("textarea");
      counterInput.name = "counter-evidence";
      counterInput.rows = 2;
      counterInput.maxLength = 2000;
      counterInput.value = decisions.get(finding.finding_id)?.counter_evidence || "";
      counterInput.placeholder = "Record contrary evidence or what remains unverified.";
      counterInput.addEventListener("input", () => updateDecision("counter_evidence", counterInput.value));
      counterField.append(counterInput);
      review.append(counterField);

      const notes = element("label", "", "Analyst note / next verification step");
      const textarea = element("textarea");
      textarea.name = "analyst-note";
      textarea.rows = 3;
      textarea.maxLength = 2000;
      textarea.value = decisions.get(finding.finding_id)?.note || "";
      textarea.placeholder = "Record source checks and the next concrete step.";
      textarea.addEventListener("input", () => updateDecision("note", textarea.value));
      notes.append(textarea);
      review.append(notes);
      review.append(element("p", "lock-note", "This local disposition cannot qualify, score, save, or publish an expansion lead."));
      card.append(review);
      findingCards.push(card);
    }

    // Build off-screen first; malformed input must not erase the currently loaded review.
    summaries.replaceChildren(...summaryCards);
    findings.replaceChildren(...findingCards);
  }

  $("packet-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const requestGeneration = ++state.importGeneration;
    try {
      if (file.size > 10_000_000) throw new Error("Packet exceeds the 10 MB local import bound.");
      const contents = await file.text();
      if (requestGeneration !== state.importGeneration) return;
      const candidate = validatePacket(JSON.parse(contents));
      const nextDecisions = new Map();
      render(candidate, nextDecisions);
      state.packet = candidate;
      state.decisions = nextDecisions;
      $("export-review").disabled = false;
      $("export-brief").disabled = false;
      setStatus(`Loaded ${candidate.findings.length} findings from local file “${file.name}”. Nothing was uploaded.`);
    } catch (error) {
      if (requestGeneration !== state.importGeneration) return;
      const reason = error.message || "Could not read this packet.";
      setStatus(`Could not load packet; current review was not changed. ${reason}`, true);
    } finally {
      if (requestGeneration === state.importGeneration) event.target.value = "";
    }
  });

  $("load-demo").addEventListener("click", () => {
    state.importGeneration += 1;
    const candidate = validatePacket(DEMO_PACKET);
    const nextDecisions = new Map();
    render(candidate, nextDecisions);
    state.packet = candidate;
    state.decisions = nextDecisions;
    $("export-review").disabled = false;
    $("export-brief").disabled = false;
    setStatus("Loaded a synthetic fixture demonstration. This does not describe a real company or event.");
  });

  $("export-review").addEventListener("click", () => {
    if (!state.packet) return;
    const output = {
      export_type: "LOCAL_ANALYST_REVIEW_NOT_A_LEAD",
      exported_at: new Date().toISOString(),
      lead_promotion_allowed: false,
      independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
      decisions: state.packet.findings.map((finding) => {
        const value = state.decisions.get(finding.finding_id) || {};
        return {
          finding_id: finding.finding_id,
          source: finding.source,
          source_record_id: finding.source_record_id,
          disposition: value.disposition || "UNREVIEWED_CONTEXT_ONLY",
          follow_up_owner: value.owner || "",
          follow_up_date: value.follow_up_date || "",
          counter_evidence: value.counter_evidence || "",
          note: value.note || "",
          lead_eligible: false
        };
      })
    };
    const blob = new Blob([JSON.stringify(output, null, 2) + "\n"], {type: "application/json"});
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "atlanticbridge-local-review-not-a-lead.json";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Exported local review notes. The export cannot create or qualify a lead.");
  });

  $("export-brief").addEventListener("click", () => {
    if (!state.packet) return;
    const blob = new Blob([buildReviewBrief(state.packet, state.decisions)], {
      type: "text/markdown;charset=utf-8"
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "atlanticbridge-analyst-evidence-review.md";
    a.click();
    URL.revokeObjectURL(url);
    setStatus("Downloaded local evidence-backed review brief. It preserves source limits and cannot qualify a lead.");
  });

})();
