import {verifyCaseBriefs} from './case_briefs_acceptance.mjs';
import {verifyMonitorReview} from './monitor_review_acceptance.mjs';
import assert from "node:assert/strict";
import {verifyOpportunities,verifyOpportunityPaths} from "./opportunities_acceptance.mjs";
import {verifyReviewed} from "./reviewed_acceptance.mjs";
import {verifyLiveDossiers,verifyWorkspace} from "./workspace_acceptance.mjs";
import fs from "node:fs";
import path from "node:path";
import { isDeepStrictEqual } from "node:util";
import { chromium, webkit, devices } from "playwright";

// One acceptance contract for local previews and the exact hosted release.
const root = process.cwd();
const base = process.env.UI_BASE_URL || "http://127.0.0.1:8000";
const dashboard = JSON.parse(fs.readFileSync(path.join(root, "ui/data/dashboard.json"), "utf8"));
const checkedLive = JSON.parse(fs.readFileSync(path.join(root, "ui/data/live-signals.json"), "utf8"));
const requireLive = process.env.REQUIRE_LIVE_SIGNALS === "1";
const out = path.join(root, "artifacts/ui-acceptance");
fs.mkdirSync(out, { recursive: true });
const report = { verified_commit: process.env.GITHUB_SHA || null, expected_case_count: dashboard.cases.length, expected_evidence_count: dashboard.cases.reduce((n,c)=>n+c.evidence.length,0), checks: [], failures: [] };
const check = (name, condition, detail = "") => { report.checks.push({name,ok:Boolean(condition),detail});assert.ok(condition, `${name}: ${detail}`); };
async function overflow(page, label) {
  const value = await page.evaluate(() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth}));
  check(`${label}: no page-level horizontal overflow`,value.document<=value.viewport+2 && value.body<=value.viewport+2,JSON.stringify(value));
}
async function ready(page) {
  await page.locator('body[data-ui-version="2026-09-22-workbench-01"]').waitFor();
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
function validateLivePayload(payload,label) {
  check(`${label}: live payload schema`,payload?.schema_version===1 && ["ACTIVE","UNAVAILABLE"].includes(payload?.status) && Array.isArray(payload?.signals) && payload?.summary);
  if(payload.status==="ACTIVE"){
    check(`${label}: live signal count contract`,payload.summary.signal_count===payload.signals.length);
    check(`${label}: live signal IDs unique`,new Set(payload.signals.map(x=>x.id)).size===payload.signals.length);
    check(`${label}: live company count contract`,payload.summary.company_count===new Set(payload.signals.map(x=>x.company_id)).size);
    check(`${label}: live CanadaBuys semantics`,payload.signals.every(x=>x.signal_family==="CANADABUYS_AWARD" && x.source_confidence==="SOURCE_CONFIRMED" && x.company_id && x.company_name && x.publicly_available_date && x.source_url));
  } else {
    check(`${label}: unavailable live feed explains itself`,typeof payload.reason==="string" && payload.reason.length>0);
  }
  if(requireLive)check(`${label}: hosted release requires active live feed`,payload.status==="ACTIVE" && payload.summary.signal_count>0 && payload.summary.company_count>0);
  return payload;
}
async function fetchLivePayload(page,label) {
  const payload=await page.evaluate(async()=>{const r=await fetch(new URL("data/live-signals.json",location.href),{cache:"no-store"});if(!r.ok)throw new Error(`Live payload HTTP ${r.status}`);return r.json();});
  return validateLivePayload(payload,label);
}
async function exactAssets(page, label) {
  for (const name of ["index.html","app.js","styles.css","workspace.js","workbench.js","workspace.css","reviewed.js","opportunities.js","monitor-review.js","case-briefs.js","data/case-briefs.json","data/company-reviews.json","data/reviewed-evidence.json","data/dashboard.json"]) {
    const actual=await page.evaluate(async name=>{const r=await fetch(new URL(name,location.href),{cache:"no-store"});if(!r.ok)throw new Error(`Asset HTTP ${r.status}: ${name}`);return r.text();},name);
    const expected=fs.readFileSync(path.join(root,"ui",name),"utf8");
    check(`${label}: ${name.endsWith(".json")?"identical audited payload":"exact deployed asset"} ${name}`,name.endsWith(".json")?isDeepStrictEqual(JSON.parse(actual),JSON.parse(expected)):actual===expected);
  }
  const live=await fetchLivePayload(page,label);
  if(!requireLive && checkedLive.status==="ACTIVE" && live.status==="ACTIVE"){
    check(`${label}: checked and served live source family agree`,checkedLive.source?.family===live.source?.family);
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
  check(`${label}: saved empty state`,await page.locator("tr.case-row").count()===0 && (await page.locator("#companies-view .empty-state").innerText()).includes("No saved cases yet"));
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
    for(const route of ["overview","signals","companies","research","markets","coverage","guide"]) {
      await go(page,`#${route}`);await page.locator(`#${route}-view`).waitFor();await overflow(page,`${label}/${route}`);
      await captureRoute(page,label,route);
    }
    await go(page,"#signals");
    const live=await fetchLivePayload(page,`${label}/signals`);
    if(live.status==="ACTIVE"){
      const allAvailable=live.signals;
      const expected90=allAvailable.filter(x=>{const age=Math.floor((Date.parse(new Date().toISOString().slice(0,10))-Date.parse(x.publicly_available_date))/86400000);return age>=0 && age<=90;});
      check(`${label}: default signal row count`,await page.locator("[data-live-signal-id]").count()===expected90.length);
      check(`${label}: signal feed boundary`,(await page.locator("#signals-view").innerText()).includes("not establish first entry") && !(await page.locator("#signals-view").innerText()).toLowerCase().includes("probability score"));
      await page.locator("#signal-window").selectOption("all");
      await page.waitForFunction(expected=>document.querySelectorAll("[data-live-signal-id]").length===expected,allAvailable.length);
      if(allAvailable.length){
        const first=allAvailable[0];
        await page.locator("#signal-search").fill(first.company_name);
        await page.waitForFunction(()=>document.querySelectorAll("[data-live-signal-id]").length>0);
        check(`${label}: signal company search`,(await page.locator("[data-live-signal-id]").first().innerText()).includes(first.company_name));
        await page.locator("#signal-reset").click();
        await page.locator("#signal-window").selectOption("all");
        const watchedCompany=await page.locator("[data-watch-company]").first().getAttribute("data-watch-company");
        await page.locator("[data-watch-company]").first().click();
        // Storage commits may await a cross-tab Web Lock; assert the result, not click timing.
        await page.waitForFunction(id=>document.querySelector(`[data-watch-company="${id}"]`)?.getAttribute("aria-pressed")==="true",watchedCompany);
        check(`${label}: company watch saved`,await page.evaluate(id=>JSON.parse(localStorage.getItem("atlanticbridge.analyst-workspace.v1")).entries.some(e=>e.id===id),watchedCompany));
        await page.reload({waitUntil:"networkidle"});await ready(page);
        check(`${label}: actual source watch survives reload`,await page.locator(`[data-watch-company="${watchedCompany}"]`).first().getAttribute("aria-pressed")==="true");
        await page.locator('[data-signal-view="watched"]').click();
        check(`${label}: watched signal view`,await page.locator("[data-live-signal-id]").count()>0);
        check(`${label}: official live source link`,await page.locator(".live-signal-item .source-link").first().isVisible());
        await page.locator("[data-watch-company]").first().click();
        await page.waitForFunction(id=>!JSON.parse(localStorage.getItem("atlanticbridge.analyst-workspace.v1")).entries.some(e=>e.id===id),watchedCompany);
        await page.locator("#signal-reset").click();
      }
    } else {
      check(`${label}: unavailable live feed is explicit`,(await page.locator("#signal-count-label").innerText()).includes("unavailable—not zero"));
    }
    await go(page,"#overview");
    check(`${label}: overview research count`,await page.locator("#metric-evidence").innerText()===String(dashboard.summary.research_cohort_count));
    const presentCount=dashboard.research_cohort.filter(x=>(x.signal_analysis||[]).some(s=>s.signal_family==="CIPO_CANADIAN_TRADEMARK" && s.state==="PRESENT")).length;
    const overviewText=await page.locator("#overview-view").innerText();
    check(`${label}: overview live/research boundary`,overviewText.includes("live evidence inbox") && overviewText.includes("Historical cases and research controls remain separate context."));
    await go(page,"#research");
    check(`${label}: research CIPO signal count`,await page.locator("#research-cipo-present-count").innerText()===String(presentCount));
    check(`${label}: expanded research rows`,await page.locator("[data-research-id]").count()===dashboard.research_cohort.length);
    check(`${label}: 40-company universe arithmetic`,dashboard.summary.browsable_company_count===dashboard.summary.case_count+dashboard.summary.research_cohort_count);
    check(`${label}: research result count`,await page.locator("#research-result-count").innerText()===`${dashboard.research_cohort.length} of ${dashboard.research_cohort.length} companies`);
    const researchText=await page.locator("#research-view").innerText();
    check(`${label}: research role boundary`,(await page.locator(".research-page-heading").innerText()).includes("not current prospects") && await page.locator("#research-accepted-count").innerText()==="4" && await page.locator("#research-qualified-count").innerText()==="9");
    check(`${label}: research signal pills`,await page.locator(".research-signal-pill").count()===dashboard.research_cohort.length*3);
    check(`${label}: research signal boundaries`,researchText.includes("Present") && researchText.includes("Proven absent") && researchText.includes("Unknown"));
    await page.locator("#research-cipo-filter").selectOption("PRESENT");
    await page.waitForFunction(()=>document.querySelectorAll("[data-research-id]").length===1);
    check(`${label}: CIPO present filter`,(await page.locator("[data-research-id]").innerText()).includes("Andriani"));
    check(`${label}: research filter URL`,page.url().includes("cipo=PRESENT"));
    await page.locator("#research-reset").click();
    await page.waitForFunction(expected=>document.querySelectorAll("[data-research-id]").length===expected,dashboard.research_cohort.length);
    await page.locator("#research-role-filter").selectOption("ACCEPTED_BACKTEST_CONTROL");
    await page.waitForFunction(()=>document.querySelectorAll("[data-research-id]").length===4);
    check(`${label}: accepted control filter`,await page.locator("[data-research-id]").count()===4);
    await page.locator("#research-reset").click();
    await page.locator("#research-search").fill("Andriani");
    await page.waitForFunction(()=>document.querySelectorAll("[data-research-id]").length===1);
    check(`${label}: research search`,(await page.locator("[data-research-id]").innerText()).includes("Andriani"));
    await page.locator(".research-detail summary").click();
    check(`${label}: research details expand`,await page.locator(".research-detail[open] .research-detail-body").isVisible());
    check(`${label}: primary research source link`,await page.locator(".research-detail[open] .source-link").count()>0);
    await page.locator("#research-reset").click();
    await go(page,"#companies");
    const mobileCompanyScanExpected = label === "iphone" || label === "narrow-phone";
    check(`${label}: mobile company scan visibility`,(await page.locator(".mobile-case-scan").first().isVisible())===mobileCompanyScanExpected);
    check(`${label}: company activity detail visibility`,(await page.locator(".company-meta").first().isVisible())!==mobileCompanyScanExpected);
    if (mobileCompanyScanExpected) {
      check(`${label}: compact scan rows complete`,await page.locator(".mobile-case-scan").count()===dashboard.cases.length);
      const firstHeight=await page.locator(".case-row").first().evaluate(node=>node.getBoundingClientRect().height);
      check(`${label}: compact first case row`,firstHeight < 125,`height=${firstHeight}`);
    }
    await go(page,"#markets");
    const marketText=await page.locator("#markets-view").innerText();
    check(`${label}: Canada-wide market scope`,marketText.includes("Nova Scotia-specific evidence remains useful") && marketText.includes("Ontario") && marketText.includes("Québec") && marketText.includes("British Columbia"));
    await filters(page,label);await bookmarks(page,label);await allCases(page,label);
    await verifyLiveDossiers(page,live,label,out,check);
    await verifyWorkspace(browser,options,base,label,out,check);
    await verifyReviewed(browser,options,base,label,out,check);
    await verifyOpportunities(browser,options,base,label,out,check);
    await verifyOpportunityPaths(browser,options,base,label,out,check);
    await verifyMonitorReview(browser,options,base,label,out,check);
    await verifyCaseBriefs(browser,options,base,label,out,check);
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
  await run("tablet",chromium,{viewport:{width:768,height:900},hasTouch:true});
  await run("iphone",webkit,devices["iPhone 15 Pro"]);
  await run("narrow-phone",chromium,{viewport:{width:320,height:740},isMobile:true,hasTouch:true});
  report.passed=true;
} catch(error) {report.passed=false;report.failures.push(String(error?.stack||error));}
finally {fs.writeFileSync(path.join(out,"ui-acceptance-report.json"),JSON.stringify(report,null,2)+"\n");console.log(JSON.stringify(report,null,2));}
if(!report.passed)process.exit(1);
