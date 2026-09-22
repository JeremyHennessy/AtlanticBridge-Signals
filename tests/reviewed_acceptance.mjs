import fs from 'node:fs';
import path from 'node:path';

// All saves and injected failures use new browser contexts, never a user's work.
export async function verifyReviewed(browser,options,base,label,out,check){
  const catalog=JSON.parse(fs.readFileSync('ui/data/reviewed-evidence.json','utf8'));
  const context=await browser.newContext(options),page=await context.newPage();
  const key='atlanticbridge.analyst-workspace.v1';
  try{
    await page.goto(base,{waitUntil:'networkidle'});
    await page.waitForFunction(()=>document.querySelector('#metric-cases')?.textContent==='27');
    await page.evaluate(()=>location.hash='#signals');
    await page.locator('[data-reviewed-project]').first().waitFor();
    const procurement=await page.locator('[data-live-signal-id]').count();
    if(process.env.REQUIRE_LIVE_SIGNALS==='1'){
      let actual=null;
      for(let attempt=0;attempt<12&&!actual;attempt++){
        actual=await page.evaluate(async()=>{try{const r=await fetch('https://raw.githubusercontent.com/JeremyHennessy/AtlanticBridge-Signals/monitoring-state/health.json',{cache:'no-store'});return r.ok?await r.json():null;}catch(_){return null;}});
        if(!actual)await page.waitForTimeout(5000);
      }
      check(`${label}: actual public monitoring state is accessible`,actual?.schema_version===1&&actual.sources?.length===8&&actual.run_id&&actual.last_attempt_at);
      await page.locator('#monitoring-refresh').click();
      await page.waitForFunction(()=>!document.querySelector('#monitoring-refresh')?.disabled);
      const liveHealth=await page.locator('#monitoring-status').innerText();
      check(`${label}: real monitoring status renders without fixture replacement`,!liveHealth.includes('could not be loaded')&&actual.sources.every(source=>liveHealth.includes(source.id)));
      check(`${label}: real monitoring retains fourteen-day qualification`,liveHealth.includes('14-day operational target')&&liveHealth.includes('No prediction has been validated'));
      await page.locator('#monitoring-status').screenshot({path:path.join(out,`${label}-actual-monitoring-status.png`)});
    }
    check(`${label}: six reviewed project links`,await page.locator('[data-reviewed-project]').count()===catalog.project_count);
    for(const p of catalog.projects){
      await page.evaluate(id=>location.hash='#company?id='+id,p.id);
      await page.waitForFunction(name=>document.querySelector('#company-title')?.textContent===name,p.company_name);
      check(`${label}: reviewed project event count ${p.id}`,await page.locator('[data-reviewed-event]').count()===p.events.length);
      const text=await page.locator('#company-content').innerText();
      check(`${label}: reviewed histories not new alerts ${p.id}`,text.includes('not a new expansion alert')&&text.includes('not a verified legal entity'));
      for(let i=0;i<p.events.length;i++)check(`${label}: exact reviewed source ${p.id}:${i}`,await page.locator('[data-reviewed-event] .source-link').nth(i).getAttribute('href')===p.events[i].source_url);
      const bounds=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));
      check(`${label}: reviewed dossier fits ${p.id}`,bounds.s<=bounds.w+2,JSON.stringify(bounds));
    }
    const first=catalog.projects[0];
    await page.evaluate(id=>location.hash='#company?id='+id,first.id);
    await page.waitForFunction(name=>document.querySelector('#company-title')?.textContent===name,first.company_name);
    await page.locator('#work-action').fill('TEST: verify current facility activity');
    await page.locator('#work-notes').fill('<script>unsafe()</script> TEST-only notes');
    await page.locator('#work-save').click();
    await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
    const saved=await page.evaluate(({key,id})=>JSON.parse(localStorage.getItem(key)).entries.find(e=>e.id===id),{key,id:first.id});
    check(`${label}: reviewed source provenance saved, not CanadaBuys`,saved.source_url===first.source.source_url&&saved.source_sha256===first.source.source_sha256&&saved.snapshot_observed_at===first.source.observed_at);
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: reviewed notes survive reload`,await page.locator('#work-notes').inputValue()==='<script>unsafe()</script> TEST-only notes');
    check(`${label}: notes are text not injected nodes`,await page.locator('#company-content script').count()===0);
    await page.locator('#reviewer-label').fill('TEST-only reviewer');
    await page.locator('#review-supported').selectOption('true');
    await page.locator('#review-useful').selectOption('true');
    await page.locator('#review-known').selectOption('false');
    await page.locator('#review-feedback-form button[type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#review-feedback-state')?.textContent.includes('Saved in this browser'));
    const downloadPromise=page.waitForEvent('download');await page.locator('#review-export').click();
    const download=await downloadPromise,file=path.join(out,`${label}-feedback-test-only.json`);await download.saveAs(file);
    const reviews=JSON.parse(fs.readFileSync(file,'utf8'));
    check(`${label}: actual feedback download preserves unknown identity`,reviews.length===1&&reviews[0].identity_correct===null&&reviews[0].useful===true&&reviews[0].already_known===false&&reviews[0].timing_basis==='ELAPSED_PAGE_VIEW_INCLUDES_IDLE');
    await page.locator('#review-feedback-state').click();
    await page.screenshot({path:path.join(out,`${label}-reviewed-project.png`),fullPage:true});
    await page.evaluate(()=>location.hash='#worklist');await page.locator(`[data-worklist-id="${first.id}"]`).waitFor();
    check(`${label}: reviewed project joins existing worklist`,(await page.locator(`[data-worklist-id="${first.id}"]`).innerText()).includes('reviewed historical events'));
    await page.route('**/data/reviewed-evidence.json',route=>route.fulfill({status:503,body:'TEST failure'}));
    await page.reload({waitUntil:'networkidle'});
    check(`${label}: source failure preserves saved project`,await page.locator(`[data-worklist-id="${first.id}"]`).count()===1);
    await page.evaluate(id=>location.hash='#company?id='+id,first.id);
    await page.waitForFunction(name=>document.querySelector('#company-title')?.textContent===name,first.company_name);
    const unavailable=await page.locator('#company-content').innerText();
    check(`${label}: unavailable project is not relabelled as a supplier`,unavailable.includes('Saved country label')&&!unavailable.includes('Supplier address country')&&!unavailable.includes('Current supplier evidence'));
    check(`${label}: unavailable dossier retains notes`,await page.locator('#work-notes').inputValue()==='<script>unsafe()</script> TEST-only notes');
    await page.evaluate(()=>location.hash='#signals');await page.locator('#signals-list').waitFor();
    check(`${label}: reviewed failure leaves procurement unchanged`,await page.locator('[data-live-signal-id]').count()===procurement);
    check(`${label}: reviewed failure explicit`,(await page.locator('#reviewed-project-list').innerText()).includes('unavailable'));
    await page.route('https://raw.githubusercontent.com/**/health.json',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({schema_version:1,status:'DEGRADED',last_attempt_at:new Date().toISOString(),sources:[{id:'TEST source',status:'UNVERIFIED_SOURCE_FAILURE',source_url:'https://example.org/',records:null,last_success_at:null}],consecutive_successful_days:0,retention:'TEST-only retention'})}));
    await page.locator('#monitoring-refresh').click();await page.waitForFunction(()=>document.querySelector('#monitoring-status')?.textContent.includes('source failures'));
    check(`${label}: failed source never displayed as zero records`,(await page.locator('#monitoring-status').innerText()).includes('coverage unverified')&&!(await page.locator('#monitoring-status').innerText()).includes('0 records observed'));
  }finally{await context.close();}
}
