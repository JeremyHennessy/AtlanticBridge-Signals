"""Apply accepted source evidence to the two existing project-local decisions.

Never promote a different facility's operating evidence into the original case.
No automatic legal-parent joins, source permissions, alerts or scores.
"""
from copy import deepcopy
from pathlib import Path
import json

PROOF_ID=10729682735
PROOF_SHA='39892597bcdf03f6ba7e093ece34c7618f0dff8450d8c77c30951745b1ff2064'
SOURCE_IDS={
 'cellcentric-contact-current','cellcentric-home-current','cellcentric-supplier-current',
 'cellcentric-ised-importer-current','cellcentric-legal-current','roquette-locations-current',
 'roquette-job-portage-20260904','roquette-legal-current','cid-open-data-licence-metadata'}


def apply(outputs, proof_path, archive, checked_report):
    catalog, register, cohort=deepcopy(outputs)
    z=archive(proof_path,PROOF_SHA)
    reports=[checked_report(z,s) for s in ('first','second')]
    expected={'sources_requested':9,'sources_observed':9,'source_failures':0,'observations':9,'events':0,'raw_responses_verified':13}
    for r in reports:
        if r['summary']!=expected or r['events']: raise ValueError('Unaccepted qualification-two capture')
        ids=[o['source_id'] for o in r['observations']]
        if len(ids)!=len(set(ids)) or set(ids)!=SOURCE_IDS: raise ValueError('Wrong or duplicated source set')
    a={o['source_id']:o for o in reports[0]['observations']}
    b={o['source_id']:o for o in reports[1]['observations']}
    if a!=b: raise ValueError('Captures do not reproduce identical reviewed source observations')
    responses=reports[1]['responses']
    if register.get('decision_count')!=20: raise ValueError('Unexpected decision baseline')
    original=json.dumps(register['decisions'],sort_keys=True)
    def row(name):
        matches=[r for r in register['decisions'] if r['company_name']==name]
        if len(matches)!=1 or matches[0]['decision']!='HOLD': raise ValueError('Decision changed; explicit re-review required')
        return matches[0]
    def attach(r, sid):
        o=b[sid]
        found=[x for x in responses if x.get('final_url')==o['source_url'] and x.get('status')==200 and 'sha256' in x]
        if len(found)!=1: raise ValueError('Ambiguous response binding')
        if any(e['source_id']==sid for e in r['evidence']): raise ValueError('Evidence already integrated')
        x=found[0]
        r['evidence'].append(dict(source_id=sid,source_url=o['source_url'],raw_sha256=x['sha256'],observed_at=x['retrieved_at'],source_publication_date=o['source_publication_date']))
    def check(r, key, status, ids):
        if not set(ids)<=set(e['source_id'] for e in r['evidence']): raise ValueError('Unsupported source binding')
        r['checks'][key]=status;r['check_sources'][key]=ids
    c=row('Cellcentric')
    for sid in ('cellcentric-contact-current','cellcentric-home-current','cellcentric-supplier-current','cellcentric-ised-importer-current','cellcentric-legal-current','cid-open-data-licence-metadata'):attach(c,sid)
    check(c,'legal_identity','SUPPORTED',['cellcentric-contact-current','cellcentric-ised-importer-current'])
    check(c,'civilian_scope','SUPPORTED',['cellcentric-home-current','cellcentric-supplier-current'])
    check(c,'current_status','SUPPORTED',['cellcentric-contact-current','cellcentric-home-current'])
    # Founding ownership and present Canadian presence are distinct review questions.
    check(c,'corporate_group','UNKNOWN',['cellcentric-home-current'])
    check(c,'source_reuse','UNKNOWN',['cellcentric-legal-current','cid-open-data-licence-metadata'])
    c['review_date']='2026-09-23'
    c['current_status_date']=None;c['current_status_source_id']=None
    c['reason']='The 2022 Burnaby record remains an expansion/relocation history, not first Canadian entry. The current official contact page names cellcentric Fuel Cell Canada Inc.; the ISED table independently matches its Burnaby name and postal locality for importer year 2024. Current corporate pages describe a Burnaby engineering site and civilian heavy-duty fuel-cell applications. The supplier enquiry route is company-wide, not proof of a Burnaby purchase or contract. These pages are undated. Founding ownership does not settle later shareholder changes. The separately captured 2023 CID dataset licence does not establish rights for the 2024 table or corporate pages. Current group/control and intended source reuse remain unresolved.'
    c['next_action']='Review the company-wide supplier enquiry route for relevant civilian fuel-cell work, then confirm whether any requirement serves Burnaby. Verify shareholder changes and permission for the intended source use; retain dated Canadian-site evidence before qualification.'
    r=row('Roquette')
    for sid in ('roquette-locations-current','roquette-job-portage-20260904','roquette-legal-current'):attach(r,sid)
    # Do not attach Portage's legal operator/current activity to the Winnipeg R&D project.
    check(r,'source_reuse','CONTRADICTED',['roquette-legal-current'])
    r['review_date']='2026-09-23'
    r['reason']='The original agency source supports a Winnipeg-datelined collaborative R&D project; it does not establish a separate Winnipeg R&D facility. The newly reviewed corporate location and September 4, 2026 hiring sources concern Roquette Canada Ltd. at Portage la Prairie, a different location and activity. They cannot verify the original R&D project operator or current status. The corporate legal notice states prior-approval restrictions for republication and hyperlinks; no permission for the intended reuse has been established. The corporate-source reuse check is therefore contradicted, not silently approved. The original independent agency evidence remains retained.'
    r['next_action']='Obtain current, project-specific Winnipeg R&D evidence from a permitted primary source. Treat the Portage plant and its engineering vacancy separately; do not transfer their date, operator or activity to this case. Resolve the corporate source-use restrictions before publication or promotion.'
    r['current_status_date']=None;r['current_status_source_id']=None
    if r['checks']['current_status']!='UNKNOWN' or r['checks']['legal_identity']!='UNKNOWN':raise ValueError('Wrong-location evidence cannot clear Winnipeg checks')
    if not all(d['decision']=='HOLD' for d in register['decisions']):raise ValueError('No qualification promotion authorised by this proof')
    register['proofs'].append({'artifact_id':PROOF_ID,'archive_sha256':PROOF_SHA})
    register['scope']='Twenty project-local review decisions with source-bound partial qualification. No fully qualified opportunities; different facilities, source permissions and ownership changes remain separate.'
    if original==json.dumps(register['decisions'],sort_keys=True):raise ValueError('No qualification progress applied')
    return catalog,register,cohort
