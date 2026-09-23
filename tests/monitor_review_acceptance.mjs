import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url),api=require('../ui/monitor-review.js');
const register=JSON.parse(fs.readFileSync('ui/data/company-reviews.json','utf8'));
const url='https://raw.githubusercontent.com/JeremyHennessy/AtlanticBridge-Signals/monitoring-state/checkpoint.json';
function fixture(){
 const review=register.decisions.find(r=>r.company_name==='Adyen Canada Ltd.'),sid='adyen-payments-membership';
 const last=new Date(Date.now()-60000).toISOString(),first=new Date(Date.now()-86400000).toISOString(),finished=new Date(Date.now()-30000).toISOString();
 const r={id:'a'.repeat(64),source_id:sid,source_record_id:'TEST_ONLY_METADATA',source_url:'https://example.org/fixture-not-a-real-lead',source_publication_date:null,publication_precision:'UNKNOWN',publication_clock:'UNKNOWN',source_updated_at:null,first_observed_at:first,last_observed_at:last,raw_sha256:'d'.repeat(64),canada_relevance:'CANDIDATE_REQUIRES_REVIEW',scope_exclusion:null,backtest_eligible:false,public_alert_allowed:false};
 const e={id:'b'.repeat(64),kind:'RECORD_CHANGED',observed_at:last,public_alert_allowed:false,review_required:true,record:r};
 const c={schema_version:1,raw_retention_days:90,historical_backtest_eligible:false,tables:{company_source_state:[{id:sid,contract:'e'.repeat(64),last_success:last}],company_observations:[{id:r.id,source_id:sid,first_seen:first,last_seen:last,fingerprint:'f'.repeat(64),payload:JSON.stringify(r)}],company_observation_events:[{id:e.id,source_id:sid,observed_at:last,kind:e.kind,payload:JSON.stringify(e)}]},runs:[{id:'TEST_ONLY_NOT_PRODUCTION_RUN',finished_at:finished,sources:[{id:sid,status:'OBSERVED'}]}]};
 c.checksum=crypto.createHash('sha256').update(api.canonical(c)).digest('hex');return {c,review};
}
export async function verifyMonitorReview(browser,options,base,label,out,check){
 const context=await browser.newContext(options),page=await context.newPage(),errors=[];
 page.on('pageerror',e=>errors.push(String(e)));
 try{
  const {c,review}=fixture();
  await page.route(url,r=>r.fulfill({contentType:'application/json',body:JSON.stringify(c)}));
  await page.goto(base+'#opportunities',{waitUntil:'networkidle'});
  await page.locator('#monitor-review-panel').evaluate(n=>n.open=true);await page.locator('#monitor-review-load').click();
  await page.waitForFunction(()=>!document.querySelector('#monitor-review-load').disabled);
  check(`${label}: metadata checkpoint verified before rendering`,await page.locator('#monitor-review-list').getAttribute('data-checksum')===c.checksum);
  check(`${label}: source-bound metadata routes one review`,await page.locator('[data-monitor-review-item]').count()===1);
  check(`${label}: monitor observation is not fabricated publication`,(await page.locator('#monitor-review-list').innerText()).includes('Unknown; not replaced by observation time'));
  check(`${label}: monitor record remains unqualified`,(await page.locator('#monitor-review-status').innerText()).includes('No change is a qualified opportunity'));
  const box=await page.evaluate(()=>({w:innerWidth,s:document.documentElement.scrollWidth}));check(`${label}: monitor fixture fits`,box.s<=box.w+2);
  await page.screenshot({path:path.join(out,`${label}-monitor-review-fixture.png`),fullPage:true});
  await page.locator('#monitor-review-list .button').click();await page.locator('#work-action').waitFor();
  check(`${label}: monitored change opens exact reviewed company`,await page.locator('#company-title').innerText()===review.company_name);
  await page.locator('#work-action').fill('TEST ONLY: follow up this metadata change');await page.locator('#work-save').click();
  await page.waitForFunction(()=>document.querySelector('#work-save-state')?.textContent.includes('Saved in this browser'));
  const saved=await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'));
  await page.unroute(url);await page.route(url,r=>r.fulfill({contentType:'application/json',body:JSON.stringify({...c,checksum:'0'.repeat(64)})}));
  await page.evaluate(()=>location.hash='#opportunities');await page.locator('#monitor-review-panel').evaluate(n=>n.open=true);await page.locator('#monitor-review-load').click();await page.waitForFunction(()=>!document.querySelector('#monitor-review-load').disabled);
  check(`${label}: corrupt monitor cannot render stale success`,await page.locator('#monitor-review-list').getAttribute('data-checksum')===null&&(await page.locator('#monitor-review-status').innerText()).includes('unavailable or invalid'));
  check(`${label}: corrupt metadata leaves exact saved work`,await page.evaluate(()=>localStorage.getItem('atlanticbridge.analyst-workspace.v1'))===saved);
  if(process.env.REQUIRE_LIVE_SIGNALS==='1'){
   await page.unroute(url);
   const raw=await page.evaluate(async u=>{const r=await fetch(u,{cache:'no-store'});if(!r.ok)throw Error('Actual checkpoint unavailable');return r.text();},url);
   const expected=await api.parse(raw,register);
   await page.locator('#monitor-review-load').click();await page.waitForFunction(()=>!document.querySelector('#monitor-review-load').disabled);
   check(`${label}: real retained checkpoint renders`,await page.locator('#monitor-review-list').getAttribute('data-checksum')===expected.checkpoint_checksum);
   check(`${label}: actual monitored metadata counts`,await page.locator('[data-monitor-review-item]').count()===expected.items.length,JSON.stringify(expected.counts));
   await page.screenshot({path:path.join(out,`${label}-actual-monitor-review.png`),fullPage:true});
  }
  check(`${label}: monitor routing no page errors`,errors.length===0,errors.join(' | '));
 }finally{await context.close();}
}
