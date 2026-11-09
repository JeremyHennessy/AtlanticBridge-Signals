const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const api = require('../ui/cordis-research.js');

// Entirely synthetic. This fixture does not assert that any real entity participates.
function fixture() {
  const participant = (canadian) => ({
    source_record_sha256: (canadian ? 'c' : 'b').repeat(64),
    source_organisation_id: canadian ? 'synthetic-ca-id' : 'synthetic-eu-id',
    name: canadian ? 'Synthetic Canadian Institute' : 'Synthetic European Company',
    country: canadian ? 'CA' : 'DE', country_raw: canadian ? 'CA' : 'DE', activity_type_raw: canadian ? 'REC' : 'PRC',
    role_raw: 'participant', end_of_participation_raw: 'false', active_fpa_raw: '',
    source_content_update_raw: '2025-06-12',
  });
  return {
    schema_version: 1, status: 'AVAILABLE', mode: 'RESEARCH_CO_PARTICIPATION_ONLY',
    as_of_date: '2026-11-09', interpretation: 'Research co-participation only. No expansion inference.',
    source: {
      name: 'CORDIS Horizon Europe project and organisation open data', source_url: api.SOURCE_URL,
      catalogue_url: api.CATALOGUE_URL, sha256: 'a'.repeat(64), bytes: 12345,
      retrieved_at: '2026-11-09T12:00:00+00:00', file_last_modified: 'Fri, 06 Nov 2026 12:00:00 GMT',
      catalogue_modified: '2026-11-05', licence_url: api.LICENCE_URL,
      attribution: 'Synthetic test data only, not source-derived research.',
      clock_scope: 'CURRENT_DOWNLOADED_SNAPSHOT_NOT_FIRST_PUBLICATION_OR_FIRST_DISCOVERY',
    },
    scope: { ...api.SCOPE },
    summary: {
      project_count: 1, eu_prc_participation_rows: 1, eu_prc_source_organisation_ids: 1,
      canada_participation_rows: 1, canada_source_organisation_ids: 1, missing_organisation_id_rows: 0,
      unended_partner_projects: 1, project_status_counts: { SIGNED: 1 }, qualified_lead_count: 0,
    },
    audit: {
      archive_project_rows: 1, archive_organisation_rows: 2, valid_project_rows: 1,
      quarantined_project_rows: [], quarantined_canada_projects: [], quarantined_canada_eu_prc_projects: [],
      coverage: 'ALL_ROWS_PARSED', canada_projects: 1, canada_eu_any_activity_projects: 1,
      canada_eu_prc_projects_before_scope: 1, scope_held_projects: [], boundary: 'Civilian use is not verified.',
    },
    projects: [{
      id: 'cordis-project:123456', project_id: '123456', source_url: 'https://cordis.europa.eu/project/id/123456',
      source_record_sha256: 'd'.repeat(64), acronym: 'SYNTHETIC', title: 'Synthetic science project',
      project_status_raw: 'SIGNED', project_start_date_raw: '2025-01-01', project_end_date_raw: '2027-12-31',
      source_content_update_raw: '2026-05-05', project_end_date_is_past: false,
      unended_canada_and_eu_prc_participants_listed: true, eu_prc_participants: [participant(false)],
      canada_participants: [participant(true)], civilian_scope: 'NO_EXPLICIT_MARKER_NOT_VERIFIED',
      qualification_status: 'RESEARCH_ONLY_NOT_QUALIFIED', model_eligible: false, expansion_inferred: false,
    }],
  };
}
function rejects(change, pattern) { const data = fixture(); change(data); assert.throws(() => api.parse(JSON.stringify(data)), pattern); }
function file(data, options = {}) { const raw = JSON.stringify(data); return { size: Buffer.byteLength(raw), name: 'synthetic.json', lastModified: Date.parse('2026-11-08T12:00:00Z'), text: async () => raw, ...options }; }

test('accepts synthetic schema v1 without mutating data or changing clocks', () => {
  const data = fixture(), before = JSON.stringify(data);
  assert.equal(api.validatePayload(data), data);
  assert.equal(JSON.stringify(data), before);
  assert.notEqual(data.source.retrieved_at, data.source.file_last_modified);
  assert.notEqual(data.source.catalogue_modified, data.projects[0].source_content_update_raw);
});
test('requires exact schema, mode, qualifications and interpretation boundaries', () => {
  for (const change of [d => d.schema_version = 2, d => d.mode = 'LIVE', d => d.status = 'FAILED', d => d.projects[0].model_eligible = true, d => d.projects[0].expansion_inferred = true, d => d.projects[0].qualification_status = 'QUALIFIED', d => d.projects[0].civilian_scope = 'VERIFIED', d => d.scope.eu_country_scope = 'EU_OWNED', d => d.source.clock_scope = 'FIRST_PUBLICATION']) rejects(change);
});
test('rejects unknown fields including contacts and objectives at every object layer', () => {
  for (const change of [d => d.contact = 'not permitted', d => d.projects[0].objective = 'not permitted', d => d.projects[0].canada_participants[0].contactForm = 'not permitted', d => d.projects[0].eu_prc_participants[0].vatNumber = 'not permitted', d => d.source.address = 'not permitted', d => d.audit.contacts = [], d => d.summary.contacts = 1, d => delete d.scope.privacy]) rejects(change, /fields/);
});
test('only reviewed JSON source, catalogue and licence are accepted', () => {
  for (const key of ['source_url', 'catalogue_url', 'licence_url']) rejects(d => d.source[key] += '?redirect=elsewhere', /URL/);
  rejects(d => d.source.source_url = 'https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip', /URL/);
});
test('project links are exactly bound to numeric source IDs', () => {
  for (const url of ['javascript:alert(1)', 'https://evil.test/123456', 'https://cordis.europa.eu@evil.test/project/id/123456', 'https://cordis.europa.eu/project/id/123456?x=1', 'https://cordis.europa.eu/project/id/123457', 'https://cordis.europa.eu/project/id/123456/']) rejects(d => d.projects[0].source_url = url, /project URL/);
  rejects(d => d.projects[0].project_id = '<img>', /project ID/);
});
test('invalid or inconsistent summary values fail closed, including misleading zeroes', () => {
  for (const key of ['project_count', 'eu_prc_participation_rows', 'eu_prc_source_organisation_ids', 'canada_participation_rows', 'canada_source_organisation_ids', 'missing_organisation_id_rows', 'unended_partner_projects', 'qualified_lead_count']) rejects(d => d.summary[key] += 1, /summary/);
  rejects(d => d.summary.project_status_counts.SIGNED = 0, /status count/);
  rejects(d => d.summary.project_status_counts.UNKNOWN = 1, /fields/);
});
test('rejects duplicate projects, duplicate participant rows and out-of-scope locations', () => {
  rejects(d => d.projects.push(structuredClone(d.projects[0])), /Duplicate project/);
  rejects(d => d.projects[0].eu_prc_participants.push(structuredClone(d.projects[0].eu_prc_participants[0])), /Duplicate participant/);
  for (const code of ['GB', 'NO', 'CH', 'CA', 'EU', '__proto__']) rejects(d => d.projects[0].eu_prc_participants[0].country = code);
  rejects(d => d.projects[0].eu_prc_participants[0].activity_type_raw = 'HES', /scope/);
  rejects(d => Object.assign(d.projects[0].canada_participants[0], { country: 'US', country_raw: 'US' }), /scope/);
  rejects(d => d.projects[0].canada_participants = [], /lacks/);
});
test('unknown identifier is counted as missing rather than a company', () => {
  const data = fixture(); data.projects[0].eu_prc_participants[0].source_organisation_id = null;
  data.summary.eu_prc_source_organisation_ids = 0; data.summary.missing_organisation_id_rows = 1;
  assert.equal(api.validatePayload(data).summary.missing_organisation_id_rows, 1);
});
test('only the official EL to GR alias is normalized while preserving source country', () => {
  const data = fixture(); Object.assign(data.projects[0].eu_prc_participants[0], { country: 'GR', country_raw: 'EL' });
  const validated = api.validatePayload(data); assert.equal(validated.projects[0].eu_prc_participants[0].country_raw, 'EL');
  assert.equal(api.filterProjects(validated.projects, '', 'GR').length, 1);
  for (const [country, country_raw] of [['GR', 'UK'], ['DE', 'EL'], ['EL', 'EL'], ['DE', 'FR'], ['CA', 'CAN']]) rejects(d => Object.assign(d.projects[0].eu_prc_participants[0], { country, country_raw }));
  rejects(d => delete d.projects[0].eu_prc_participants[0].country_raw, /fields/);
});
test('unchanged source organisations can recur across projects without inflating distinct IDs', () => {
  const data = fixture(), other = structuredClone(data.projects[0]);
  Object.assign(other, { id: 'cordis-project:654321', project_id: '654321', source_url: 'https://cordis.europa.eu/project/id/654321' });
  data.projects.push(other);
  Object.assign(data.summary, { project_count: 2, eu_prc_participation_rows: 2, canada_participation_rows: 2, unended_partner_projects: 2, project_status_counts: { SIGNED: 2 } });
  Object.assign(data.audit, { archive_project_rows: 2, valid_project_rows: 2, archive_organisation_rows: 4, canada_projects: 2, canada_eu_any_activity_projects: 2, canada_eu_prc_projects_before_scope: 2 });
  assert.equal(api.validatePayload(data).summary.eu_prc_source_organisation_ids, 1);
});
test('participation flags, invalid dates and date comparisons never become publication clocks', () => {
  rejects(d => d.as_of_date = '2026-02-30', /as-of/);
  rejects(d => d.source.retrieved_at = '2026-02-30T12:00:00Z', /timestamp/);
  rejects(d => d.source.retrieved_at = '2026-11-09T12:00:00', /timestamp/);
  rejects(d => d.source.retrieved_at = '2026-11-09T24:00:00Z', /timestamp/);
  rejects(d => d.projects[0].project_end_date_is_past = true, /end-date/);
  rejects(d => d.projects[0].unended_canada_and_eu_prc_participants_listed = false, /participation/);
  const data = fixture(); data.projects[0].project_end_date_raw = ''; data.projects[0].project_end_date_is_past = null;
  assert.equal(api.validatePayload(data).projects[0].project_end_date_is_past, null);
});
test('acquisition cannot follow the as-of day, compared after UTC offset normalization', () => {
  for (const timestamp of ['2030-01-01T00:00:00Z', '2026-11-10T00:00:00Z', '2026-11-09T23:30:00-02:00']) rejects(d => d.source.retrieved_at = timestamp, /after the requested as-of/);
  for (const timestamp of ['2026-11-09T23:59:59.999999Z', '2026-11-10T00:30:00+02:00', '2026-11-08T23:30:00-02:00', '2026-11-09T00:30:00+02:00']) {
    const data = fixture(); data.source.retrieved_at = timestamp;
    assert.equal(api.validatePayload(data).source.retrieved_at, timestamp, 'Preserve the supplied timestamp while comparing its UTC date');
  }
  for (const timestamp of ['0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00']) rejects(d => d.source.retrieved_at = timestamp, /timestamp/);
});
test('participant roles and activity codes match the builder vocabulary exactly', () => {
  for (const role of ['participant', 'coordinator', 'associatedPartner', 'thirdParty']) {
    for (const activity of ['PRC', 'HES', 'REC', 'PUB', 'OTH']) {
      const data = fixture(); data.projects[0].canada_participants[0].role_raw = role;
      data.projects[0].canada_participants[0].activity_type_raw = activity;
      data.projects[0].eu_prc_participants[0].role_raw = role;
      assert.equal(api.validatePayload(data), data);
    }
  }
  for (const role of ['', 'Participant', 'associatedpartner', 'lead', 'owner']) rejects(d => d.projects[0].canada_participants[0].role_raw = role, /role/);
  for (const activity of ['', 'prc', 'BUS', 'UNKNOWN', '/PRC']) rejects(d => d.projects[0].canada_participants[0].activity_type_raw = activity, /activity/);
});
test('termination is an exact source boolean string, never an arbitrary status', () => {
  for (const value of ['', 'False', 'TRUE', 'unknown', false, null]) rejects(d => d.projects[0].canada_participants[0].end_of_participation_raw = value, /participation/);
  const data = fixture(); data.projects[0].canada_participants[0].end_of_participation_raw = 'true';
  data.projects[0].unended_canada_and_eu_prc_participants_listed = false; data.summary.unended_partner_projects = 0;
  assert.equal(api.validatePayload(data).summary.unended_partner_projects, 0);
});
test('partial coverage requires explicit quarantine and excludes held records', () => {
  const data = fixture(); data.status = 'PARTIAL';
  Object.assign(data.audit, { archive_project_rows: 2, archive_organisation_rows: 4, canada_projects: 2, canada_eu_any_activity_projects: 2, canada_eu_prc_projects_before_scope: 2, coverage: 'PARTIAL_MALFORMED_PROJECT_ROWS_QUARANTINED', quarantined_canada_projects: ['789'], quarantined_canada_eu_prc_projects: ['789'] });
  data.audit.quarantined_project_rows = [{ project_id: '789', source_record_number: 2, source_record_sha256: 'f'.repeat(64), column_count: 21, reason: 'MALFORMED_PROJECT_ROW_WIDTH' }];
  assert.equal(api.validatePayload(data).projects.length, 1);
  data.audit.quarantined_project_rows[0].project_id = '123456'; assert.throws(() => api.validatePayload(data), /quarantine/);
  rejects(d => d.status = 'PARTIAL', /partial/);
  rejects(d => d.audit.quarantined_canada_projects.push('999'), /subset/);
});
test('scope-held candidate counts reconcile without becoming visible projects', () => {
  const data = fixture(); Object.assign(data.audit, { archive_project_rows: 2, valid_project_rows: 2, canada_projects: 2, canada_eu_any_activity_projects: 2, canada_eu_prc_projects_before_scope: 2, scope_held_projects: [{ project_id: '999', reason: 'AMBIGUOUS_CIVILIAN_SCOPE' }] });
  assert.equal(api.validatePayload(data).projects.length, 1);
  data.audit.scope_held_projects[0].reason = 'QUALIFIED'; assert.throws(() => api.validatePayload(data), /scope-held/);
});
test('well-formed empty derivative is allowed without implying no activity', () => {
  const data = fixture(); data.projects = [];
  for (const key of Object.keys(data.summary)) data.summary[key] = key === 'project_status_counts' ? {} : 0;
  data.audit.canada_projects = 0; data.audit.canada_eu_any_activity_projects = 0; data.audit.canada_eu_prc_projects_before_scope = 0;
  assert.equal(api.validatePayload(data).projects.length, 0);
});
test('search and location filters combine and cover Canadian and EU participant names', () => {
  const projects = fixture().projects;
  assert.equal(api.filterProjects(projects, '  SYNTHETIC  ', 'DE').length, 1);
  assert.equal(api.filterProjects(projects, 'Canadian Institute').length, 1);
  assert.equal(api.filterProjects(projects, 'European Company').length, 1);
  assert.equal(api.filterProjects(projects, '123456').length, 1);
  assert.equal(api.filterProjects(projects, '', 'FR').length, 0);
  assert.equal(api.filterProjects(projects, 'missing').length, 0);
  assert.throws(() => api.filterProjects(projects, '', 'GB'), /filter/);
});
test('bounded pagination clamps repeated next/back and supports empty results', () => {
  const rows = Array.from({ length: 83 }, (_, index) => index);
  assert.deepEqual(api.pageOf(rows, 999), { page: 2, pages: 3, items: [80, 81, 82], start: 81, end: 83 });
  assert.equal(api.pageOf(rows, -50).items.length, api.PAGE_SIZE);
  assert.deepEqual(api.pageOf([], 4), { page: 0, pages: 1, items: [], start: 0, end: 0 });
});
test('local file state clears previous records before validation and rejects errors', async () => {
  const states = [], loader = api.createFileLoader(value => states.push(value));
  await loader.load(file(fixture())); assert.deepEqual(states.map(x => x.status), ['loading', 'ready']);
  assert.equal(states.at(-1).file.modified, '2026-11-08T12:00:00.000Z');
  await loader.load(file({}, { text: async () => '{broken' }));
  assert.deepEqual(states.slice(-2).map(x => x.status), ['loading', 'error']); assert.equal(states.at(-1).payload, undefined);
  loader.clear(); assert.equal(states.at(-1).status, 'empty');
});
test('newer file choice or clear wins over a delayed read; cancelled picker does nothing', async () => {
  const states = [], loader = api.createFileLoader(value => states.push(value)); let resolve;
  const pending = loader.load(file(fixture(), { text: () => new Promise(done => { resolve = done; }) }));
  await loader.load(file(fixture(), { name: 'second.json' }));
  resolve(JSON.stringify(fixture())); await pending; assert.equal(states.at(-1).file.name, 'second.json');
  const length = states.length; await loader.load(undefined); assert.equal(states.length, length);
  const other = loader.load(file(fixture(), { text: () => new Promise(done => { resolve = done; }) }));
  loader.clear(); resolve(JSON.stringify(fixture())); await other; assert.equal(states.at(-1).status, 'empty');
});
test('size limits fail before reading and text byte limits cannot be bypassed by metadata', async () => {
  const states = [], loader = api.createFileLoader(value => states.push(value)); let reads = 0;
  await loader.load(file(fixture(), { size: api.MAX_BYTES + 1, text: async () => { reads++; return '{}'; } }));
  assert.equal(reads, 0); assert.equal(states.at(-1).status, 'error');
  assert.throws(() => api.parse('é'.repeat(api.MAX_BYTES / 2 + 1)), /32 MiB/);
});
test('source strings may contain markup but remain inert text, never HTML or script', () => {
  const data = fixture(); data.projects[0].title = '<img src=x onerror=alert(1)>'; data.projects[0].eu_prc_participants[0].name = '<script>alert(1)</script>';
  assert.equal(api.parse(JSON.stringify(data)).projects[0].title, data.projects[0].title);
  const script = fs.readFileSync(path.join(__dirname, '../ui/cordis-research.js'), 'utf8');
  assert.doesNotMatch(script, /innerHTML|outerHTML|insertAdjacentHTML|document\.write|\beval\s*\(|new Function|\bfetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage/);
  assert.match(script, /element\.textContent = value/);
  const html = fs.readFileSync(path.join(__dirname, '../ui/cordis-research.html'), 'utf8');
  assert.match(html, /connect-src 'none'/); assert.match(html, /No file loaded\. Counts are unavailable, not zero/);
  assert.doesNotMatch(html, /(?:src|href)="https?:\/\//);
});

test('pure DOM stub renders inert text and validated links, then clears a rejected selection', async () => {
  // Deliberately not a browser test. No network, browser, DOM package or server is used.
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; this.hidden = false; this._text = ''; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this._text = ''; this.children = children; }
    addEventListener(event, listener) { this.listeners[event] = listener; }
    set innerHTML(_) { throw new Error('HTML injection sink used'); }
  }
  const html = fs.readFileSync(path.join(__dirname, '../ui/cordis-research.html'), 'utf8');
  const nodes = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(match => [match[1], new Element('section')]));
  const document = { getElementById: id => nodes[id], createElement: tag => new Element(tag) };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../ui/cordis-research.js'), 'utf8'), { document, TextEncoder });
  const data = fixture(), markup = '<img src=x onerror=alert(1)>'; data.projects[0].title = markup;
  nodes['research-file'].files = [file(data)];
  nodes['research-file'].listeners.change({ target: nodes['research-file'] });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(nodes.review.hidden, false); assert.match(nodes.projects.textContent, /<img src=x onerror=alert\(1\)>/);
  const descendants = element => [element, ...element.children.flatMap(descendants)];
  const rendered = descendants(nodes.projects), links = rendered.filter(element => element.tag === 'a');
  assert.equal(rendered.some(element => ['img', 'script', 'iframe'].includes(element.tag)), false);
  assert.equal(links.length, 1); assert.equal(links[0].href, data.projects[0].source_url); assert.equal(links[0].rel, 'noopener noreferrer');
  assert.match(nodes.clocks.textContent, /Acquisition retrieved at/); assert.match(nodes.clocks.textContent, /Local file modified \(device metadata\)/);
  nodes['research-file'].files = [file({})]; nodes['research-file'].listeners.change({ target: nodes['research-file'] });
  assert.equal(nodes.review.hidden, true); assert.equal(nodes.projects.children.length, 0);
  await new Promise(resolve => setImmediate(resolve));
  assert.match(nodes['load-status'].textContent, /File rejected/); assert.equal(nodes.review.hidden, true);
});

module.exports = { fixture };
