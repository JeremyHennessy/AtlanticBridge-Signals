'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createHash, webcrypto } = require('node:crypto');
const api = require('../ui/cordis-research.js');
const raw = fs.readFileSync(path.join(__dirname, '../ui', api.PUBLISHED.path));
const html = fs.readFileSync(path.join(__dirname, '../ui/cordis-research.html'), 'utf8');
const script = fs.readFileSync(path.join(__dirname, '../ui/cordis-research.js'), 'utf8');
const response = (body = raw, init = {}) => new Response(body, { headers: { 'content-type': 'application/json' }, ...init });
const local = (name = 'local.json') => ({ name, size: raw.length, text: async () => raw.toString('utf8'), lastModified: Date.parse('2030-01-01T00:00:00Z') });
const tick = () => new Promise(resolve => setTimeout(resolve, 5));
async function settle(check) { for (let i = 0; i < 100; i++) { if (check()) return; await tick(); } assert.ok(check(), 'asynchronous state did not settle'); }

test('published file is the exact reviewed sanitized derivative, not a regenerated source', () => {
  assert.equal(raw.length, 977669);
  assert.equal(createHash('sha256').update(raw).digest('hex'), 'df7d55e6e3e2603e1b1bd38fc0068752388885357deb8442e95b498385b84825');
  const data = api.parse(raw.toString('utf8'));
  assert.equal(data.as_of_date, '2026-11-09');
  assert.equal(data.source.retrieved_at, '2026-11-09T18:36:59.372836+00:00');
  assert.equal(data.source.file_last_modified, 'Thu, 08 Oct 2026 15:52:57 GMT');
  assert.equal(data.source.catalogue_modified, '2026-10-15');
  assert.equal(data.source.sha256, '5f791fb527da6880322496278099d11661894a9e66d305431788e6ed88349533');
  assert.equal(data.summary.project_count, 244);
  assert.equal(data.summary.eu_prc_participation_rows, 1273);
  assert.equal(data.summary.canada_participation_rows, 294);
  assert.equal(data.summary.eu_prc_source_organisation_ids, 1094);
  assert.equal(data.summary.canada_source_organisation_ids, 128);
  assert.equal(data.summary.qualified_lead_count, 0);
  assert.equal(data.audit.scope_held_projects.length, 6);
  assert.ok(data.projects.every(p => !p.model_eligible && !p.expansion_inferred && p.qualification_status === 'RESEARCH_ONLY_NOT_QUALIFIED'));
});

test('loader makes one credential-free fixed same-origin request and validates checksum before use', async () => {
  const calls = [];
  const payload = await api.readPublished(async (...args) => { calls.push(args); return response(); }, webcrypto);
  assert.equal(payload.projects.length, 244);
  assert.deepEqual(calls, [[api.PUBLISHED.path, { credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer' }]]);
  assert.match(api.PUBLISHED.path, /^data\/cordis-research-2026-11-09\.json$/);
});

test('unavailable, redirected, non-JSON, wrong-size and changed-byte responses fail closed without retry', async () => {
  const changed = Buffer.from(raw); changed[changed.indexOf(Buffer.from('2026-11-09'))] = 0x31;
  const cases = [
    [() => response('denied', { status: 403 }), /request failed/],
    [() => ({ ok: true, redirected: true }), /request failed/],
    [() => response(raw, { headers: { 'content-type': 'text/html' } }), /not JSON/],
    [() => response(raw.subarray(1)), /size/],
    [() => response(Buffer.concat([raw, Buffer.from(' ')])), /size/],
    [() => response(changed), /checksum/],
    [() => { throw new Error('offline'); }, /offline/],
  ];
  for (const [make, error] of cases) {
    let calls = 0;
    await assert.rejects(api.readPublished(async () => { calls++; return make(); }, webcrypto), error);
    assert.equal(calls, 1);
  }
  await assert.rejects(api.readPublished(null, webcrypto), /unavailable/);
  await assert.rejects(api.readPublished(async () => response(), null), /unavailable/);
});

test('oversized streaming body is cancelled immediately and never hashed', async () => {
  let reads = 0, cancels = 0, released = 0, digests = 0;
  const fake = { ok: true, redirected: false, headers: { get: () => 'application/json' }, body: { getReader: () => ({
    read: async () => { reads++; return { done: false, value: new Uint8Array(api.PUBLISHED.bytes + 1) }; },
    cancel: async () => { cancels++; }, releaseLock: () => { released++; }
  }) } };
  await assert.rejects(api.readPublished(async () => fake, { subtle: { digest: () => { digests++; } } }), /size/);
  assert.deepEqual([reads, cancels, released, digests], [1, 1, 1, 0]);
});

test('clear and local choice both defeat a delayed published response', async () => {
  for (const chooseLocal of [false, true]) {
    let resolve; const states = [];
    const loader = api.createFileLoader(state => states.push(state), { fetcher: () => new Promise(r => { resolve = r; }), cryptoApi: webcrypto });
    const pending = loader.loadPublished();
    if (chooseLocal) await loader.load(local()); else loader.clear();
    resolve(response()); await pending;
    assert.equal(states.at(-1).status, chooseLocal ? 'ready' : 'empty');
    if (chooseLocal) assert.equal(states.at(-1).file.name, 'local.json');
    assert.notEqual(states.at(-1).published, true);
  }
});

test('published reload defeats delayed local selection and repeated reload retains the newest request', async () => {
  const states = [], loader = api.createFileLoader(state => states.push(state), { fetcher: async () => response(), cryptoApi: webcrypto });
  let resolve;
  const pending = loader.load({ ...local('late.json'), text: () => new Promise(r => { resolve = r; }) });
  await loader.loadPublished(); resolve(raw.toString('utf8')); await pending;
  assert.equal(states.at(-1).published, true);
  const replies = [], states2 = [], loader2 = api.createFileLoader(state => states2.push(state), { fetcher: () => new Promise(r => replies.push(r)), cryptoApi: webcrypto });
  const first = loader2.loadPublished(), second = loader2.loadPublished();
  replies[1](response()); await second;
  replies[0](response('denied', { status: 403 })); await first;
  assert.equal(states2.at(-1).status, 'ready');
});

test('errors clear previously valid published results instead of reporting zero or retaining stale data', async () => {
  let fail = false; const states = [];
  const loader = api.createFileLoader(state => states.push(state), { fetcher: async () => fail ? response('', { status: 403 }) : response(), cryptoApi: webcrypto });
  await loader.loadPublished(); fail = true; await loader.loadPublished();
  assert.deepEqual(states.map(s => s.status), ['loading', 'ready', 'loading', 'error']);
  assert.equal(states.at(-1).payload, undefined);
});

function dom(fetcher) {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; this.value = ''; this.hidden = false; this._text = ''; }
    set textContent(value) { this._text = String(value); this.children = []; }
    get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this._text = ''; this.children = children; }
    addEventListener(event, listener) { this.listeners[event] = listener; }
    set innerHTML(_) { throw new Error('HTML sink'); }
  }
  const nodes = Object.fromEntries([...html.matchAll(/\bid="([^"]+)"/g)].map(m => [m[1], new Element('section')]));
  const document = { getElementById: id => nodes[id], createElement: tag => new Element(tag) };
  vm.runInNewContext(script, { document, TextEncoder, TextDecoder, fetch: fetcher, crypto: webcrypto });
  return nodes;
}

test('actual published data auto-renders with fixed clocks, separate counts, working search/filter/pagination/reload', async () => {
  let requests = 0; const nodes = dom(async () => { requests++; return response(); });
  await settle(() => !nodes.review.hidden);
  assert.equal(requests, 1); assert.match(nodes['load-status'].textContent, /Published snapshot as of 9 November 2026/);
  assert.match(nodes.summary.textContent, /244Included projects/);
  assert.match(nodes.summary.textContent, /0Qualified leads/);
  assert.match(nodes.clocks.textContent, /2026-11-09T18:36:59.372836\+00:00/);
  assert.match(nodes.clocks.textContent, /08 Oct 2026/);
  assert.match(nodes.clocks.textContent, /Published snapshot file/);
  assert.equal(nodes.projects.children.length, 40);
  assert.equal(nodes['page-status'].textContent, 'Page 1 of 7');
  for (let n = 0; n < 9; n++) nodes['next-page'].listeners.click();
  assert.equal(nodes.projects.children.length, 4); assert.equal(nodes['page-status'].textContent, 'Page 7 of 7');
  nodes.search.value = 'unlikely-test-no-match-zzyy'; nodes.search.listeners.input();
  assert.match(nodes['results-status'].textContent, /0 matching projects/);
  nodes.search.value = ''; nodes.country.value = 'GR'; nodes.country.listeners.change();
  assert.match(nodes['results-status'].textContent, /36 matching projects/);
  nodes['clear-file'].listeners.click(); assert.equal(nodes.review.hidden, true); assert.equal(nodes.projects.children.length, 0);
  nodes['reload-published'].listeners.click(); await settle(() => !nodes.review.hidden);
  assert.equal(requests, 2); assert.equal(nodes.search.value, ''); assert.equal(nodes['page-status'].textContent, 'Page 1 of 7');
});

test('initial published failure shows unavailable counts and local review is visibly distinct', async () => {
  const nodes = dom(async () => response('', { status: 403 }));
  await settle(() => nodes['load-status'].textContent.includes('unavailable:'));
  assert.equal(nodes.review.hidden, true); assert.equal(nodes.summary.children.length, 0);
  assert.match(nodes['load-status'].textContent, /Counts are unavailable, not zero/);
  nodes['research-file'].files = [local()]; nodes['research-file'].listeners.change({ target: nodes['research-file'] });
  await settle(() => !nodes.review.hidden);
  assert.match(nodes['load-status'].textContent, /This is not the published snapshot/);
  assert.match(nodes.clocks.textContent, /2030-01-01/); // Device clock remains separately labelled.
  assert.match(nodes.clocks.textContent, /2026-11-09T18:36:59/);
});

test('research navigation, CSP, safe links and data lane remain independent of app metrics', () => {
  const index = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
  assert.match(index, /href="cordis-research.html">EU–Canada research<\/a>/);
  assert.match(html, /href="index.html#overview"/);
  assert.match(html, /default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'/);
  assert.match(html, /base-uri 'none'; form-action 'none'/);
  assert.match(html, /img-src data:/);
  assert.match(html, /<link rel="icon" href="data:,">/);
  assert.match(html, /meta name="referrer" content="no-referrer"/);
  assert.match(html, /Deployment time does not refresh these source clocks/);
  assert.match(html, /separate from CanadaBuys notices and the review queue/);
  assert.doesNotMatch(script, /live-signals|dashboard\.json|company-reviews|localStorage|sessionStorage|innerHTML|XMLHttpRequest|WebSocket|sendBeacon/);
  assert.doesNotMatch(html, /(?:src|href)="https?:\/\//);
});


test('dedicated hosted checks are invoked by the existing public UI acceptance entrypoint', () => {
  const entry = fs.readFileSync(path.join(__dirname, 'ui_visual_acceptance.mjs'), 'utf8');
  const checks = fs.readFileSync(path.join(__dirname, 'cordis_acceptance.mjs'), 'utf8');
  assert.match(entry, /import \{verifyCordis\} from '\.\/cordis_acceptance\.mjs'/);
  assert.match(entry, /await verifyCordis\(browser,options,base,label,out,check\)/);
  for (const text of ['exact deployed asset', 'acquisition and original file clocks preserved', 'clear hides old counts', 'reload resets filters', 'checksum mismatch', 'no original source or third-party request', 'return preserves unrelated app counts']) assert.ok(checks.includes(text));
  assert.doesNotMatch(checks, /127\.0\.0\.1|localhost|listen\(|source_url.*goto|\.launch\(/);
});


test('primary navigation wraps before the mobile breakpoint without hiding any destination', () => {
  const css = fs.readFileSync(path.join(__dirname, '../ui/styles.css'), 'utf8');
  const baseRule = css.match(/\.primary-nav\{([^}]+)\}/)[1];
  assert.match(baseRule, /display:flex;/);
  assert.match(baseRule, /flex-wrap:wrap;/);
  assert.match(baseRule, /gap:0 30px;/);
  assert.match(css, /\.primary-nav\{gap:0 22px\}/);
  assert.doesNotMatch(baseRule, /overflow|display:none|visibility:hidden/);
  const index = fs.readFileSync(path.join(__dirname, '../ui/index.html'), 'utf8');
  const nav = index.match(/<nav class="primary-nav"[^>]*>([\s\S]*?)<\/nav>/)[1];
  assert.deepEqual([...nav.matchAll(/href="([^"]+)"/g)].map(match => match[1]), ['#overview', '#opportunities', '#signals', '#companies', '#research', 'cordis-research.html', '#markets', '#coverage', '#guide', '#companies?view=saved']);
});
