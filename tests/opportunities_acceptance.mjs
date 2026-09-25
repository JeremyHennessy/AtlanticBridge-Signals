import {capturePage} from './bounded_screenshot.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),api=require('../ui/opportunities.js');
const catalog=JSON.parse(fs.readFileSync('ui/data/reviewed-evidence.json','utf8'));
const register=JSON.parse(fs.readFileSync('ui/data/company-reviews.json','utf8'));
export async function verifyOpportunities(browser,options,base,label,out,check){
  const context=await browser.newContext(options),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  const goto=async hash=>{await page.evaluate(h=>location.hash=h,hash);await page.locator('#opportunities-view').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#opportunity-current-count')?.textContent!=='—');};
  const fit=async suffix=>{const b=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));check(`${label}: opportunity ${suffix} fits`,b.s<=b.w+2,JSON.stringify(b));};
  try{
    await page.goto(base,{waitUntil:'networkidle'});await goto('#opportunities');
    const live=await page.evaluate(async()=>{const r=await fetch(new URL('data/live-signals.json',location.href));return r.ok?r.json():null;});
    const model=api.queue(live,catalog,register,await page.evaluate(()=>Date.now()));
    check(`${label}: opportunity public-date recency`,await page.locator('[data-opportunity-id]').count()===model.current.length);
    check(`${label}: opportunity register decision count`,await page.locator('[data-review-decision]').count()===20);
    check(`${label}: opportunity qualification is not fabricated`,await page.locator('#opportunity-qualified-count').innerText()==='0');
    check(`${label}: opportunity existing watch store untouched`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1')===null||JSON.parse(localStorage.getItem('atlanticbridge.analyst-workspace.v1')).entries.length===0));
    check(`${label}: qualification progress visible without expanding details`,(await page.locator('[data-opportunity-id]').first().innerText()).includes('Qualification:'));
    check(`${label}: qualification blocker summary visible`,api.checks.every(k=>(documentText=>documentText.includes(api.checkLabels[k]))(await page.locator('#opportunity-gates').innerText())));
    const legalBlockers=model.current.filter(r=>api.readiness(r.decision).blockers.includes('legal_identity')).length;
    await page.locator('#opportunity-blocker').selectOption('legal_identity');
    check(`${label}: legal-identity blocker filter`,await page.locator('[data-opportunity-id]').count()===legalBlockers);
    check(`${label}: blocker filter persists in URL`,page.url().includes('blocker=legal_identity'));
    await page.locator('#opportunity-reset').click();
    check(`${label}: blocker reset clears qualification filter`,await page.locator('#opportunity-blocker').inputValue()==='');
    await fit('current');await capturePage(page,path.join(out,`${label}-opportunity-current.png`));
    await page.locator('[data-opportunity-view="qualified"]').click();
    check(`${label}: qualified empty state explains held evidence`,(await page.locator('#opportunity-list').innerText()).includes('No loaded current item has passed every qualification check'));
    await page.locator('[data-opportunity-view="history"]').click();
    check(`${label}: fifteen reviewed histories in separate queue`,await page.locator('[data-opportunity-id]').count()===15);
    for(const p of catalog.projects){const row=page.locator(`[data-opportunity-id="project:${p.id}"]`);check(`${label}: queue correct dossier link ${p.id}`,await row.locator('.company-dossier-link').getAttribute('href')==='#company?id='+p.id);check(`${label}: queue source provenance ${p.id}`,await row.locator('.source-link').getAttribute('href')===p.source.source_url);}
    await page.locator('#opportunity-search').fill('cellcentric');
    check(`${label}: opportunity search narrows source-local records`,await page.locator('[data-opportunity-id]').count()===1);
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: opportunity URL search survives reload`,await page.locator('#opportunity-search').inputValue()==='cellcentric'&&await page.locator('[data-opportunity-id]').count()===1);
    await fit('searched history');await capturePage(page,path.join(out,`${label}-opportunity-history.png`));
    await page.locator('#opportunity-list .company-dossier-link').first().click();await page.locator('#work-action').waitFor();
    const project=catalog.projects.find(p=>p.company_name.toLowerCase().includes('cellcentric'));
    check(`${label}: opportunity opens actual project dossier`,await page.locator('#company-title').innerText()===project.company_name);
    await page.locator('#work-action').fill('TEST ONLY: qualify current operator');await page.locator('#work-save').click();
    await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
    const saved=await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'));
    await goto('#opportunities');
    await page.route('**/data/company-reviews.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: unavailable qualifications not zero`,await page.locator('#opportunity-qualified-count').innerText()==='Unverified');
    check(`${label}: register failure leaves independently available current evidence`,await page.locator('[data-opportunity-id]').count()===api.queue(live,catalog,null).current.length);
    check(`${label}: register failure preserves saved action bytes`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
    await page.route('**/data/reviewed-evidence.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: unavailable histories not zero`,await page.locator('#opportunity-history-count').innerText()==='Unverified');
    check(`${label}: histories unavailable leaves procurement`,await page.locator('[data-opportunity-id]').count()===api.queue(live,null,null).current.length);
    await page.route('**/data/live-signals.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: all queue sources unavailable not zero activity`,await page.locator('#opportunity-current-count').innerText()==='Unverified');
    check(`${label}: independent failure warnings visible`,(await page.locator('#opportunity-coverage').innerText()).includes('Missing coverage is not zero activity'));
    check(`${label}: all source failures preserve notes bytes`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
    await capturePage(page,path.join(out,`${label}-opportunity-unavailable.png`));
    check(`${label}: opportunity no JavaScript page errors`,errors.length===0,errors.join(' | '));
  }finally{await context.close();}
}

// Independent fixture contexts exercise qualification routes without promoting live data.
export async function verifyOpportunityPaths(browser,options,base,label,out,check){
  const context=await browser.newContext(options),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  const fit=async suffix=>{const box=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));check(`${label}: qualification path ${suffix} fits`,box.s<=box.w+2,JSON.stringify(box));};
  try{
    await page.goto(base+'#opportunities',{waitUntil:'networkidle'});
    await page.locator('#opportunity-review-register').waitFor({state:'attached'});
    await page.locator('details:has(#opportunity-review-register)').evaluate(e=>e.open=true);
    const real=register.decisions.find(r=>r.company_name==='Adyen Canada Ltd.'&&r.project_id===null);
    const link=page.locator(`[data-review-decision="${real.id}"] .company-dossier-link`);
    check(`${label}: actual company-only review has stable link`,await link.getAttribute('href')==='#company?id='+real.id);
    await link.click();await page.locator('#work-save').waitFor();
    check(`${label}: company-only dossier has actual name`,await page.locator('#company-title').innerText()===real.company_name);
    check(`${label}: review dossier never inherits procurement supplier semantics`,!(await page.locator('#company-content').innerText()).includes('Supplier address country'));
    check(`${label}: all company-only evidence available`,await page.locator('[data-company-review-evidence]').count()===real.evidence.length);
    await page.locator('#work-action').fill('TEST ONLY: retain company-only investigation');
    await page.locator('#work-notes').fill('TEST ONLY: notes must survive source outage');
    await page.locator('#work-save').click();await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
    const saved=await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'));
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: company-only notes survive reload`,await page.locator('#work-action').inputValue()==='TEST ONLY: retain company-only investigation');
    await fit('actual company-only');await capturePage(page,path.join(out,`${label}-company-only-review.png`));
    await page.evaluate(()=>location.hash='#worklist');await page.locator('#worklist-view').waitFor({state:'visible'});
    check(`${label}: company-only worklist is not a procurement count`,(await page.locator(`[data-worklist-id="${real.id}"]`).innerText()).includes('review evidence references'));
    await page.locator(`[data-worklist-id="${real.id}"] .work-company-link`).click();await page.locator('#work-save').waitFor();
    await page.route('**/data/company-reviews.json',route=>route.fulfill({status:503,body:'TEST review outage'}));
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: review outage preserves exact work bytes`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
    check(`${label}: saved company-only dossier survives evidence outage`,await page.locator('#work-action').inputValue()==='TEST ONLY: retain company-only investigation');
    check(`${label}: saved review outage not fabricated supplier`,(await page.locator('#company-content').innerText()).includes('Saved country label'));
    await page.unroute('**/data/company-reviews.json');
    const today=new Date(await page.evaluate(()=>Date.now())).toISOString().slice(0,10);
    const old=catalog.projects.find(p=>p.latest_public_date<'2025-01-01');
    const ref={source_id:'TEST_ONLY_CURRENT_QUALIFICATION',source_url:'https://example.org/test-only-evidence',raw_sha256:'a'.repeat(64),observed_at:today+'T00:00:00Z',source_publication_date:today};
    const qualified=(row)=>({...structuredClone(row),decision:'QUALIFIED_FOR_INVESTIGATION',review_date:today,reviewer:'TEST_ONLY_NOT_A_REAL_REVIEW',current_status_date:today,current_status_source_id:ref.source_id,evidence:[ref],checks:Object.fromEntries(api.checks.map(k=>[k,'SUPPORTED'])),check_sources:Object.fromEntries(api.checks.map(k=>[k,[ref.source_id]]))});
    const fixture=structuredClone(register);
    fixture.decisions=fixture.decisions.map(r=>r.project_id===old.id||r.id===real.id?qualified(r):r);
    await page.route('**/data/company-reviews.json',route=>route.fulfill({contentType:'application/json',body:JSON.stringify(fixture)}));
    await page.goto(base+'#opportunities?view=qualified',{waitUntil:'networkidle'});await page.reload({waitUntil:'networkidle'});
    check(`${label}: both qualified path regressions render`,await page.locator('[data-opportunity-id]').count()===2);
    check(`${label}: company-only qualified card exists`,await page.locator(`[data-opportunity-id="review:${real.id}"]`).count()===1);
    const oldCard=page.locator(`[data-opportunity-id="project:${old.id}"]`);
    check(`${label}: old project qualifies on newer status evidence`,await oldCard.count()===1);
    check(`${label}: old project date remains unmodified`,(await oldCard.locator('p.small.muted').innerText()).includes(String(new Date(old.latest_public_date).getUTCFullYear())));
    check(`${label}: newer qualification source visible separately`,(await oldCard.innerText()).includes('Qualification status evidence'));
    await fit('qualified fixtures');await capturePage(page,path.join(out,`${label}-qualified-path-fixtures.png`));
    await page.locator(`[data-opportunity-id="review:${real.id}"] .company-dossier-link`).click();await page.locator('#work-save').waitFor();
    check(`${label}: qualification never overwrites saved work`,await page.locator('#work-action').inputValue()==='TEST ONLY: retain company-only investigation');
    check(`${label}: new dossier shows qualification, not prediction`,(await page.locator('#company-content').innerText()).includes('Qualified for investigation'));
    // Every current status date is expired here; changing the original project date cannot revive it.
    fixture.decisions=fixture.decisions.map(r=>r.decision==='QUALIFIED_FOR_INVESTIGATION'?{...r,review_date:'2020-01-01',current_status_date:'2020-01-01',evidence:[{...ref,source_publication_date:'2020-01-01'}]}:r);
    await page.goto(base+'#opportunities?view=qualified',{waitUntil:'networkidle'});await page.reload({waitUntil:'networkidle'});
    check(`${label}: both expired qualifications excluded`,await page.locator('[data-opportunity-id]').count()===0);
    check(`${label}: path acceptance no page errors`,errors.length===0,errors.join(' | '));
  }finally{await context.close();}
}
