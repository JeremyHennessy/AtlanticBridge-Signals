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
        coverage: "SYNTHETIC_FIXTURE_ONLY",
        source_license: "Open Government Licence - Nova Scotia",
        attribution: "Synthetic test envelope"
      }],
      findings: ["1", "2"].map(id => ({
        finding_id: "synthetic-" + id,
        source: "nova_scotia_awarded_public_tenders",
        source_record_id: "SYNTHETIC-" + id,
        entity_label: "Invented Example " + id,
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
    assert.match(elements["collection-summary"].textContent, /Independent review: not verified/);
    assert.match(elements.findings.textContent, /Zero amount0/);
    assert.match(elements.findings.textContent, /Goods flagfalse/);

    const select = created.filter(node => node.tagName === "select").at(-1);
    const textarea = created.filter(node => node.tagName === "textarea").at(-1);
    assert.ok(select);
    assert.ok(textarea);
    select.value = "FOLLOW_UP_SOURCE_CHECK";
    await select.dispatch("change");
    textarea.value = "Synthetic source recheck note.";
    await textarea.dispatch("input");

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
    assert.equal(exported.decisions[0].lead_eligible, false);
    assert.equal(exported.decisions[1].source_record_id, "SYNTHETIC-2");
    assert.equal(exported.decisions[1].disposition, "FOLLOW_UP_SOURCE_CHECK");
    assert.equal(exported.decisions[1].note, "Synthetic source recheck note.");
    assert.equal(exported.decisions[1].lead_eligible, false);
    assert.equal(elements["packet-status"].textContent, "Exported local review notes. The export cannot create or qualify a lead.");
  } finally {
    delete global.document;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
  }
});
