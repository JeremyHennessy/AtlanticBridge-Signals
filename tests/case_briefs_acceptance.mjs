import fs from 'node:fs';
import path from 'node:path';
const briefs=JSON.parse(fs.readFileSync('ui/data/case-briefs.json','utf8'));
const catalog=JSON.parse(fs.readFileSync('ui/data/reviewed-evidence.json','utf8'));
export async function verifyCaseBriefs(browser,options,base,label,out,check){
 const context=await browser.newContext(options),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 try{
  await page.goto(base+'#opportunities',{waitUntil:'networkidle'});
  await page.locator('#case-brief-panel').evaluate(e=>e.open=true);
  check(`${label}: five bound dispositions in review index`,await page.locator('[data-brief-id]').count()===5);
  const nature=briefs.briefs.find(b=>b.company_name==='Nature Energy');
  for(const b of briefs.briefs){
   await page.goto(base+'#company?id='+b.company_id,{waitUntil:'networkidle'});
   await page.locator(`[data-case-disposition="${b.id}"]`).waitFor();
   const panel=page.locator('.case-disposition-panel'),text=await panel.innerText();
   check(`${label}: ${b.company_name} exact disposition title`,await panel.locator('h2').innerText()===b.title);
   check(`${label}: ${b.company_name} preserved conditional assessment`,text.includes(b.summary));
   check(`${label}: ${b.company_name} no automatic qualification or fit score`,text.toLowerCase().includes('not a qualified opportunity')&&text.toLowerCase().includes('context, not a fit score'),text);
   await panel.locator('details').evaluate(e=>e.open=true);
   check(`${label}: ${b.company_name} all disposition references exposed`,await panel.locator('.company-notice').count()===b.evidence.length);
   const old=catalog.projects.find(p=>p.id===b.company_id);
   if(old)check(`${label}: ${b.company_name} original history survives`,await page.locator('[data-reviewed-event]').count()===old.events.length);
   const fit=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));
   check(`${label}: ${b.company_name} case disposition fits`,fit.s<=fit.w+2,JSON.stringify(fit));
   if(b.company_name==='Sanofi'){
    check(`${label}: Sanofi production pending approval not current production`,text.includes('early 2027')&&text.includes('regulatory approval'));
    await page.screenshot({path:path.join(out,`${label}-sanofi-case-disposition.png`),fullPage:true});
   }
   if(b.company_name==='Roquette'){
    check(`${label}: Roquette locations never conflated`,text.includes('Portage la Prairie')&&text.includes('Winnipeg'));
    check(`${label}: restricted corporate links withheld in new brief`,await panel.locator('a[href*="roquette.com"]').count()===0);
   }
   if(b.company_name==='Nature Energy'){
    check(`${label}: PDF fiscal amendment has no invented publication day`,(await panel.innerText()).includes('Exact day unknown')&&(await panel.innerText()).includes('PDF page 52'));
    check(`${label}: original PDF is page-bound`,await panel.locator('a.source-link').getAttribute('href')===b.evidence[0].source_url+'#page=52');
    await page.locator('#work-action').fill('TEST ONLY: check continued Farnham development under ÉDI');
    await page.locator('#work-save').click();await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
    await page.screenshot({path:path.join(out,`${label}-nature-case-disposition.png`),fullPage:true});
   }
  }
  const saved=await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'));
  await page.route('**/data/case-briefs.json',route=>route.fulfill({status:503,body:'TEST case assessment outage'}));
  await page.goto(base+'#company?id='+nature.company_id,{waitUntil:'networkidle'});await page.reload({waitUntil:'networkidle'});
  check(`${label}: brief outage never removes original project evidence`,await page.locator('[data-reviewed-event]').count()===catalog.projects.find(p=>p.id===nature.company_id).events.length);
  check(`${label}: brief outage leaves exact saved work`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
  check(`${label}: saved corrective action survives assessment outage`,await page.locator('#work-action').inputValue()==='TEST ONLY: check continued Farnham development under ÉDI');
  await page.evaluate(()=>location.hash='#opportunities');await page.locator('#case-brief-panel').evaluate(e=>e.open=true);
  check(`${label}: case brief outage explicit not empty success`,(await page.locator('#case-brief-index').innerText()).includes('unavailable'));
  check(`${label}: case briefs no page errors`,errors.length===0,errors.join(' | '));
 }finally{await context.close();}
}
