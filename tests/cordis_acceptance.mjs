import fs from 'node:fs';
import path from 'node:path';

// Public static assets only. Source links are inspected, never followed.
export async function verifyCordis(browser, options, base, label, out, check) {
  const expectedRaw = fs.readFileSync(path.join(process.cwd(), 'ui/data/cordis-research-2026-11-09.json'), 'utf8');
  const expected = JSON.parse(expectedRaw);
  const context = await browser.newContext(options);
  const page = await context.newPage(), errors = [], requests = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('request', request => requests.push(request.url()));
  let pageUrl;
  try {
    await page.goto(base, { waitUntil: 'networkidle' });
    await page.waitForFunction(() => /^\d+$/.test(document.querySelector('#metric-cases')?.textContent || ''));
    const before = await page.locator('#metric-live-signals, #metric-evidence, #metric-cases').allTextContents();
    const link = page.locator('.primary-nav a[href="cordis-research.html"]');
    check(`${label}/CORDIS: main navigation exposes separate research lane`, await link.count() === 1);
    await link.click();
    await page.locator('#review').waitFor({ state: 'visible' });
    pageUrl = page.url();
    check(`${label}/CORDIS: exact research route`, new URL(pageUrl).pathname.endsWith('/cordis-research.html'));
    check(`${label}/CORDIS: fixed snapshot label`, (await page.locator('#load-status').innerText()).includes('Published snapshot as of 9 November 2026'));
    check(`${label}/CORDIS: reviewed counts with zero qualified leads`, JSON.stringify((await page.locator('#summary .metric strong').allTextContents()).map(text => Number(text.replace(/[^0-9]/g, '')))) === JSON.stringify([244, 1273, 294, 1094, 128, 0]));
    const clocks = await page.locator('#clocks').innerText();
    check(`${label}/CORDIS: acquisition and original file clocks preserved`, clocks.includes(expected.source.retrieved_at) && clocks.includes(expected.source.file_last_modified) && clocks.includes(expected.as_of_date));
    check(`${label}/CORDIS: research and ownership boundaries visible`, (await page.locator('.notice').first().innerText()).includes('No records are eligible for scoring') && (await page.locator('.notice').first().innerText()).includes('not ultimate ownership'));
    check(`${label}/CORDIS: restrictive static CSP`, (await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content')).includes("connect-src 'self'") && (await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content')).includes("base-uri 'none'"));
    for (const name of ['cordis-research.html', 'cordis-research.js', 'cordis-research.css', 'data/cordis-research-2026-11-09.json']) {
      const actual = await page.evaluate(async name => { const r = await fetch(new URL(name, location.href), { credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer' }); if (!r.ok) throw new Error('CORDIS asset unavailable: ' + name); return r.text(); }, name);
      check(`${label}/CORDIS: exact deployed asset ${name}`, actual === fs.readFileSync(path.join(process.cwd(), 'ui', name), 'utf8'));
    }
    check(`${label}/CORDIS: first page bounded`, await page.locator('#projects .project').count() === 40 && await page.locator('#previous-page').isDisabled());
    await page.locator('#projects .project details').first().locator('summary').click();
    check(`${label}/CORDIS: participant details open`, await page.locator('#projects .project details[open]').count() === 1);
    const links = await page.locator('#projects .project > a').evaluateAll(nodes => nodes.map(n => ({ href: n.href, target: n.target, rel: n.rel })));
    check(`${label}/CORDIS: safe official project links without opening sources`, links.length === 40 && links.every(link => /^https:\/\/cordis\.europa\.eu\/project\/id\/\d+$/.test(link.href) && link.target === '_blank' && link.rel.includes('noopener') && link.rel.includes('noreferrer')));
    const overflow = await page.evaluate(() => ({ viewport: innerWidth, width: document.documentElement.scrollWidth }));
    check(`${label}/CORDIS: no horizontal overflow with details`, overflow.width <= overflow.viewport + 2, JSON.stringify(overflow));
    await page.screenshot({ path: path.join(out, `${label}-cordis-research.png`) });
    for (let i = 0; i < 6; i++) await page.locator('#next-page').click();
    check(`${label}/CORDIS: final page and disabled next`, await page.locator('#projects .project').count() === 4 && await page.locator('#next-page').isDisabled());
    await page.locator('#country').selectOption('GR');
    check(`${label}/CORDIS: Greek raw aliases remain searchable`, (await page.locator('#results-status').innerText()).includes(' of 36 matching projects '));
    await page.locator('#country').selectOption('');
    await page.locator('#search').fill(expected.projects[0].project_id);
    check(`${label}/CORDIS: source ID search`, (await page.locator('#results-status').innerText()).includes(' of 1 matching projects '));
    await page.locator('#search').fill('unlikely-test-no-match-zzyy');
    check(`${label}/CORDIS: empty search is not absent source evidence`, (await page.locator('#results-status').innerText()).includes(' of 0 matching projects '));
    await page.locator('#clear-file').click();
    check(`${label}/CORDIS: clear hides old counts`, await page.locator('#review').isHidden() && await page.locator('#summary .metric').count() === 0 && (await page.locator('#load-status').innerText()).includes('Counts are unavailable, not zero'));
    await page.locator('#reload-published').click();
    await page.locator('#review').waitFor({ state: 'visible' });
    check(`${label}/CORDIS: reload resets filters and pagination`, await page.locator('#search').inputValue() === '' && await page.locator('#country').inputValue() === '' && (await page.locator('#page-status').innerText()) === 'Page 1 of 7');
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#review').waitFor({ state: 'visible' });
    check(`${label}/CORDIS: direct page reload retains fixed provenance`, (await page.locator('#clocks').innerText()).includes(expected.source.retrieved_at));
    await page.locator('nav a[href="index.html#overview"]').click();
    await page.waitForFunction(() => /^\d+$/.test(document.querySelector('#metric-cases')?.textContent || ''));
    check(`${label}/CORDIS: return preserves unrelated app counts`, JSON.stringify(await page.locator('#metric-live-signals, #metric-evidence, #metric-cases').allTextContents()) === JSON.stringify(before));
    check(`${label}/CORDIS: no original source or third-party request`, requests.every(url => new URL(url).origin === new URL(base).origin));
    check(`${label}/CORDIS: no normal page or console errors`, errors.length === 0, errors.join(' | '));
  } finally { await context.close(); }

  // Intercept only the public same-origin JSON asset, without retrying any source.
  for (const [name, status, body] of [['unavailable', 503, 'Unavailable'], ['checksum mismatch', 200, expectedRaw.replace('2026-11-09', '2025-11-09')]]) {
    const failed = await browser.newContext(options);
    try {
      const broken = await failed.newPage();
      await broken.route('**/data/cordis-research-2026-11-09.json', route => route.fulfill({ status, contentType: 'application/json', body }));
      await broken.goto(pageUrl, { waitUntil: 'networkidle' });
      await broken.waitForFunction(() => document.querySelector('#load-status')?.textContent.includes('Published snapshot unavailable:'));
      check(`${label}/CORDIS: ${name} does not become zero`, await broken.locator('#review').isHidden() && await broken.locator('#summary .metric').count() === 0 && (await broken.locator('#load-status').innerText()).includes('Counts are unavailable, not zero'));
    } finally { await failed.close(); }
  }
}
