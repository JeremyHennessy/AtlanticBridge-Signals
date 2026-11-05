"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

class FakeElement {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.value = "";
    this.files = [];
    this.disabled = false;
    this.hidden = false;
    this._text = "";
  }

  append(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; this._text = ""; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
  async dispatch(name, event = {}) {
    if (!this.listeners[name]) return undefined;
    return this.listeners[name]({ target: this, ...event });
  }
  click() {
    if (this.listeners.click) return this.listeners.click({ target: this });
    return undefined;
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() {
    return this._text + this.children.map(child => child.textContent || "").join("");
  }
}

test("local analyst review imports context, keeps lead lock, and exports all notes offline", async () => {
  const ids = ["packet-file", "load-demo", "export-review", "packet-status", "collection-summary", "findings"];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement("div")]));
  elements["export-review"].disabled = true;
  const created = [];
  global.document = {
    getElementById: id => elements[id],
    createElement: tag => {
      const node = new FakeElement(tag);
      created.push(node);
      return node;
    }
  };

  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  let exportedBlob;
  URL.createObjectURL = blob => { exportedBlob = blob; return "blob:local-review-test"; };
  URL.revokeObjectURL = () => {};

  try {
    require(path.join(__dirname, "../local_analyst_review/app.js"));

    await elements["load-demo"].dispatch("click");
    assert.match(elements.findings.textContent, /Example Systems Ltd\. \(invented\)/);
    assert.match(elements.findings.textContent, /Fixture demonstration: invented example only/);
    assert.match(elements.findings.textContent, /CONTEXT ONLY · NOT A LEAD/);
    assert.match(elements["packet-status"].textContent, /synthetic fixture demonstration/i);

    const packet = {
      packet_version: 1,
      workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
      lead_promotion_allowed: true,
      independent_verification: "INDEPENDENTLY_VERIFIED",
      collections: [{
        source: "nova_scotia_awarded_public_tenders",
        evidence_class: "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED",
        records_returned: 2,
        coverage: "ONE_EXACT_VENDOR_ONE_PAGE",
        coverage_signals: {
          requested_limit: 2,
          records_returned_by_api: 2,
          records_matching_exact_query: 2,
          records_excluded_by_identity_check: 0,
          total_count_for_query: null,
          api_query_has_more_results: null,
          page_may_be_truncated: true,
          source_update_frequency: null,
          freshness_note: null
        },
        response_sha256: "a".repeat(64),
        source_license: "Open Government Licence - Nova Scotia",
        attribution: "Synthetic test envelope"
      }],
      findings: ["1", "2"].map(id => ({
        finding_id: "synthetic-" + id,
        source: "nova_scotia_awarded_public_tenders",
        source_record_id: "SYNTHETIC-" + id,
        entity_label: "Invented Example " + id,
        expected_identity_filter: "Expected collector filter: normalized exact vendor name",
        requested_identity_criterion: "Vendor name: Requested Company Ltd.",
        identity_match_verification: "NOT_VALIDATED_BY_PACKET",
        identity_verification_note: "This packet does not compare the collector's requested identifier or name with this record.",
        identity_resolution_limit: "A normalized name filter does not establish corporate affiliation.",
        headline: "Synthetic tender " + id,
        source_url: "https://data.novascotia.ca/resource/m6ps-8j6u.json",
        license_url: "https://novascotia.ca/opendata/licence.asp",
        license: "Open Government Licence - Nova Scotia",
        attribution: "Synthetic test envelope",
        event_stage: "Fixture only",
        interpretation_limit: "No real source event",
        evidence_class: "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED",
        independent_verification: "INDEPENDENTLY_VERIFIED",
        lead_eligible: true,
        lead_promotion_allowed: true,
        source_facts: { "Zero amount": 0, "Goods flag": false }
      }))
    };
    elements["packet-file"].files = [{
      name: "synthetic-packet.json",
      size: 1024,
      text: async () => JSON.stringify(packet)
    }];
    await elements["packet-file"].dispatch("change");

    assert.equal(elements["export-review"].disabled, false);
    assert.match(elements.findings.textContent, /Collector envelope reports live query · not independently verified/);
    assert.match(elements.findings.textContent, /Invented Example 1/);
    assert.match(elements.findings.textContent, /Expected collector identity filterExpected collector filter: normalized exact vendor name/);
    assert.match(elements.findings.textContent, /Requested identity criterionVendor name: Requested Company Ltd\./);
    assert.match(elements.findings.textContent, /Identity match validationNot validated by packet/);
    assert.match(elements.findings.textContent, /Identity verification noteThis packet does not compare the collector's requested identifier or name with this record\./);
    assert.match(elements.findings.textContent, /Identity resolution limitA normalized name filter does not establish corporate affiliation\./);
    assert.match(elements["collection-summary"].textContent, /Independent review: not verified/);
    assert.match(elements["collection-summary"].textContent, /Page may be truncatedYes/);
    assert.match(elements["collection-summary"].textContent, /Records returned by API2/);
    assert.match(elements["collection-summary"].textContent, /Envelope response SHA-256 \(reported\)a{64}/);
    assert.match(elements.findings.textContent, /Zero amount0/);
    assert.match(elements.findings.textContent, /Goods flagfalse/);

    const select = created.filter(node => node.tagName === "select").at(-1);
    const ownerInput = created.filter(node => node.name === "follow-up-owner").at(-1);
    const dateInput = created.filter(node => node.name === "follow-up-date").at(-1);
    const counterInput = created.filter(node => node.name === "counter-evidence").at(-1);
    const noteInput = created.filter(node => node.name === "analyst-note").at(-1);
    assert.ok(select);
    assert.ok(ownerInput);
    assert.ok(dateInput);
    assert.ok(counterInput);
    assert.ok(noteInput);
    select.value = "FOLLOW_UP_SOURCE_CHECK";
    await select.dispatch("change");
    ownerInput.value = "Analyst A";
    await ownerInput.dispatch("input");
    dateInput.value = "2026-12-01";
    await dateInput.dispatch("change");
    counterInput.value = "No confirmed site-selection mandate found.";
    await counterInput.dispatch("input");
    noteInput.value = "Synthetic source recheck note.";
    await noteInput.dispatch("input");

    elements["packet-file"].files = [{
      name: "malformed-packet.json",
      size: 64,
      text: async () => JSON.stringify({
        packet_version: 1,
        workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
        collections: [null],
        findings: []
      })
    }];
    await elements["packet-file"].dispatch("change");
    assert.match(elements["packet-status"].textContent, /current review was not changed/i);
    assert.match(elements.findings.textContent, /Invented Example 1/);
    assert.equal(elements["export-review"].disabled, false);

    elements["packet-file"].files = [{
      name: "malicious-source-value.json",
      size: 128,
      text: async () => JSON.stringify({
        packet_version: 1,
        workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
        collections: [{ source: { toString: null, valueOf: null } }],
        findings: []
      })
    }];
    await elements["packet-file"].dispatch("change");
    assert.match(elements["packet-status"].textContent, /unsupported or invalid collection source/i);
    assert.match(elements.findings.textContent, /Invented Example 1/);
    assert.equal(elements["export-review"].disabled, false);

    await elements["export-review"].dispatch("click");
    assert.ok(exportedBlob);
    const exported = JSON.parse(await exportedBlob.text());
    assert.equal(exported.export_type, "LOCAL_ANALYST_REVIEW_NOT_A_LEAD");
    assert.equal(exported.lead_promotion_allowed, false);
    assert.equal(exported.independent_verification, "NOT_INDEPENDENTLY_VERIFIED");
    assert.equal(exported.decisions.length, 2);
    assert.equal(exported.decisions[0].source_record_id, "SYNTHETIC-1");
    assert.equal(exported.decisions[0].disposition, "UNREVIEWED_CONTEXT_ONLY");
    assert.equal(exported.decisions[0].note, "");
    assert.equal(exported.decisions[0].follow_up_owner, "");
    assert.equal(exported.decisions[0].follow_up_date, "");
    assert.equal(exported.decisions[0].counter_evidence, "");
    assert.equal(exported.decisions[0].lead_eligible, false);
    assert.equal(exported.decisions[1].source_record_id, "SYNTHETIC-2");
    assert.equal(exported.decisions[1].disposition, "FOLLOW_UP_SOURCE_CHECK");
    assert.equal(exported.decisions[1].follow_up_owner, "Analyst A");
    assert.equal(exported.decisions[1].follow_up_date, "2026-12-01");
    assert.equal(exported.decisions[1].counter_evidence, "No confirmed site-selection mandate found.");
    assert.equal(exported.decisions[1].note, "Synthetic source recheck note.");
    assert.equal(exported.decisions[1].lead_eligible, false);
    assert.equal(elements["packet-status"].textContent, "Exported local review notes. The export cannot create or qualify a lead.");

    let releaseDelayedRead;
    const delayedRead = new Promise(resolve => { releaseDelayedRead = resolve; });
    elements["packet-file"].files = [{
      name: "slow-older-packet.json",
      size: 128,
      text: () => delayedRead
    }];
    const olderImport = elements["packet-file"].dispatch("change");
    await elements["load-demo"].dispatch("click");
    releaseDelayedRead(JSON.stringify({
      ...packet,
      findings: packet.findings.map(finding => ({...finding, entity_label: "Stale older packet"}))
    }));
    await olderImport;
    assert.match(elements.findings.textContent, /Example Systems Ltd\. \(invented\)/);
    assert.doesNotMatch(elements.findings.textContent, /Stale older packet/);
    assert.match(elements["packet-status"].textContent, /synthetic fixture demonstration/i);
  } finally {
    delete global.document;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
});
