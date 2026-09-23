"""Build source-local review data from exact accepted artifacts, not a forecast cohort.

Usage: python scripts/build_pilot_release.py --documentary-proof proof.zip
       --monitor-proof monitor.zip
Artifacts are read, never executed. Output retains every original six-project value.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SIX_SHA = '6777f23591c1263da741133f69de62757ca256b1267a7663afb1dc3240a80125'
DOC_ID, DOC_SHA = 10724340100, 'eb1a6546cf4306118d0dc77cbb7e665468230a169cefed7ed5dc56ef52acaf0a'
MON_ID, MON_SHA = 10720884358, 'db6e1b2055d27d3bf945a2c2ce228321b3425d1dea4c6baaf4d9d78f7713e802'
QUAL_ID, QUAL_SHA = 10729310481, '478167783afbd109deccc8a4576252fef895a67c9585ce8c61c45ae937336365'
CHECKS = ('legal_identity', 'corporate_group', 'civilian_scope', 'canadian_relevance', 'current_status', 'source_reuse')
NEXT = {
 'cellcentric-burnaby':'Confirm the current Canadian operating entity, production activity and civilian supplier requirements at the Burnaby facility; do not treat its relocation as first entry.',
 'stellantis-brampton':'Check the latest issuer update on Brampton retooling, timing and procurement before acting on the 2022 investment announcement.',
 'nature-energy-farnham':'Verify the latest project status, including the unresolved reported withdrawal, and current ownership before treating Farnham as an active project. Retrieve and review the cited primary PDF.',
 'ubisoft-sherbrooke':'Confirm whether this studio is currently operating and hiring and identify the Canadian legal entity before outreach.',
 'roquette-manitoba-rd':'Determine whether the record describes a collaborative R&D project or a separate facility, then verify the location, operator and current requirements.',
 'siemens-greenview':'Check whether the Greenview pilot remains in operation and who operates it. A completed-by bound is not an exact commissioning date.',
 'novabus-saint-francois':'Check the factory’s latest operating status and current capacity or supplier needs before acting on the 2021 transformation announcement.',
 'enel-pincher-creek':'Verify current asset ownership and operating or maintenance opportunities. These projects added capacity to an existing Canadian presence.',
 'accenture-st-catharines':'Confirm the centre’s present activity, hiring and legal operator. The source documents expansion of an existing Canadian business.',
}

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def ident(namespace, value):
    return hashlib.sha256((namespace + ':' + value).encode()).hexdigest()

def archive(path, expected):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Artifact checksum mismatch')
    z=zipfile.ZipFile(io.BytesIO(raw))
    names=z.namelist()
    if len(names)!=len(set(names)) or len(names)>5000 or sum(i.file_size for i in z.infolist())>128*1024*1024: raise ValueError('Oversized or duplicate archive')
    for i in z.infolist():
        p=PurePosixPath(i.filename)
        if p.is_absolute() or '..' in p.parts or '\\' in i.filename or (i.external_attr>>16)&0o170000==0o120000: raise ValueError('Unsafe artifact entry')
    return z

def read_json(z, path): return json.loads(z.read(path))

def checked_report(z, stage):
    report=read_json(z,stage+'/report.json')
    for response in report['responses']:
        if 'sha256' in response and hashlib.sha256(z.read(stage+'/raw/'+response['sha256']+'.bin')).hexdigest()!=response['sha256']: raise ValueError('Retained raw response mismatch')
    if report.get('failures'): raise ValueError('Failed source proof cannot produce accepted UI data')
    return report

def build(documentary_zip, monitor_zip, qualification_zip):
    dz=archive(documentary_zip,DOC_SHA);mz=archive(monitor_zip,MON_SHA);qz=archive(qualification_zip,QUAL_SHA)
    for stage in ('first','second'):
        r=checked_report(dz,stage)
        if r['summary']['successful_source_paths']!=11 or r['summary']['source_records']!=81 or r['summary']['change_events']!=0: raise ValueError('Unaccepted documentary source proof')
    first=read_json(dz,'first/reviewed-discovery.json');second=read_json(dz,'second/reviewed-discovery.json')
    original={r['id']:r['first_observed_at'] for r in first['records']}
    if any(original[r['id']]!=r['first_observed_at'] for r in second['records']): raise ValueError('First observation changed')
    baseline=json.loads((ROOT/'ui/data/reviewed-evidence.json').read_text())
    preserved=baseline['projects'][:6]
    if hashlib.sha256(canonical(preserved)).hexdigest()!=SIX_SHA: raise ValueError('Original six approved project records changed')
    projects=deepcopy(preserved)
    for row in second['records']:
        review=row.get('documentary_review')
        if not review: continue
        refs={e['source_id']:e for e in review['evidence']}
        latest=max(refs.values(),key=lambda e:e['source_publication_date'])
        p=dict(id=ident('reviewed-project-v1',row['source_record_id']+':'+review['project_key']),project_key=review['project_key'],company_name=row['company_candidate'],country=row['source_country_as_published'],location=row['location_text'],title=row['investment_type_as_published'],identity_scope='REVIEWED_PROJECT_SOURCE_LOCAL_NOT_LEGAL_PARENT_JOIN',status='DOCUMENTARY_HISTORY',summary=review['interpretation'],next_action=NEXT[review['id']],prior_presence_status=review['prior_presence_status'],reviewer=review['reviewer'],source={'observed_at':latest['last_observed_at'],'source_url':latest['source_url'],'source_sha256':latest['raw_sha256']},latest_public_date=latest['source_publication_date'],evidence=review['evidence'],events=[])
        for key in ('legal_identity_confirmed','first_entry_confirmed','backtest_eligible','public_alert_allowed','independent_holdout'):p[key]=False
        for event in review['events']:
            ref=refs[event['source_id']]
            p['events'].append({k:event[k] for k in ('kind','date','date_basis','source_id')}|{'source_url':ref['source_url'],'raw_sha256':ref['raw_sha256']})
        projects.append(p)
    if len(projects)!=15 or len({p['id'] for p in projects})!=15: raise ValueError('Unexpected reviewed project count')
    catalog={k:v for k,v in baseline.items() if k not in ('projects','project_count','additional_proofs')}
    catalog.update(project_count=15,projects=projects,additional_proofs=[{'artifact_id':DOC_ID,'archive_sha256':DOC_SHA,'preserved_six_project_values_sha256':SIX_SHA}])
    decisions=[]
    for p in projects:
        evidence=[{'source_id':e['source_id'],'source_url':e['source_url'],'raw_sha256':e['raw_sha256'],'observed_at':e['last_observed_at'],'source_publication_date':e['source_publication_date']} for e in p['evidence']]
        checks={k:'UNKNOWN' for k in CHECKS};checks['canadian_relevance']='SUPPORTED'
        links={k:[] for k in CHECKS};links['canadian_relevance']=[e['source_id'] for e in evidence]
        # Civilian project wording is not company-wide dual-use clearance or source reuse permission.
        decisions.append(dict(id=ident('company-review-v1',p['id']),project_id=p['id'],company_name=p['company_name'],decision='HOLD',review_date='2026-09-22',reviewer='assistant-source-review-2026-09-22',reason=p['summary']+' Exact legal identity, ownership, present status, civilian scope and commercial source reuse still require separate qualification.',next_action=p['next_action'],checks=checks,check_sources=links,evidence=evidence,current_status_date=None,current_status_source_id=None,first_entry_confirmed=False,predictive_score_allowed=False,independent_holdout=False))
    mr=checked_report(mz,'first')
    if mr['retained_observation_count']!=373 or len(mr['sources'])!=8: raise ValueError('Unexpected accepted monitor proof')
    sources={s['id']:s for s in mr['sources']}
    responses={x['sha256']:x for x in mr['responses'] if 'sha256' in x}
    manifest=json.loads((ROOT/'reviews/company_sources/pilot-2026-09-22.json').read_text())
    settings={s['id']:s for s in manifest['sources']}
    extra=[
      ('Mistral AI',['mistral-official-careers','mistral-montreal-announcement'],'A Canadian-hub announcement and seven Canada-location hiring records are retained. All seven job candidates remain scope-held because of defence wording; zero unheld jobs is not no Canadian hiring.','Review role-specific civilian scope, the exact legal entity and current hub status before treating these observations as an opportunity.'),
      ('DeepL',['deepl-official-careers'],'The accepted board capture contains 40 published job records. No Canada-location candidate was retained in that bounded capture; this does not establish company-wide absence or no Canadian plans.','Seek dated Canada-specific hiring or announcement evidence and verify the legal entity and ownership before qualification.'),
      ('Pleo',['pleo-official-careers'],'The accepted board capture contains 30 published job records. The bounded board does not establish Canadian presence or absence, and does not prove expansion intent.','Verify legal identity and find a specific, dated Canada-facing change before promoting this monitoring target.'),
      ('Giesecke+Devrient',['gd-montreal-announcement'],'The Montreal announcement describes an AI centre and explicitly reports Canadian presence since 1962. It is an expansion context record, not first Canadian entry.','Verify the operating entity, current centre activity and civilian commercial needs; retain existing Canadian presence in the classification.'),
      ('Adyen Canada Ltd.',['adyen-payments-membership'],'The source documents Payments Canada membership. Membership is not a verified first office, first operation or first Canadian entry.','Resolve the Canadian member-to-European-parent relationship and identify a concrete current operational or commercial requirement.'),
    ]
    for name,ids,reason,next_action in extra:
        refs=[]
        for sid in ids:
            s=sources[sid];response=responses[s['raw_sha256']]
            refs.append({'source_id':sid,'source_url':response['final_url'],'entry_url':s['source_url'],'raw_sha256':s['raw_sha256'],'observed_at':s['last_success_at'],'source_publication_date':settings[sid].get('reviewed_publication_date')})
        checks={k:'UNKNOWN' for k in CHECKS};links={k:[] for k in CHECKS}
        if name not in {'DeepL','Pleo'}:
            checks['canadian_relevance']='SUPPORTED';links['canadian_relevance']=[i for i in ids if settings[i]['kind']=='article']
        decisions.append(dict(id=ident('company-review-v1',name),project_id=None,company_name=name,decision='HOLD',review_date='2026-09-22',reviewer='assistant-source-review-2026-09-22',reason=reason,next_action=next_action,checks=checks,check_sources=links,evidence=refs,current_status_date=None,current_status_source_id=None,first_entry_confirmed=False,predictive_score_allowed=False,independent_holdout=False))
    # Add only source-bound facts from the accepted current-qualification proof.
    # Undated current pages may support a HOLD check but can never satisfy the
    # dated <=90-day requirement for QUALIFIED_FOR_INVESTIGATION.
    qfirst=checked_report(qz,'first');qsecond=checked_report(qz,'second')
    if qfirst['summary']!={'sources_requested':5,'sources_observed':5,'source_failures':0,'observations':5,'events':0,'raw_responses_verified':10} or qsecond['summary']!={'sources_requested':5,'sources_observed':5,'source_failures':0,'observations':5,'events':0,'raw_responses_verified':10}:
        raise ValueError('Unexpected current qualification proof summary')
    qobs={r['source_id']:r for r in qsecond['observations']}
    if set(qobs)!={'adyen-current-affiliate-20260701','ubisoft-sherbrooke-current','accenture-stcatharines-current','gd-montreal-hub-20260616','sanofi-canada-current'}:
        raise ValueError('Unexpected current qualification source set')
    qresponses=[r for r in qsecond['responses'] if 'sha256' in r]
    def current_evidence(name,sid,supported,reason,next_action,current_date=None):
        row=next(d for d in decisions if d['company_name']==name)
        o=qobs[sid]
        matches=[x for x in qresponses if x.get('final_url')==o['source_url'] and x.get('status')==200]
        if len(matches)!=1: raise ValueError('Ambiguous retained current source response: '+sid)
        response=matches[0]
        evidence={'source_id':sid,'source_url':o['source_url'],'raw_sha256':response['sha256'],
                  'observed_at':response['retrieved_at'],'source_publication_date':o['source_publication_date']}
        if any(e['source_id']==sid for e in row['evidence']): raise ValueError('Duplicate current qualification evidence')
        row['evidence'].append(evidence)
        for check in supported:
            row['checks'][check]='SUPPORTED'
            if sid not in row['check_sources'][check]: row['check_sources'][check].append(sid)
        row['review_date']='2026-09-23';row['reason']+=' '+reason;row['next_action']=next_action
        if current_date is not None:
            if o['source_publication_date']!=current_date: raise ValueError('Current-status date is not source-bound')
            row['current_status_date']=current_date;row['current_status_source_id']=sid
    current_evidence('Adyen Canada Ltd.','adyen-current-affiliate-20260701',
        ('legal_identity','corporate_group','civilian_scope','canadian_relevance','current_status'),
        'A dated Adyen legal page lists Adyen Canada Ltd. at a Canadian address among the wholly-owned Adyen affiliates used to provide payment services. Commercial source-reuse permission remains unverified.',
        'Complete source-reuse/legal-use review and identify a concrete current commercial requirement before promotion.','2026-07-01')
    current_evidence('Ubisoft','ubisoft-sherbrooke-current',
        ('civilian_scope','canadian_relevance','current_status'),
        'The current official Sherbrooke careers/location page reports more than thirty employees and active talent recruitment. The page is undated, so retrieval is not treated as a public status date.',
        'Resolve the exact Canadian legal entity/group and source-reuse terms; obtain a dated current-status source before promotion.')
    current_evidence('Accenture','accenture-stcatharines-current',
        ('civilian_scope','canadian_relevance','current_status'),
        'A current official Accenture job page says Accenture Niagara is growing and the role is onsite at the St. Catharines office. The page is undated, so retrieval is not a public status date.',
        'Resolve the exact Canadian legal operator/group and source-reuse terms; retain a dated current-status source before promotion.')
    current_evidence('Giesecke+Devrient','gd-montreal-hub-20260616',
        ('canadian_relevance','current_status'),
        'G+D’s dated issuer release reports the Montréal AI Hub launched and first projects started, while also describing security-critical domains and long-standing Canadian presence. Civilian-only scope is therefore not inferred.',
        'Refresh the hub status with evidence inside the 90-day window and resolve the Canadian legal operator, dual-use/civilian scope and source-reuse terms.','2026-06-16')
    current_evidence('Sanofi','sanofi-canada-current',
        ('civilian_scope','canadian_relevance','current_status'),
        'Sanofi’s current Canada page describes active Canadian biopharma operations and the new Toronto influenza manufacturing facility. The page is undated and does not establish an exact production-start date.',
        'Resolve the exact Canadian legal entity/group and source-reuse terms, then obtain dated evidence of production/operating status before promotion.')
    register={'schema_version':1,'status':'REVIEW_REGISTER_NOT_PREDICTIONS','decision_count':20,'decisions':decisions,'proofs':[{'artifact_id':DOC_ID,'archive_sha256':DOC_SHA},{'artifact_id':MON_ID,'archive_sha256':MON_SHA},{'artifact_id':QUAL_ID,'archive_sha256':QUAL_SHA}],'qualification_completed':False,'scope':'Documented triage decisions with partial source-bound qualification progress, not twenty qualified opportunities.'}
    if len(decisions)!=20: raise ValueError('Unexpected decision count')
    # Select an operational review roster, keeping known-history bias explicit. Exact labels
    # group repeated discovery cards only; this is never a legal-parent entity-resolution join.
    groups=defaultdict(list)
    for row in second['records']:
        if row['source_origin_triage'] in ('EU27_SOURCE_LABEL_NOT_CONTROL_PROOF','OTHER_EUROPE_SOURCE_LABEL_NOT_CONTROL_PROOF'):groups[row['company_candidate']].append(row)
    targets=[]
    def target(name,role,refs,origin=None,existing_identity=False):
        targets.append({'id':ident('operational-review-target-v1',role+':'+name),'company_label':name,'source_role':role,'origin_label':origin,'origin_is_current_control_proof':False,'source_references':refs,'existing_research_identity_review':existing_identity,'current_monitoring_qualified':False,'independent_holdout':False,'new_entry_label':False,'selection_status':'SELECTED_FOR_REVIEW_NOT_ENROLLED_MONITORING','qualification_decision_id':next((d['id'] for d in decisions if d['company_name']==name),None)})
    for name,rows in groups.items():target(name,'INVESTMENT_DISCOVERY_EXACT_LABEL',[{'source_record_id':r['source_record_id'],'source_url':r['source_url'],'raw_sha256':r['raw_sha256'],'observed_at':r['last_observed_at']} for r in rows],rows[0]['source_country_as_published'])
    dashboard=json.loads((ROOT/'ui/data/dashboard.json').read_text())
    for c in dashboard['research_cohort']:target(c['foreign_legal_name'],'KNOWN_HISTORICAL_RESEARCH_CONTROL',[{'case_id':c['id'],'source_url':e['source_url'],'claim':e['claim']} for e in c['identity_evidence']],c['ultimate_control_country'],True)
    for name,ids,_,_ in extra:target(name,'EXISTING_BOUNDED_COMPANY_SOURCE',[{'source_id':sid,'source_url':sources[sid]['source_url'],'proof_artifact_id':MON_ID} for sid in ids])
    vonage=json.loads((ROOT/'reviews/company_sources/investment-discovery-2026-09-22.json').read_text())['sources'][1]
    target(vonage['company'],'KNOWN_PRODUCT_AVAILABILITY_CALIBRATION',[{'source_id':vonage['id'],'source_url':vonage['url']}])
    for wanted in ['Sioo Wood Protection Industry Canada Inc.','Linet Canada Inc.']:
        c=next(c for c in dashboard['cases'] if c['canadian_business_name']==wanted)
        target(c['investor_name'],'KNOWN_HISTORICAL_CASE_INVESTOR',[{'case_id':c['id'],'source_url':e['source_url'],'claim':e['claim']} for e in c['evidence'] if e.get('source_url')],c['ultimate_control_country'])
    if len(targets)!=50 or len({t['id'] for t in targets})!=50:raise ValueError('Expected fifty source-local targets, never fifty qualified companies')
    cohort={'schema_version':1,'cohort_id':'operational-review-2026-09-22','selection_date':'2026-09-22','target_count':50,'identity_qualified_current_company_count':None,'operational_monitoring_qualified_count':0,'independent_holdout':False,'known_outcome_selection_bias':True,'targets':targets,'limitations':['Targets are source-local labels, not fifty independently qualified legal entities. Repeated exact discovery labels retain every underlying card.','Known historical companies and controls are deliberately included for operational review; this is not a prospective independent predictive holdout.','The existing eight-source monitor is unchanged. Roster selection does not enroll fifty company sources or establish fourteen days of monitoring.','Source-country labels, corporate control, legal identity, civilian suitability and current status require separate review.']}
    return catalog,register,cohort

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--documentary-proof',required=True);ap.add_argument('--monitor-proof',required=True);ap.add_argument('--qualification-proof',required=True);ap.add_argument('--check',action='store_true');args=ap.parse_args()
    outputs=build(args.documentary_proof,args.monitor_proof,args.qualification_proof)
    for relative,value in zip(('ui/data/reviewed-evidence.json','ui/data/company-reviews.json','reviews/pilot/operational-cohort-2026-09-22.json'),outputs):
        path=ROOT/relative;encoded=json.dumps(value,indent=2,ensure_ascii=False)+'\n'
        if args.check:
            if path.read_text()!=encoded:raise ValueError('Non-deterministic or mismatched release data: '+relative)
        else:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(encoded)
    print(json.dumps({'reviewed_projects':15,'documented_triage_decisions':20,'source_local_review_targets':50,'current_qualification_sources':5,'qualified_for_investigation':0,'fifty_company_monitoring_qualification_complete':False,'predictive_validation_complete':False}))
if __name__=='__main__':main()
