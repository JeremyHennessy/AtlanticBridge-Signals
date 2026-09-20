import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { chromium, webkit, devices } from "playwright";

const root = process.cwd();
const dashboardPath = path.join(root, "ui", "data", "dashboard.json");
const dashboard = JSON.parse(fs.readFileSync(dashboardPath, "utf8"));
const baseUrl = process.env.UI_BASE_URL || "http://127.0.0.1:8000";
const artifactsDir = path.join(root, "artifacts", "ui-acceptance");
fs.mkdirSync(artifactsDir, { recursive: true });

const report = {
  verified_commit: process.env.GITHUB_SHA || null,
  expected_case_count: dashboard.cases.length,
  expected_evidence_count: dashboard.cases.reduce((sum, item) => sum + item.evidence.length, 0),
  desktop: {},
  iphone: {},
  checks: [],
  failures: [],
};

function record(name, ok, detail = "") {
  report.checks.push({ name, ok, detail });
  if (!ok) report.failures.push({ name, detail });
  if (!ok) throw new Error(`${name}: ${detail}`);
}

function expectedClassificationCount(value) {
  return dashboard.cases.filter((item) => item.outcome_classification === value).length;
}

function expectedEvidenceFilterCount(value) {
  if (value === "with") return dashboard.cases.filter((item) => item.evidence_count > 0).length;
  if (value === "without") return dashboard.cases.filter((item) => item.evidence_count === 0).length;
  return dashboard.cases.length;
}

async function attachErrorCapture(page, bucket) {
  bucket.consoleErrors = [];
  bucket.pageErrors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") bucket.consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => bucket.pageErrors.push(String(err)));
}

async function waitForCaseRows(page, label) {
  const attempts = [];
  for (let attempt = 1; attempt <= 8; attempt += 1) {
    try {
      await page.locator("#cases-body tr.case-row").first().waitFor({
        state: "visible",
        timeout: 5000,
      });
      return attempts;
    } catch (_) {
      const diagnostic = await page.evaluate(async () => {
        let dashboard = { status: null, ok: false, contentType: null, prefix: null };
        try {
          const response = await fetch("data/dashboard.json", { cache: "no-store" });
          dashboard = {
            status: response.status,
            ok: response.ok,
            contentType: response.headers.get("content-type"),
            prefix: (await response.text()).slice(0, 120),
          };
        } catch (error) {
          dashboard.error = String(error);
        }
        return {
          attempt: null,
          readyState: document.readyState,
          tableText: document.querySelector("#cases-body")?.textContent?.trim().slice(0, 240) || "",
          dashboard,
          scripts: Array.from(document.scripts).map((script) => script.src || "inline"),
        };
      });
      diagnostic.attempt = attempt;
      attempts.push(diagnostic);
      if (attempt < 8) {
        await page.waitForTimeout(5000);
        await page.reload({ waitUntil: "networkidle", timeout: 30000 });
      }
    }
  }
  throw new Error(`${label}: case rows did not become ready: ${JSON.stringify(attempts)}`);
}

async function assertNoPageOverflow(page, label) {
  const result = await page.evaluate(() => ({
    viewport: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  record(
    `${label}: no page-level horizontal overflow`,
    result.documentWidth <= result.viewport + 2 && result.bodyWidth <= result.viewport + 2,
    JSON.stringify(result),
  );
  return result;
}

async function testFilters(page, label) {
  const search = page.locator("#case-search");
  const first = dashboard.cases[0];
  await search.fill(first.canadian_business_name);
  await page.waitForTimeout(100);
  let rows = page.locator("#cases-body tr.case-row");
  const searchCount = await rows.count();
  record(`${label}: search filter`, searchCount >= 1, `rows=${searchCount}`);
  for (let i = 0; i < searchCount; i += 1) {
    const text = (await rows.nth(i).innerText()).toLowerCase();
    record(
      `${label}: search row ${i + 1} matches query`,
      text.includes(first.canadian_business_name.toLowerCase()),
      text.slice(0, 180),
    );
  }
  await search.fill("");

  const classification = page.locator("#classification-filter");
  const classificationValues = await classification.locator("option").evaluateAll((options) =>
    options.map((option) => option.value).filter(Boolean),
  );
  for (const value of classificationValues) {
    await classification.selectOption(value);
    await page.waitForTimeout(50);
    const actual = await page.locator("#cases-body tr.case-row").count();
    const expected = expectedClassificationCount(value);
    record(
      `${label}: classification filter ${value}`,
      actual === expected,
      `expected=${expected} actual=${actual}`,
    );
  }
  await classification.selectOption("");

  const evidence = page.locator("#evidence-filter");
  for (const value of ["with", "without"]) {
    await evidence.selectOption(value);
    await page.waitForTimeout(50);
    const actual = await page.locator("#cases-body tr.case-row").count();
    const expected = expectedEvidenceFilterCount(value);
    record(
      `${label}: evidence filter ${value}`,
      actual === expected,
      `expected=${expected} actual=${actual}`,
    );
  }
  await evidence.selectOption("");
}

async function verifyAllRowsAndDrawers(page, label) {
  const initialRows = await page.locator("#cases-body tr.case-row").count();
  record(
    `${label}: every table row rendered`,
    initialRows === dashboard.cases.length,
    `expected=${dashboard.cases.length} actual=${initialRows}`,
  );

  let drawerScreenshotTaken = false;
  for (const item of dashboard.cases) {
    const row = page.locator(`#cases-body tr.case-row[data-case-id="${item.id}"]`);
    record(`${label}: row exists ${item.id}`, (await row.count()) === 1, item.canadian_business_name);
    await row.click();
    await page.locator("#case-drawer.open").waitFor({ state: "visible", timeout: 5000 });

    const title = (await page.locator("#drawer-title").innerText()).trim();
    record(`${label}: drawer title ${item.id}`, title === item.canadian_business_name, title);

    const timeline = page.locator("#case-drawer .case-timeline");
    record(
      `${label}: timeline rendered ${item.id}`,
      (await timeline.count()) === 1,
      item.canadian_business_name,
    );
    const timelineItems = timeline.locator(".timeline-item");
    record(
      `${label}: timeline contains registry and notification ${item.id}`,
      (await timelineItems.count()) >= 2,
      `items=${await timelineItems.count()}`,
    );

    const cards = page.locator("#case-drawer .evidence-card");
    const cardCount = await cards.count();
    record(
      `${label}: drawer evidence count ${item.id}`,
      cardCount === item.evidence.length,
      `expected=${item.evidence.length} actual=${cardCount}`,
    );

    for (let i = 0; i < item.evidence.length; i += 1) {
      const evidence = item.evidence[i];
      const card = cards.nth(i);
      const badges = card.locator(".publication-chip");
      record(
        `${label}: publication badge ${item.id}#${i + 1}`,
        (await badges.count()) === 1,
        evidence.publication_status,
      );
      const badgeText = (await badges.innerText()).trim();
      record(
        `${label}: publication badge text ${item.id}#${i + 1}`,
        badgeText.length > 0,
        badgeText,
      );

      const links = card.locator("a.source-link");
      const expectedLink = /^https?:\/\//.test(String(evidence.source_url || "")) ? 1 : 0;
      record(
        `${label}: source link render ${item.id}#${i + 1}`,
        (await links.count()) === expectedLink,
        `expected=${expectedLink}`,
      );
      if (expectedLink) {
        const href = await links.getAttribute("href");
        const target = await links.getAttribute("target");
        const rel = await links.getAttribute("rel");
        record(
          `${label}: source link href ${item.id}#${i + 1}`,
          href === evidence.source_url,
          String(href),
        );
        record(
          `${label}: source link target ${item.id}#${i + 1}`,
          target === "_blank" && String(rel || "").includes("noopener"),
          `target=${target} rel=${rel}`,
        );
      }
    }

    if (!drawerScreenshotTaken && item.evidence.length > 0) {
      await page.screenshot({
        path: path.join(artifactsDir, `${label}-drawer.png`),
        fullPage: false,
      });
      drawerScreenshotTaken = true;
    }

    await page.locator("#drawer-close").click();
    await page.waitForFunction(() => {
      const drawer = document.querySelector("#case-drawer");
      return drawer && drawer.getAttribute("aria-hidden") === "true" && !drawer.classList.contains("open");
    }, null, { timeout: 5000 });
  }
}

async function runDesktop() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  await attachErrorCapture(page, report.desktop);
  const response = await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30000 });
  record("desktop: page HTTP success", Boolean(response && response.ok()), `status=${response?.status()}`);
  report.desktop.readinessAttempts = await waitForCaseRows(page, "desktop");

  report.desktop.title = await page.title();
  record("desktop: correct title", report.desktop.title.includes("AtlanticBridge Signals"), report.desktop.title);
  report.desktop.overflow = await assertNoPageOverflow(page, "desktop");

  await page.screenshot({
    path: path.join(artifactsDir, "desktop-overview.png"),
    fullPage: true,
  });

  await testFilters(page, "desktop");
  await verifyAllRowsAndDrawers(page, "desktop");

  record(
    "desktop: no console errors",
    report.desktop.consoleErrors.length === 0,
    report.desktop.consoleErrors.join(" | "),
  );
  record(
    "desktop: no page errors",
    report.desktop.pageErrors.length === 0,
    report.desktop.pageErrors.join(" | "),
  );
  await browser.close();
}

async function runIphone() {
  const iphone = devices["iPhone 15 Pro"] || devices["iPhone 14 Pro"] || {
    viewport: { width: 393, height: 852 },
    userAgent:
      "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1",
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  };
  const browser = await webkit.launch({ headless: true });
  const context = await browser.newContext({ ...iphone });
  const page = await context.newPage();
  await attachErrorCapture(page, report.iphone);
  const response = await page.goto(baseUrl, { waitUntil: "networkidle", timeout: 30000 });
  record("iphone: page HTTP success", Boolean(response && response.ok()), `status=${response?.status()}`);
  report.iphone.readinessAttempts = await waitForCaseRows(page, "iphone");

  report.iphone.viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }));
  report.iphone.overflow = await assertNoPageOverflow(page, "iphone");

  const keyBoxes = await page.evaluate(() => {
    const selectors = [".topbar", ".hero", ".metrics", ".content-grid", ".panel-wide", ".side-panel"];
    return selectors.map((selector) => {
      const node = document.querySelector(selector);
      if (!node) return { selector, missing: true };
      const r = node.getBoundingClientRect();
      return { selector, left: r.left, right: r.right, width: r.width, viewport: innerWidth };
    });
  });
  for (const box of keyBoxes) {
    record(
      `iphone: layout bounds ${box.selector}`,
      !box.missing && box.left >= -2 && box.right <= box.viewport + 2,
      JSON.stringify(box),
    );
  }

  await page.screenshot({
    path: path.join(artifactsDir, "iphone-overview.png"),
    fullPage: true,
  });

  await testFilters(page, "iphone");

  const firstWithEvidence = dashboard.cases.find((item) => item.evidence.length > 0);
  const row = page.locator(`#cases-body tr.case-row[data-case-id="${firstWithEvidence.id}"]`);
  await row.click();
  await page.locator("#case-drawer.open").waitFor({ state: "visible", timeout: 5000 });
  await page.waitForTimeout(250);
  const drawerBox = await page.locator("#case-drawer").boundingBox();
  record(
    "iphone: drawer fits viewport",
    Boolean(drawerBox) && drawerBox.x >= -2 && drawerBox.x + drawerBox.width <= report.iphone.viewport.width + 2,
    JSON.stringify(drawerBox),
  );
  const drawerOverflow = await page.locator("#drawer-content").evaluate((node) => ({
    clientWidth: node.clientWidth,
    scrollWidth: node.scrollWidth,
  }));
  record(
    "iphone: drawer content not horizontally clipped",
    drawerOverflow.scrollWidth <= drawerOverflow.clientWidth + 2,
    JSON.stringify(drawerOverflow),
  );
  await page.screenshot({
    path: path.join(artifactsDir, "iphone-drawer.png"),
    fullPage: false,
  });
  await page.locator("#drawer-close").click();

  record(
    "iphone: no console errors",
    report.iphone.consoleErrors.length === 0,
    report.iphone.consoleErrors.join(" | "),
  );
  record(
    "iphone: no page errors",
    report.iphone.pageErrors.length === 0,
    report.iphone.pageErrors.join(" | "),
  );
  await browser.close();
}

try {
  await runDesktop();
  await runIphone();
  report.passed = report.failures.length === 0;
} catch (error) {
  report.passed = false;
  report.fatal = String(error?.stack || error);
} finally {
  const out = path.join(artifactsDir, "ui-acceptance-report.json");
  fs.writeFileSync(out, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify(report, null, 2));
}

if (!report.passed) process.exit(1);
