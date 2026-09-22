import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { chromium, webkit, devices } from "playwright";

// One acceptance contract for local previews and the exact hosted release.
const root = process.cwd();
const base = process.env.UI_BASE_URL || "http://127.0.0.1:8000";
const dashboard = JSON.parse(fs.readFileSync(path.join(root, "ui/data/dashboard.json"), "utf8"));
const out = path.join(root, "artifacts/ui-acceptance");
fs.mkdirSync(out, { recursive: true });
const report = { verified_commit: process.env.GITHUB_SHA || null, expected_case_count: dashboard.cases.length, expected_evidence_count: dashboard.cases.reduce((n,c)=>n+c.evidence.length,0), checks: [], failures: [] };
const check = (name, condition, detail = "") => { report.checks.push({name,ok:Boolean(condition),detail});assert.ok(condition, `${name}: ${detail}`); };
async function overflow(page, label) {
  const value = await page.evaluate(() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
  check(`${label}: no page-level horizontal overflow`,value.document<=value.viewport+2 && value.body<=value.viewport+2,JSON.stringify(value));
}
async function ready(page) {
  await page.locator('body[data-ui-version="2026-09-22-research-01"]').waitFor();
  await page.waitForFunction(expected => document.querySelector("#metric-cases")?.textContent === String(expected), dashboard.cases.length);
}
async function go(page, route) {
  await page.evaluate(hash => { location.hash = hash; }, route);
  await page.waitForFunction(hash => location.hash === hash, route);
  await page.waitForTimeout(60);
}
async function captureRoute(page, label, route) {
  const {height,dpr} = await page.evaluate(() => ({
    height: document.documentElement.scrollHeight,
    dpr: window.devicePixelRatio || 1,
  }));
  const baseName = path.join(out,`${label}-${route}`);
  if (height * dpr <= 30000) {
    await page.screenshot({path:`${baseName}.png`,fullPage:true});
    return;
  }
  await page.evaluate(() => window.scrollTo(0,0));
  await page.screenshot({path:`${baseName}-top.png`});
  await page.evaluate(() => window.scrollTo(0,document.documentElement.scrollHeight));
  await page.waitForTimeout(60);
  await page.screenshot({path:`${baseName}-bottom.png`});
  await page.evaluate(() => window.scrollTo(0,0));
}
async function exactAssets(page, label) {
  for (const name of ["index.html","app.js","styles.css","data/dashboard.json"]) {
    const actual=await page.evaluate(async name=>{const r=await fetch(new URL(name,location.href),{cache:"no-store"});if(!r.ok)throw new Error(`Asset HTTP ${r.status}: ${name}`);return r.text();},name);
    const expected=fs.readFileSync(path.join(root,"ui",name),"utf8");
    // The existing payload builder changes JSON key order, not audited values.
    // Code must match byte-for-byte; payload contents must match structurally.
    check(`${label}: ${name.endsWith(".json")?"identical audited payload":"exact deployed asset"} ${name}`,name.endsWith(".json")?isDeepStrictEqual(JSON.parse(actual),JSON.parse(expected)):actual===expected);
  }
}
async function allCases(page,label) {
  await go(page,"#companies");
  check(`${label}: all cases rendered`,await page.locator("tr.case-row").count()===dashboard.cases.length);
  for(const item of dashboard.cases) {
    const row=page.locator(`tr.case-row[data-case-id="${item.id}"]`);
    check(`${label}: row ${item.id}`,await row.count()===1);
    await row.click();await page.locator("#case-drawer.open").waitFor();
    check(`${label}: case title ${item.id}`,await page.locator("#drawer-title").innerText()===item.canadian_business_name);
    check(`${label}: timeline ${item.id}`,await page.locator("#case-drawer .case-timeline").count()===1 && await page.locator("#case-drawer .timeline-item").count()>=2);
    check(`${label}: plain-language summary ${item.id}`,await page.locator(".case-summary .summary-block").count()===3);
    const cards=page.locator("#case-drawer .evidence-card");
    check(`${label}: complete evidence ledger ${item.id}`,await cards.count()===item.evidence.length);
    for(let i=0;i<item.evidence.length;i++) {
      const source=item.evidence[i],card=cards.nth(i),link=card.locator("a.source-link");
      check(`${label}: publication badge ${item.id}:${i}`,await card.locator(".publication-chip").count()===1 && (await card.locator(".publication-chip").innerText()).trim().length>0);
      check(`${label}: claim preserved ${item.id}:${i}`,await card.locator(".evidence-claim").innerText()===(source.claim || "No claim text recorded."));
      const valid=/^https?:\/\//.test(String(source.source_url||""));
      check(`${label}: safe source presence ${item.id}:${i}`,await link.count()===(valid?1:0));
      if(valid) {
        check(`${label}: exact source URL ${item.id}:${i}`,await link.getAttribute("href")===new URL(source.source_url).href);
        check(`${label}: safe external target ${item.id}:${i}`,await link.getAttribute("target")==="_blank" && /noopener/.test(await link.getAttribute("rel")) && /noreferrer/.test(await link.getAttribute("rel")));
      }
    }
    check(`${label}: background inert ${item.id}`,await page.locator("#app-shell").evaluate(n=>n.inert));
    const bounds=await page.locator("#drawer-content").evaluate(n=>({width:n.clientWidth,scroll:n.scrollWidth}));
    check(`${label}: drawer not clipped ${item.id}`,bounds.scroll<=bounds.width+2,JSON.stringify(bounds));
    if(item===dashboard.cases[0]) {
      await page.screenshot({path:path.join(out,`${label}-drawer.png`)});
      await page.locator("#drawer-close").focus();await page.keyboard.press("Shift+Tab");
      check(`${label}: focus wraps inside dialog`,await page.evaluate(()=>Boolean(document.activeElement.closest("#case-drawer"))));
    }
    await page.keyboard.press("Escape");await page.locator("#case-drawer.open").waitFor({state:"hidden"});
    check(`${label}: closed dialog inert ${item.id}`,await page.locator("#case-drawer").evaluate(n=>n.inert));
  }
}
async function filters(page,label) {
  await go(page,"#companies");
  const first=dashboard.cases[0];
  await page.locator("#case-search").fill(first.canadian_business_name);
  check(`${label}: search`,await page.locator("tr.case-row").count()>=1);
  await page.locator("#advanced-filters").evaluate(n=>n.open=true);
  await page.locator("#case-search").fill("");
  for(const value of [...new Set(dashboard.cases.map(c=>c.outcome_classification))]) {
    await page.locator("#classification-filter").selectOption(value);
    check(`${label}: finding ${value}`,await page.locator("tr.case-row").count()===dashboard.cases.filter(c=>c.outcome_classification===value).length);
  }
  await page.locator("#classification-filter").selectOption("");
  for(const value of ["with","without"]) {
    await page.locator("#evidence-filter").selectOption(value);
    check(`${label}: coverage ${value}`,await page.locator("tr.case-row").count()===dashboard.cases.filter(c=>value==="with"?c.evidence_count>0:c.evidence_count===0).length);
  }
  await page.locator("#evidence-filter").selectOption("");
  for(const value of [...new Set(dashboard.cases.map(c=>c.ultimate_control_country).filter(Boolean))]) {
    await page.locator("#country-filter").selectOption(value);
    check(`${label}: country ${value}`,await page.locator("tr.case-row").count()===dashboard.cases.filter(c=>c.ultimate_control_country===value).length);
  }
  await page.locator("#reset-filters").click();
  await page.locator('[data-view="early"]').click();
  check(`${label}: earlier evidence filter`,await page.locator("tr.case-row").count()===dashboard.cases.filter(c=>c.verified_pre_notification_evidence_count>0).length);
  await page.locator("#reset-filters").click();
  await page.locator("#case-search").fill("not-a-real-company-xyz");
  check(`${label}: empty state`,await page.locator("tr.case-row").count()===0 && await page.locator("[data-reset]").isVisible());
  await page.locator("[data-reset]").click();
  await page.locator("#sort-order").selectOption("evidence");
  const ids=await page.locator("tr.case-row").evaluateAll(rows=>rows.map(n=>n.dataset.caseId));
  const counts=ids.map(id=>dashboard.cases.find(c=>c.id===id).evidence_count);
  check(`${label}: evidence sort`,counts.every((n,i)=>i===0||counts[i-1]>=n));
  await page.locator("#reset-filters").click();
  await page.locator("#case-search").fill(first.canadian_business_name);
  await page.reload({waitUntil:"networkidle"});await ready(page);
  check(`${label}: filter persists in URL`,await page.locator("#case-search").inputValue()===first.canadian_business_name);
  await page.locator("#reset-filters").click();
}
async function bookmarks(page,label) {
  const id=dashboard.cases[0].id;
  await go(page,"#companies");
  await page.locator(`[data-save="${id}"]`).click();
  await page.reload({waitUntil:"networkidle"});await ready(page);
  await page.locator('[data-view="saved"]').click();
  check(`${label}: local save survives reload`,await page.locator("tr.case-row").count()===1 && await page.locator(`[data-case-id="${id}"]`).count()===1);
  await page.locator(`[data-save="${id}"]`).click();
  check(`${label}: saved empty state`,await page.locator("tr.case-row").count()===0 && (await page.locator(".empty-state").innerText()).includes("No saved cases yet"));
  await go(page,`#companies?case=${id}`);await page.locator("#case-drawer.open").waitFor();
  await page.reload({waitUntil:"networkidle"});await ready(page);await page.locator("#case-drawer.open").waitFor();
  check(`${label}: case deep link survives reload`,await page.locator("#drawer-title").innerText()===dashboard.cases[0].canadian_business_name);
  await page.locator("#drawer-close").click();
  await go(page,"#companies?case=missing");
  check(`${label}: missing case explained`,await page.locator("#route-notice").isVisible());
  await go(page,"#missing-view");check(`${label}: unknown route recovers`,await page.locator("#overview-view").isVisible());
  await go(page,"#companies");
}
async function run(label,type,options) {
  const browser=await type.launch({headless:true});
  try {
    const context=await browser.newContext(options);const page=await context.newPage();const errors=[];
    page.on("pageerror",e=>errors.push(String(e)));page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
    const response=await page.goto(base,{waitUntil:"networkidle",timeout:30000});
    check(`${label}: page HTTP success`,response?.ok());await ready(page);await exactAssets(page,label);
    for(const route of ["overview","companies","research","markets","coverage","guide"]) {
      await go(page,`#${route}`);await page.locator(`#${route}-view`).waitFor();await overflow(page,`${label}/${route}`);
      await captureRoute(page,label,route);
    }
    await go(page,"#research");
    check(`${label}: expanded research cards`,await page.locator("[data-research-id]").count()===dashboard.research_cohort.length);
    check(`${label}: 40-company universe`,await page.locator("#metric-browsable").innerText()===String(dashboard.summary.browsable_company_count));
    const researchText=await page.locator("#research-view").innerText();
    check(`${label}: research role boundary`,researchText.includes("not a current expansion prediction") && researchText.includes("Accepted control") && researchText.includes("Identity-qualified"));
    await go(page,"#markets");
    const marketText=await page.locator("#markets-view").innerText();
    check(`${label}: Canada-wide market scope`,marketText.includes("Nova Scotia-specific evidence remains useful") && marketText.includes("Ontario") && marketText.includes("Québec") && marketText.includes("British Columbia"));
    await filters(page,label);await bookmarks(page,label);await allCases(page,label);
    check(`${label}: no console or page errors`,errors.length===0,errors.join(" | "));
    // Failure tests use a separate context: expected network errors are not mixed with normal acceptance.
    const failed=await browser.newContext(options);const broken=await failed.newPage();
    await broken.route("**/data/dashboard.json",route=>route.fulfill({status:503,body:"Unavailable"}));
    await broken.goto(base);await broken.locator("#retry-load").waitFor();
    check(`${label}: unavailable data is not zero`,await broken.locator("#metric-cases").innerText()==="—" && (await broken.locator("#load-status").innerText()).includes("No results or scores have been inferred"));
    await broken.screenshot({path:path.join(out,`${label}-data-unavailable.png`),fullPage:true});
    await failed.close();await context.close();
  } finally {await browser.close();}
}
try {
  await run("desktop",chromium,{viewport:{width:1440,height:1000}});
  await run("iphone",webkit,devices["iPhone 15 Pro"]);
  await run("narrow-phone",chromium,{viewport:{width:320,height:740},isMobile:true,hasTouch:true});
  report.passed=true;
} catch(error) {report.passed=false;report.failures.push(String(error?.stack||error));}
finally {fs.writeFileSync(path.join(out,"ui-acceptance-report.json"),JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify(report,null,2));}
if(!report.passed)process.exit(1);
