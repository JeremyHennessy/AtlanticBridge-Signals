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
    await fit('current');await page.screenshot({path:path.join(out,`${label}-opportunity-current.png`),fullPage:true});
    await page.locator('[data-opportunity-view="qualified"]').click();
    check(`${label}: qualified empty state explains held evidence`,(await page.locator('#opportunity-list').innerText()).includes('No loaded current item has passed every qualification check'));
    await page.locator('[data-opportunity-view="history"]').click();
    check(`${label}: fifteen reviewed histories in separate queue`,await page.locator('[data-opportunity-id]').count()===15);
    for(const p of catalog.projects){const row=page.locator(`[data-opportunity-id="project:${p.id}"]`);check(`${label}: queue correct dossier link ${p.id}`,await row.locator('.company-dossier-link').getAttribute('href')==='#company?id='+p.id);check(`${label}: queue source provenance ${p.id}`,await row.locator('.source-link').getAttribute('href')===p.source.source_url);}
    await page.locator('#opportunity-search').fill('cellcentric');
    check(`${label}: opportunity search narrows source-local records`,await page.locator('[data-opportunity-id]').count()===1);
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: opportunity URL search survives reload`,await page.locator('#opportunity-search').inputValue()==='cellcentric'&&await page.locator('[data-opportunity-id]').count()===1);
    await fit('searched history');await page.screenshot({path:path.join(out,`${label}-opportunity-history.png`),fullPage:true});
    await page.locator('#opportunity-list .company-dossier-link').first().click();await page.locator('#work-action').waitFor();
    const project=catalog.projects.find(p=>p.company_name.toLowerCase().includes('cellcentric'));
    check(`${label}: opportunity opens actual project dossier`,await page.locator('#company-title').innerText()===project.company_name);
    await page.locator('#work-action').fill('TEST ONLY: qualify current operator');await page.locator('#work-save').click();
    await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
    const saved=await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'));
    await goto('#opportunities');
    await page.route('**/data/company-reviews.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: unavailable qualifications not zero`,await page.locator('#opportunity-qualified-count').innerText()==='Unverified');
    check(`${label}: register failure leaves current evidence`,await page.locator('[data-opportunity-id]').count()===model.current.length);
    check(`${label}: register failure preserves saved action bytes`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
    await page.route('**/data/reviewed-evidence.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: unavailable histories not zero`,await page.locator('#opportunity-history-count').innerText()==='Unverified');
    check(`${label}: histories unavailable leaves procurement`,await page.locator('[data-opportunity-id]').count()===api.queue(live,null,null).current.length);
    await page.route('**/data/live-signals.json',r=>r.fulfill({status:503,body:'TEST source failure'}));await page.reload({waitUntil:'networkidle'});
    check(`${label}: all queue sources unavailable not zero activity`,await page.locator('#opportunity-current-count').innerText()==='Unverified');
    check(`${label}: independent failure warnings visible`,(await page.locator('#opportunity-coverage').innerText()).includes('Missing coverage is not zero activity'));
    check(`${label}: all source failures preserve notes bytes`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
    await page.screenshot({path:path.join(out,`${label}-opportunity-unavailable.png`),fullPage:true});
    check(`${label}: opportunity no JavaScript page errors`,errors.length===0,errors.join(' | '));
  }finally{await context.close();}
}
