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

test("local analyst review imports context, keeps lead lock, and exports all notes offline", { timeout: 5000 }, async () => {
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

    const longTextWithoutEmail = "ordinary source text ".repeat(5000);
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
        source_license_url: "https://www.data.gouv.fr/pages/legal/licences/etalab-2-0",
        api_query_url: "https://bodacc-datadila.opendatasoft.com/api/explore/v2.0/catalog/datasets/annonces-commerciales/records?where=search%28registre%2C%22123456789%22%29&limit=1",
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
        license_url: id === "1" ? "https://novascotia.ca/opendata/licence.asp" : "https://www.data.gouv.fr/pages/legal/licences/etalab-2-0",
        license: id === "1" ? "Open Government Licence - Nova Scotia" : "Etalab Open Licence 2.0",
        api_query_url: id === "1" ? null : "https://bodacc-datadila.opendatasoft.com/api/explore/v2.0/catalog/datasets/annonces-commerciales/records?where=search%28registre%2C%22123456789%22%29&limit=1",
        attribution: id === "1" ? "Synthetic test envelope" : "Synthetic BODACC test envelope",
        event_stage: id === "1" ? "Awarded tender context" : "French commercial notice context",
        interpretation_limit: id === "1" ? "Tender award is not expansion intent or site selection." : "A French notice does not establish Canadian activity, expansion mandate, or site-selection intent.",
        evidence_class: id === "1" ? "LIVE_QUERY_NOT_INDEPENDENTLY_VERIFIED" : "FIXTURE_DEMONSTRATION_NOT_LIVE",
        independent_verification: "NOT_INDEPENDENTLY_VERIFIED",
        lead_eligible: true,
        lead_promotion_allowed: true,
        source_facts: { "Zero amount": 0, "Goods flag": false, "Untrusted source text": "<script>alert(1)</script>\n# injected heading", "Untrusted URL": "https://evil.example/path_with_underscores", "Prefixed HTTPS autolink": "xhttps://attacker.invalid/path", "Underscore-prefixed HTTPS autolink": "_https://attacker.invalid/path", "Prefixed www autolink": "xwww.attacker.invalid/path", "Underscore-prefixed www autolink": "_www.attacker.invalid/path", "Underscore-prefixed email": "_analyst@attacker.invalid", "Letter-prefixed email": "xanalyst@attacker.invalid", "Single-character TLD email": "analyst@attacker.c", "Unicode TLD email": "analyst@attacker.рф", "Long text without email": id === "1" ? longTextWithoutEmail : "short", "Strikethrough source text": "~~keep literal~~" }
      }))
    };
    elements["packet-file"].files = [{
      name: "synthetic-packet.json",
      size: new TextEncoder().encode(JSON.stringify(packet)).length,
      text: async () => JSON.stringify(packet)
    }];
    await elements["packet-file"].dispatch("change");

    assert.equal(elements["export-review"].disabled, false);
    assert.equal(elements["export-brief"].disabled, false);
    assert.ok(created.some(node => node.tagName === "a" && node.href === "https://www.data.gouv.fr/pages/legal/licences/etalab-2-0"));
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
    const rejectedImportCases = [
      [
        "oversized response hash",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, response_sha256: "f".repeat(600_000)}
            : collection)
        },
        /invalid collection response SHA-256/i
      ],
      [
        "oversized API count",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, coverage_signals: {...collection.coverage_signals, records_returned_by_api: "9".repeat(600_000)}}
            : collection)
        },
        /invalid collection records returned by api count/i
      ],
      [
        "oversized packet row count",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, records_returned: "6".repeat(600_000)}
            : collection)
        },
        /invalid collection records returned count/i
      ],
      [
        "oversized coverage description",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, coverage: "c".repeat(4_097)}
            : collection)
        },
        /oversized collection coverage/i
      ],
      [
        "oversized source licence",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, source_license: "l".repeat(1_025)}
            : collection)
        },
        /oversized collection source_license/i
      ],
      [
        "oversized attribution",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, attribution: "a".repeat(2_049)}
            : collection)
        },
        /oversized collection attribution/i
      ],
      [
        "oversized retrieval timestamp",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, retrieved_at: "t".repeat(65)}
            : collection)
        },
        /oversized collection retrieved_at/i
      ],
      [
        "oversized freshness note",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, coverage_signals: {...collection.coverage_signals, freshness_note: "n".repeat(4_097)}}
            : collection)
        },
        /oversized collection freshness_note/i
      ],
      [
        "oversized update frequency",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, coverage_signals: {...collection.coverage_signals, source_update_frequency: "d".repeat(257)}}
            : collection)
        },
        /oversized collection source_update_frequency/i
      ],
      [
        "invalid collection coverage signals",
        {
          ...packet,
          collections: packet.collections.map((collection, index) => index === 0
            ? {...collection, coverage_signals: []}
            : collection)
        },
        /invalid collection coverage signals/i
      ]
    ];
    for (const [name, rejectedPacket, expectedError] of rejectedImportCases) {
      const serialized = JSON.stringify(rejectedPacket);
      elements["packet-file"].files = [{
        name: name.replaceAll(" ", "-") + ".json",
        size: new TextEncoder().encode(serialized).length,
        text: async () => serialized
      }];
      await elements["packet-file"].dispatch("change");
      assert.match(elements["packet-status"].textContent, expectedError);
      assert.match(elements.findings.textContent, /Invented Example 1/);
      assert.match(elements["collection-summary"].textContent, /Records returned by API2/);
      assert.equal(select.value, "FOLLOW_UP_SOURCE_CHECK");
      assert.equal(ownerInput.value, "Analyst A");
      assert.equal(noteInput.value, "Synthetic source recheck note.");
      assert.equal(elements["export-brief"].disabled, false);
    }


    const oversizedUrlPacket = {
      ...packet,
      findings: packet.findings.map((finding, index) => index === 0
        ? {...finding, source_url: "https://data.novascotia.ca/" + String.fromCharCode(96).repeat(260_000)}
        : finding)
    };
    const oversizedUrlText = JSON.stringify(oversizedUrlPacket);
    elements["packet-file"].files = [{
      name: "oversized-url-packet.json",
      size: new TextEncoder().encode(oversizedUrlText).length,
      text: async () => oversizedUrlText
    }];
    await elements["packet-file"].dispatch("change");
    assert.match(elements["packet-status"].textContent, /invalid or oversized source url/i);
    assert.match(elements.findings.textContent, /Invented Example 1/);
    assert.equal(select.value, "FOLLOW_UP_SOURCE_CHECK");
    assert.equal(ownerInput.value, "Analyst A");
    assert.equal(noteInput.value, "Synthetic source recheck note.");
    assert.equal(elements["export-brief"].disabled, false);
    const oversizedTextPacket = {
      ...packet,
      findings: packet.findings.map((finding, index) => index === 0
        ? {...finding, source_facts: {...finding.source_facts, "Oversized fact": "x".repeat(128_001)}}
        : finding)
    };
    const oversizedText = JSON.stringify(oversizedTextPacket);
    elements["packet-file"].files = [{
      name: "oversized-text-packet.json",
      size: new TextEncoder().encode(oversizedText).length,
      text: async () => oversizedText
    }];
    await elements["packet-file"].dispatch("change");
    assert.match(elements["packet-status"].textContent, /oversized source fact value/i);
    assert.match(elements.findings.textContent, /Invented Example 1/);
    assert.equal(select.value, "FOLLOW_UP_SOURCE_CHECK");
    assert.equal(ownerInput.value, "Analyst A");
    assert.equal(noteInput.value, "Synthetic source recheck note.");
    assert.equal(elements["export-brief"].disabled, false);
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
    const { marked } = await import("marked");
    assert.match(brief, /AtlanticBridge analyst evidence review/);
    assert.match(brief, /Context only — not a qualified lead, investment mandate/);
    assert.match(brief, /Envelope response SHA-256 \(reported, not authenticated\)/);
    assert.match(brief, /Finding origin.*Collector envelope reports live query · not independently verified/);
    assert.match(brief, /Finding origin.*Collector envelope reports fixture · not live/);
    assert.match(brief, /Requested identity criterion/);
    assert.ok(brief.includes("- **Identity verification note:** This packet does not compare the collector's requested identifier or name with this record."));
    assert.ok(brief.includes("- **Identity resolution limit:** A normalized name filter does not establish corporate affiliation."));
    assert.ok(brief.includes("- **Identity resolution limit:** Identifies a French registered entity only; it does not establish a parent, affiliate, or Canadian-entity relationship."));
    assert.match(brief, /Open Government Licence - Nova Scotia/);
    assert.ok(brief.includes("https://www.data.gouv.fr/pages/legal/licences/etalab-2-0"));
    assert.ok(brief.includes("https://bodacc-datadila.opendatasoft.com/api/explore/v2.0/catalog/datasets/annonces-commerciales/records?where=search%28registre%2C%22123456789%22%29&limit=1"));
    assert.ok(brief.includes("https://data.novascotia.ca/resource/m6ps-8j6u.json?observed_field=source_record"));
    assert.ok(brief.includes("https&#58;//evil.example/path\\_with\\_underscores"));
    assert.ok(!brief.includes("https://evil.example"));
    const renderedBrief = marked.parse(brief);
    assert.doesNotMatch(renderedBrief, /<a\b[^>]*href="[^"]*attacker\.invalid/i);
    assert.doesNotMatch(renderedBrief, /<a\b[^>]*href="mailto:/i);
    assert.ok(brief.includes("analyst&#64;attacker.c"));
    assert.ok(brief.includes("analyst&#64;attacker.рф"));
    assert.ok(brief.includes(longTextWithoutEmail));
    assert.ok(renderedBrief.includes(longTextWithoutEmail));
    assert.doesNotMatch(renderedBrief, /<del>/i);
    assert.ok(renderedBrief.includes("~~keep literal~~"));
    assert.ok(renderedBrief.includes("<code>https://data.novascotia.ca/resource/m6ps-8j6u.json?observed_field=source_record</code>"));


    assert.match(brief, /No confirmed site-selection mandate found\./);
    assert.match(brief, /Synthetic source recheck note\./);
    assert.match(brief, /&lt;script&gt;alert\(1\)&lt;\/script&gt; \\# injected heading/);
    assert.equal(elements["packet-status"].textContent, "Downloaded local evidence-backed review brief. It preserves source limits and cannot qualify a lead.");
    const briefLink = created.filter(node => node.tagName === "a").at(-1);
    assert.equal(briefLink.download, "atlanticbridge-analyst-evidence-review.md");


    const oversizedOutputPacket = {
      packet_version: 1,
      workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
      collections: [{ source: "nova_scotia_awarded_public_tenders" }],
      findings: [{
        finding_id: "synthetic-utf8-size-bound",
        source: "nova_scotia_awarded_public_tenders",
        entity_label: "UTF-8 export bound fixture",
        source_facts: {
          "Ampersand field one": "&".repeat(104_000),
          "Ampersand field two": "&".repeat(104_000),
          "Ampersand field three": "&".repeat(104_000),
          "Ampersand field four": "&".repeat(104_000)
        }
      }]
    };
    const oversizedOutputText = JSON.stringify(oversizedOutputPacket);
    elements["packet-file"].files = [{
      name: "utf8-export-bound-packet.json",
      size: new TextEncoder().encode(oversizedOutputText).length,
      text: async () => oversizedOutputText
    }];
    await elements["packet-file"].dispatch("change");
    assert.match(elements["packet-status"].textContent, /Loaded 1 findings/);
    const utf8BoundNote = created.filter(node => node.name === "analyst-note").at(-1);
    utf8BoundNote.value = "Retain this review note when export is refused.";
    await utf8BoundNote.dispatch("input");
    await elements["export-brief"].dispatch("click");
    assert.equal(exportedBlobs.length, 2);
    assert.match(elements["packet-status"].textContent, /exceeds the 2 MB UTF-8 local export bound/i);
    assert.equal(utf8BoundNote.value, "Retain this review note when export is refused.");
    assert.match(elements.findings.textContent, /UTF-8 export bound fixture/);
    assert.equal(elements["export-brief"].disabled, false);

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

test("current Etalab licence is allowed without admitting arbitrary or disguised destinations", async () => {
  const ids = ["packet-file", "load-demo", "export-review", "export-brief", "packet-status", "collection-summary", "findings"];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement("div")]));
  const created = [];
  const modulePath = path.join(__dirname, "../local_analyst_review/app.js");
  global.document = {
    getElementById: id => elements[id],
    createElement: tag => {
      const node = new FakeElement(tag);
      created.push(node);
      return node;
    }
  };
  const official = "https://www.data.gouv.fr/pages/legal/licences/etalab-2-0";
  const api = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.0/catalog/datasets/annonces-commerciales/records?limit=1";
  const candidates = [
    [official, true],
    ["https://www.etalab.gouv.fr/licence-ouverte-open-licence/", true],
    ["https://www.data.gouv.fr/unrelated", false],
    [official + "?redirect=https://evil.example", false],
    [official + "#unverified-fragment", false],
    [official.replace("https:", "http:"), false],
    [official.replace("www.data.gouv.fr", "www.data.gouv.fr.evil.example"), false],
    [official.replace("www.data.gouv.fr", "user@www.data.gouv.fr"), false],
    [official.replace("www.data.gouv.fr", "www.data.gouv.fr:444"), false],
    ["javascript:alert(1)", false],
    [api, true],
    [api.replace("/records?", "/exports?"), false],
    [api.replace("https:", "http:"), false],
    [api.replace("bodacc-datadila.opendatasoft.com", "user@bodacc-datadila.opendatasoft.com"), false],
    [api.replace("bodacc-datadila.opendatasoft.com", "bodacc-datadila.opendatasoft.com:444"), false],
    [api.replace("bodacc-datadila.opendatasoft.com", "bodacc-datadila.opendatasoft.com.evil.example"), false],
    [api + "#unverified", false]
  ];
  try {
    delete require.cache[require.resolve(modulePath)];
    require(modulePath);
    for (const [licenseUrl, expected] of candidates) {
      created.length = 0;
      const packet = {
        packet_version: 1,
        workflow_mode: "LOCAL_ANALYST_REVIEW_ONLY",
        collections: [{ source: "bodacc_commercial_notices" }],
        findings: [{
          finding_id: "synthetic-licence-safety",
          source: "bodacc_commercial_notices",
          license_url: licenseUrl,
          attribution: "Source: bodacc.fr / DILA. Source-file name: unknown; source-file date: unknown."
        }]
      };
      const encoded = JSON.stringify(packet);
      elements["packet-file"].files = [{ name: "licence-safety.json", size: encoded.length, text: async () => encoded }];
      await elements["packet-file"].dispatch("change");
      assert.match(elements["packet-status"].textContent, /Loaded 1 findings/);
      const links = created.filter(node => node.tagName === "a");
      assert.equal(links.length, expected ? 1 : 0, licenseUrl);
      if (expected) assert.equal(links[0].href, licenseUrl);
      assert.match(elements.findings.textContent, /Source-file name: unknown; source-file date: unknown/);
      assert.match(elements.findings.textContent, /CONTEXT ONLY · NOT A LEAD/);
    }
  } finally {
    delete global.document;
    delete require.cache[require.resolve(modulePath)];
  }
});
