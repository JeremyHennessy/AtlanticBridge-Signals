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
  const ids = ["packet-file", "load-demo", "export-review", "export-brief", "packet-status", "collection-summary", "findings"];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement("div")]));
  elements["export-review"].disabled = true;
  elements["export-brief"].disabled = true;
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
  const exportedBlobs = [];
  URL.createObjectURL = blob => { exportedBlobs.push(blob); return "blob:local-review-test"; };
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
      }, {
        source: "bodacc_commercial_notices",
        evidence_class: "FIXTURE_DEMONSTRATION_NOT_LIVE",
        records_returned: 1,
        coverage: "SYNTHETIC_FIXTURE_ONLY",
        source_license: "Etalab Open Licence 2.0",
        attribution: "Synthetic BODACC fixture envelope"
      }],
      findings: ["1", "2"].map(id => ({
        finding_id: "synthetic-" + id,
        source: id === "1" ? "nova_scotia_awarded_public_tenders" : "bodacc_commercial_notices",
        source_record_id: id === "1" ? "SYNTHETIC-1" : "SYNTHETIC-BODACC-2",
        entity_label: "Invented Example " + id,
        expected_identity_filter: id === "1" ? "Expected collector filter: normalized exact vendor name" : "Expected collector filter: exact SIREN query",
        requested_identity_criterion: id === "1" ? "Vendor name: Requested Company Ltd." : "SIREN: 123456789",
        identity_match_verification: "NOT_VALIDATED_BY_PACKET",
        identity_verification_note: "This packet does not compare the collector's requested identifier or name with this record.",
        identity_resolution_limit: id === "1" ? "A normalized name filter does not establish corporate affiliation." : "Identifies a French registered entity only; it does not establish a parent, affiliate, or Canadian-entity relationship.",
        headline: "Synthetic tender " + id,
        source_url: id === "1" ? "https://data.novascotia.ca/resource/m6ps-8j6u.json?observed_field=source_record" : "https://www.bodacc.fr/pages/annonces-commerciales-detail/?q.id=id:SYNTHETIC-BODACC-2",
        license_url: id === "1" ? "https://novascotia.ca/opendata/licence.asp" : "https://www.etalab.gouv.fr/licence-ouverte-open-licence/",
        license: id === "1" ? "Open Government Licence - Nova Scotia" : "Etalab Open Licence 2.0",
        attribution: id === "1" ? "Synthetic test envelope" : "Synthetic BODACC test envelope",
        event_stage: id === "1" ? "Awarded tender context" : "French commercial notice context",
        interpretation_limit: id === "1" ? "Tender award is not expansion intent or site selection." : "A French notice does not establish Canadian activity, expansion mandate, or site-selection intent.",
        evidence_class: id === "1" ? "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED" : "FIXTURE_DEMONSTRATION_NOT_LIVE",
        independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
        lead_eligible: true,
        lead_promotion_allowed: true,
        source_facts: { "Zero amount": 0, "Goods flag": false, "Untrusted source text": "<script>alert(1)</script>\n# injected heading" }
      }))
    };
    elements["packet-file"].files = [{
      name: "synthetic-packet.json",
      size: 1024,
      text: async () => JSON.stringify(packet)
    }];
    await elements["packet-file"].dispatch("change");

    assert.equal(elements["export-review"].disabled, false);
    assert.equal(elements["export-brief"].disabled, false);
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
    assert.ok(exportedBlobs[0]);
    const exported = JSON.parse(await exportedBlobs[0].text());
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
    assert.equal(exported.decisions[1].source_record_id, "SYNTHETIC-BODACC-2");
    assert.equal(exported.decisions[1].disposition, "FOLLOW_UP_SOURCE_CHECK");
    assert.equal(exported.decisions[1].follow_up_owner, "Analyst A");
    assert.equal(exported.decisions[1].follow_up_date, "2026-12-01");
    assert.equal(exported.decisions[1].counter_evidence, "No confirmed site-selection mandate found.");
    assert.equal(exported.decisions[1].note, "Synthetic source recheck note.");
    assert.equal(exported.decisions[1].lead_eligible, false);
    assert.equal(elements["packet-status"].textContent, "Exported local review notes. The export cannot create or qualify a lead.");

    await elements["export-brief"].dispatch("click");
    assert.equal(exportedBlobs.length, 2);
    const brief = await exportedBlobs[1].text();
    assert.match(brief, /AtlanticBridge analyst evidence review/);
    assert.match(brief, /Context only — not a qualified lead, investment mandate/);
    assert.match(brief, /Envelope response SHA-256 \(reported, not authenticated\)/);
    assert.match(brief, /Finding origin.*Collector envelope reports live query · not independently verified/);
    assert.match(brief, /Finding origin.*Collector envelope reports fixture · not live/);
    assert.match(brief, /Requested identity criterion/);
    assert.match(brief, /Identity verification noteThis packet does not compare the collector\'s requested identifier or name with this record\./);
    assert.match(brief, /Identity resolution limitA normalized name filter does not establish corporate affiliation\./);
    assert.match(brief, /Identity resolution limitIdentifies a French registered entity only; it does not establish a parent, affiliate, or Canadian-entity relationship\./);
    assert.match(brief, /Open Government Licence - Nova Scotia/);
    assert.match(brief, /Source URL \\(approved host only\\):\\*\\* `https:\\/\\/data\\.novascotia\\.ca\\/resource\\/m6ps-8j6u\\.json\\?observed_field=source_record`/);
    assert.match(brief, /https&#58;\\/\\/evil\\.example\\/path\\_with\\_underscores/);
    assert.doesNotMatch(brief, /https:\\/\\/evil\\.example/);
    assert.match(brief, /No confirmed site-selection mandate found\./);
    assert.match(brief, /Synthetic source recheck note\./);
    assert.match(brief, /&lt;script&gt;alert\(1\)&lt;\/script&gt; \\# injected heading/);
    assert.equal(elements["packet-status"].textContent, "Downloaded local evidence-backed review brief. It preserves source limits and cannot qualify a lead.");
    const briefLink = created.filter(node => node.tagName === "a").at(-1);
    assert.equal(briefLink.download, "atlanticbridge-analyst-evidence-review.md");

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
