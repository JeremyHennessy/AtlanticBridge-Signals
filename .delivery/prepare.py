"""Branch-only delivery adapter; removed before the PR is opened."""
import hashlib,json,zipfile,os
from pathlib import Path
root=Path('.')
archive=Path(os.environ['REVIEW_ARCHIVE'])
assert hashlib.sha256(archive.read_bytes()).hexdigest()=='46f6e0853b6848cc10d5982e54bebeac2bf810e6e3ede19062b470e6c39a75a6'
with zipfile.ZipFile(archive) as z:src=json.loads(z.read('second/reviewed-discovery.json'))
actions={
'powerco-st-thomas':'Verify the current construction and production schedule before considering outreach; do not reuse the historical 2027 plan as a current commitment.',
'sanofi-toronto-flu':'Check whether the inaugurated influenza facility has entered production and whether relevant supplier opportunities remain open.',
'airliquide-becancour':'Look for a newer capacity or procurement announcement; the recorded 2021 operation is historical context, not a new entry lead.',
'tcb-burlington':'Verify the facility\'s current operating status and corporate identity before treating the opening announcement as an active opportunity.',
'klarna-toronto':'Confirm the current Toronto footprint and current hiring independently of the historical hiring target.',
'avanade-halifax':'Confirm the named Canadian legal entity and current office activity; do not treat the agency country label as verified parent control.'}
projects=[]
for r in src['records']:
 c=r['documentary_review']
 if not c:continue
 evidence=sorted(c['evidence'],key=lambda x:x['source_publication_date'],reverse=True)
 latest=evidence[0]
 pid=hashlib.sha256(('reviewed-project\x1f'+c['project_key']).encode()).hexdigest()
 events=[]
 for e in c['events']:
  er=next(x for x in evidence if x['source_id']==e['source_id'])
  events.append({k:e[k] for k in ['kind','date','date_basis','source_id']}|{'source_url':er['source_url'],'raw_sha256':er['raw_sha256']})
 projects.append({'id':pid,'project_key':c['project_key'],'company_name':r['company_candidate'],
  'country':r['source_country_as_published'],'location':r['location_text'],'title':r['investment_type_as_published'],
  'identity_scope':'REVIEWED_PROJECT_SOURCE_LOCAL_NOT_LEGAL_PARENT_JOIN','status':'DOCUMENTARY_HISTORY',
  'summary':c['interpretation'],'next_action':actions[c['id']],
  'prior_presence_status':c['prior_presence_status'],'reviewer':c['reviewer'],
  'source':{'observed_at':latest['last_observed_at'],'source_url':latest['source_url'],'source_sha256':latest['raw_sha256']},
  'latest_public_date':latest['source_publication_date'],'evidence':evidence,'events':events,
  'legal_identity_confirmed':False,'first_entry_confirmed':False,'backtest_eligible':False,
  'public_alert_allowed':False,'independent_holdout':False})
projects.sort(key=lambda x:(x['latest_public_date'],x['company_name']),reverse=True)
result={'schema_version':1,'status':'REVIEWED_HISTORY_NOT_CURRENT_ALERTS','baseline_commit':'4d87ea022b1ae5f439fe095b38b695a40ed6f830',
 'proof_artifact_id':10718724645,'proof_archive_sha256':'46f6e0853b6848cc10d5982e54bebeac2bf810e6e3ede19062b470e6c39a75a6',
 'project_count':len(projects),'projects':projects}
(root/'ui/data/reviewed-evidence.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

def replace(path,old,new,count=1):
 p=root/path;s=p.read_text();assert s.count(old)==count,(path,old[:80],s.count(old));p.write_text(s.replace(old,new))
replace('ui/index.html','  <script src="workbench.js" defer></script>','  <script src="reviewed.js" defer></script>\n  <script src="workbench.js" defer></script>')
old='''        <p class="small muted">Open a company name to investigate its notices and record a next action. Your worklist and notes stay in this browser; export a backup to preserve them. No team sync or automated follow-up reminders are available.</p>
      </section>'''
new=old[:-len('      </section>')]+'''        <section class="panel" aria-labelledby="reviewed-project-heading"><div class="panel-header"><div><p class="eyebrow">Separate evidence / Reviewed histories</p><h2 id="reviewed-project-heading">Company project histories</h2></div></div><div class="coverage-stack"><p>These six source-local project histories are not new alerts, verified parent identities, or additions to the procurement counts above. Open one to inspect its dated sources and save a next action.</p><div id="reviewed-project-list">Loading reviewed histories…</div></div></section>
        <section class="panel" aria-labelledby="monitoring-heading"><div class="panel-header"><div><p class="eyebrow">Source operations / Separate from website builds</p><h2 id="monitoring-heading">Company-source monitoring</h2></div><button class="button" id="monitoring-refresh" type="button">Load monitoring status</button></div><div class="coverage-stack" id="monitoring-status" role="status">Load the latest collection history. Collection changes require review; they are not automatic public expansion alerts.</div></section>
      </section>'''
replace('ui/index.html',old,new)
replace('ui/app.js','    fetchEvidence("data/live-signals.json",validateLivePayload),','    fetchEvidence("data/live-signals.json",validateLivePayload),\n    fetchEvidence("data/reviewed-evidence.json",ABReviewed.validate),')
replace('ui/app.js','  loadWatched();renderMetrics();renderSignals();','''  reviewedCatalog=results[2].status==="fulfilled"?results[2].value:null;
  loadWatched();renderMetrics();renderSignals();renderReviewedProjects();
  $("monitoring-refresh").addEventListener("click",loadMonitoringHealth);''')
replace('ui/workbench.js','function workCompanies() { return ABWorkspace.groupCompanies(state.live); }','function workCompanies() { const groups=ABWorkspace.groupCompanies(state.live);for(const [id,p] of ABReviewed.groups(reviewedCatalog)){if(!groups.has(id))groups.set(id,p);}return groups; }')
replace('ui/workbench.js','  workCompanyId=id;workDirty=false;workConflict=false;','  workCompanyId=id;workDirty=false;workConflict=false;\n  const reviewed=reviewedProject(id);if(reviewed){renderReviewedCompany(reviewed);return;}')
replace('ui/workbench.js','  const previous=workEntry(id) || ABWorkspace.blankEntry(id,company,state.live);','  const feed=workFeedFor(id);\n  const previous=workEntry(id) || ABWorkspace.blankEntry(id,company,feed);')
replace('ui/workbench.js','snapshot_observed_at:state.live.source?.observed_at || "",source_url:state.live.source?.source_url || "",source_sha256:state.live.source?.source_sha256 || ""','snapshot_observed_at:feed.source?.observed_at || "",source_url:feed.source?.source_url || "",source_sha256:feed.source?.source_sha256 || ""')
replace('ui/workbench.js','${company.signals.length} available source notices','${company.signals.length} ${company.reviewed?"reviewed historical events":"available source notices"}')
replace('tests/ui_visual_acceptance.mjs','import assert from "node:assert/strict";','import assert from "node:assert/strict";\nimport {verifyReviewed} from "./reviewed_acceptance.mjs";')
replace('tests/ui_visual_acceptance.mjs','"workspace.css","data/dashboard.json"','"workspace.css","reviewed.js","data/reviewed-evidence.json","data/dashboard.json"')
replace('tests/ui_visual_acceptance.mjs','    await verifyWorkspace(browser,options,base,label,out,check);','    await verifyWorkspace(browser,options,base,label,out,check);\n    await verifyReviewed(browser,options,base,label,out,check);')
replace('.github/workflows/ui-usability.yml','      - "tests/workspace_acceptance.mjs"','      - "tests/workspace_acceptance.mjs"\n      - "tests/reviewed_acceptance.mjs"\n      - "tests/test_reviewed.cjs"',2)
replace('.github/workflows/ui-usability.yml','run: node --test tests/test_workspace.cjs','run: node --test tests/test_workspace.cjs tests/test_reviewed.cjs')
replace('src/atlanticbridge/monitoring_checkpoint.py','Persistent fingerprints and clocks support operational change detection. Restricted\nraw documents stay in access-controlled Actions artifacts (90-day retention); this','Persistent fingerprints and clocks support operational change detection. Full\nraw documents stay in Actions artifacts (90-day retention); this')
expected=json.loads((root/'.delivery/hashes.json').read_text())
for path,sha in expected.items():
 actual=hashlib.sha256((root/path).read_bytes()).hexdigest()
 assert actual==sha,(path,actual,sha)
print('All',len(expected),'delivery files match locally tested bytes')
