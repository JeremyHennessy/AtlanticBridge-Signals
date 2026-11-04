/* Standalone local evidence review. No network access or persistent storage. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const state = { packet: null, decisions: new Map() };
  const allowedHosts = new Set(["www.bodacc.fr", "open.canada.ca", "data.novascotia.ca"]);

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
    if (value === "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED") return "Live query · not independently verified";
    if (value === "FIXTURE_DEMONSTRATION_NOT_LIVE") return "Fixture demonstration · not live";
    return "Legacy origin unknown";
  }

  function safeLink(value) {
    try {
      const u = new URL(value);
      if (u.protocol === "https:" && allowedHosts.has(u.hostname) && !u.username && !u.password) return u.href;
    } catch (_) {}
    return null;
  }

  function element(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  }

  function addField(parent, label, value) {
    const wrapper = element("div", "field");
    wrapper.append(element("dt", "", label));
    wrapper.append(element("dd", "", value || "Unknown"));
    parent.append(wrapper);
  }

  function validatePacket(input) {
    if (!input || input.packet_version !== 1 || input.workflow_mode !== "LOCAL_ANALYST_REVIEW_ONLY") {
      throw new Error("Unsupported packet format. Build a local analyst review packet first.");
    }
    if (!Array.isArray(input.collections) || !Array.isArray(input.findings)) {
      throw new Error("Packet is missing collection or finding arrays.");
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

  function render(packet) {
    const summaries = $("collection-summary");
    const findings = $("findings");
    summaries.replaceChildren();
    findings.replaceChildren();

    for (const collection of packet.collections) {
      const card = element("article", "collection-card");
      card.append(element("span", "origin", originLabel(collection.evidence_class)));
      card.append(element("h2", "", collection.source || "Unknown source"));
      const dl = element("dl", "compact");
      addField(dl, "Retrieved", collection.retrieved_at || "Unknown");
      addField(dl, "Rows returned", collection.records_returned ?? "Unknown");
      addField(dl, "Coverage", collection.coverage || "Unknown");
      addField(dl, "Licence", collection.source_license || "Unknown");
      card.append(dl);
      card.append(element("p", "attribution", collection.attribution || "Attribution not supplied"));
      card.append(element("p", "warning", "Independent review: not verified"));
      summaries.append(card);
    }

    if (!packet.findings.length) {
      findings.append(element("div", "empty", "No source records were returned in this packet."));
      return;
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
      select.value = state.decisions.get(finding.finding_id)?.disposition || "UNREVIEWED_CONTEXT_ONLY";
      select.addEventListener("change", () => {
        const previous = state.decisions.get(finding.finding_id) || {};
        state.decisions.set(finding.finding_id, {...previous, disposition: select.value});
      });
      disposition.append(select);
      review.append(disposition);

      const notes = element("label", "", "Analyst note / next verification step");
      const textarea = element("textarea");
      textarea.rows = 3;
      textarea.maxLength = 2000;
      textarea.value = state.decisions.get(finding.finding_id)?.note || "";
      textarea.placeholder = "Record source checks, counter-evidence, owner and follow-up date.";
      textarea.addEventListener("input", () => {
        const previous = state.decisions.get(finding.finding_id) || {};
        state.decisions.set(finding.finding_id, {...previous, note: textarea.value});
      });
      notes.append(textarea);
      review.append(notes);
      review.append(element("p", "lock-note", "This local disposition cannot qualify, score, save, or publish an expansion lead."));
      card.append(review);
      findings.append(card);
    }
  }

  $("packet-file").addEventListener("change", async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      if (file.size > 10_000_000) throw new Error("Packet exceeds the 10 MB local import bound.");
      const parsed = JSON.parse(await file.text());
      state.packet = validatePacket(parsed);
      state.decisions.clear();
      render(state.packet);
      $("export-review").disabled = false;
      setStatus(`Loaded ${state.packet.findings.length} findings from local file “${file.name}”. Nothing was uploaded.`);
    } catch (error) {
      setStatus(error.message || "Could not read this packet.", true);
    } finally {
      event.target.value = "";
    }
  });

  $("load-demo").addEventListener("click", () => {
    state.packet = validatePacket(DEMO_PACKET);
    state.decisions.clear();
    render(state.packet);
    $("export-review").disabled = false;
    setStatus("Loaded a synthetic fixture demonstration. This does not describe a real company or event.");
  });

  $("export-review").addEventListener("click", () => {
    if (!state.packet) return;
    const output = {
      export_type: "LOCAL_ANALYST_REVIEW_NOT_A_LEAD",
      exported_at: new Date().toISOString(),
      lead_promotion_allowed: false,
      independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
      decisions: [...state.decisions.entries()].map(([finding_id, value]) => ({
        finding_id,
        disposition: value.disposition || "UNREVIEWED_CONTEXT_ONLY",
        note: value.note || "",
        lead_eligible: false
      }))
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
})();
