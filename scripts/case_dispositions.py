"""Five evidence-bound case dispositions, preserving historical dossier objects.

A completed disposition is not a qualified opportunity, legal-use approval or
prediction. PDF fiscal periods never become invented publication days.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

SIX_ID=10718724645
SIX_SHA='46f6e0853b6848cc10d5982e54bebeac2bf810e6e3ede19062b470e6c39a75a6'
PDF_ID=10724109813
PDF_SHA='6f5f5b169681f0bbc0b01d116f97cb3ee0a254385619f094cd101d8c98c415cc'
PDF_RAW='bf156e3ae322bd12803a93a72c04f09fc35799393601de8c638556cc319a6cea'

def apply(outputs, six_path, pdf_path, archive, checked_report):
    catalog,register,cohort=deepcopy(outputs)
    six=archive(six_path,SIX_SHA);pdf=archive(pdf_path,PDF_SHA)
    for stage in ('first','second'):checked_report(six,stage)
    source_id='sanofi-flu-inauguration-20260916'
    project=next(p for p in catalog['projects'] if p['company_name']=='Sanofi')
    src=next(e for e in project['evidence'] if e['source_id']==source_id)
    raw=six.read('second/raw/'+src['raw_sha256']+'.bin')
    if hashlib.sha256(raw).hexdigest()!=src['raw_sha256']:raise ValueError('Sanofi raw provenance mismatch')
    from atlanticbridge.company_sources import text
    plain=text(raw.decode('utf-8'))
    for anchor in ('Charles Best Building','Sept. 16, 2026','pending regulatory approval','will begin production in early 2027'):
        if anchor not in plain:raise ValueError('Retained inauguration source lacks reviewed fact')
    report=json.loads(pdf.read('report.json'))
    if report.get('raw_sha256')!=PDF_RAW or report.get('current_status_claim_allowed') is not False:raise ValueError('Unexpected PDF capture contract')
    for response in report['responses']:
        body=pdf.read('raw/'+response['sha256']+'.bin')
        if hashlib.sha256(body).hexdigest()!=response['sha256'] or response['status']!=200:raise ValueError('PDF response mismatch')
    document=pdf.read('raw/'+PDF_RAW+'.bin')
    if len(document)!=12323559 or not document.startswith(b'%PDF-'):raise ValueError('Unexpected PDF bytes')
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'reviewed.pdf';path.write_bytes(document)
        extracted=subprocess.check_output(['pdftotext','-f','52','-l','52','-enc','UTF-8',str(path),'-'],timeout=30).decode('utf-8')
    page=' '.join(extracted.split())
    for anchor in ('Nature Energy withdrew from this project in fiscal year 2025','ÉDI acquired the entire Farnham site','ensuring the continuity thereof','fiscal year 2028'):
        if anchor not in page:raise ValueError('PDF page 52 does not support the reviewed amendment')
    pdf_response=next(r for r in report['responses'] if r.get('sha256')==PDF_RAW)
    pdf_evidence=dict(source_id='energir-farnham-fy2025-pdf-page52',source_url=report['source_url'],raw_sha256=PDF_RAW,
        observed_at=pdf_response['retrieved_at'],source_publication_date=None,page=52,event_period='Fiscal year 2025',publication_precision='UNKNOWN')
    rows={r['company_name']:r for r in register['decisions']}
    sanofi=rows['Sanofi'];nature=rows['Nature Energy']
    sanofi['current_status_date']='2026-09-16';sanofi['current_status_source_id']=source_id
    sanofi['check_sources']['current_status']=[source_id];sanofi['checks']['current_status']='SUPPORTED'
    sanofi['reason']='The dated September 16, 2026 issuer release inaugurates the Toronto Charles Best influenza building and calls the facility operational, but explicitly plans vaccine production for early 2027 subject to regulatory approval. This is a material expansion of an existing Canadian campus, not first entry or verified vaccine production. Exact facility operator/group and intended source reuse remain unresolved.'
    sanofi['next_action']='Check regulatory approval and an actual production-start announcement for the Charles Best influenza building; do not substitute activity at the separate diphtheria/tetanus/pertussis facility. Confirm the facility legal operator and intended source-use terms before qualification.'
    sanofi['review_date']='2026-09-23'
    if any(e['source_id']==pdf_evidence['source_id'] for e in nature['evidence']):raise ValueError('PDF amendment already applied')
    nature['evidence'].append(pdf_evidence)
    nature['reason']='The 2022 Nature Energy Farnham plan and 2023 Shell acquisition history remain retained. Énergir’s 2025 climate report, page 52, reports Nature Energy’s withdrawal in fiscal year 2025 and ÉDI’s acquisition of the Farnham site to continue development. The foreign partner’s exit is not cancellation of the whole project. The report provides no verified exact publication day here; its planned construction/deployment periods do not establish current operations or a new Nature Energy entry.'
    nature['next_action']='Do not treat Farnham as an active Nature Energy entry opportunity. Obtain a recent, permitted ÉDI project update before evaluating continuing development under its operator. Keep the fiscal-year withdrawal amendment separate from any future operational or ownership event.'
    nature['review_date']='2026-09-23';nature['checks']['current_status']='UNKNOWN';nature['check_sources']['current_status']=[pdf_evidence['source_id']]
    nature['current_status_date']=None;nature['current_status_source_id']=None
    for aid,sha in ((SIX_ID,SIX_SHA),(PDF_ID,PDF_SHA)):
        if any(p['artifact_id']==aid for p in register['proofs']):raise ValueError('Proof already integrated')
        register['proofs'].append({'artifact_id':aid,'archive_sha256':sha})
    specs=[
        ('Adyen Canada Ltd.','MEMBERSHIP_NOT_ENTRY','Membership documented; commercial requirement still to establish',
         'The retained July 2026 membership and affiliate evidence support a Canadian payment-network relationship and the named Canadian affiliate. They do not establish first Canadian entry, a new office, or a specific open commercial requirement.',
         'Identify a dated, concrete Canadian expansion or partnership requirement and resolve the intended source-use review before promotion.',
         'Canada / payment-network participation','Membership is a Canadian relationship, not a recommended office location or a market-fit score.',
         ['adyen-payments-membership','adyen-current-affiliate-20260701'],'2026-07-14','Dated membership document'),
        ('Cellcentric','PRESENCE_WITH_UNRESOLVED_DEMAND','Burnaby presence supported; supplier demand remains unconfirmed',
         'Retained company and ISED evidence identify the Burnaby company/locality and current engineering context. The supplier-inquiry route is company-wide, not a Burnaby contract. Founding ownership must not be substituted for a current shareholder review.',
         rows['Cellcentric']['next_action'],'Burnaby, British Columbia','Site-specific engineering context only. A wider hydrogen-market or supplier-fit conclusion has not been scored.',
         ['cellcentric-contact-current','cellcentric-home-current','cellcentric-supplier-current','cellcentric-ised-importer-current'],None,'Undated current pages; observation dates remain separate'),
        ('Roquette','DIFFERENT_PROJECT_EVIDENCE','Portage evidence does not qualify the Winnipeg R&D case',
         'The September 2026 plant vacancy and Roquette Canada location concern Portage la Prairie. The original record concerns a Winnipeg-datelined R&D collaboration, not an independently established Winnipeg facility. These are separate activities; the newer date and plant operator do not transfer to the R&D case.',
         rows['Roquette']['next_action'],'Winnipeg R&D context / separate Portage la Prairie plant','Manitoba activity is documented, but this is not a comparison or recommendation between the two locations.',
         ['roquette-rd-20200619','roquette-locations-current','roquette-job-portage-20260904','roquette-legal-current'],'2026-09-04','Date belongs to the separate Portage vacancy'),
        ('Sanofi','INAUGURATED_PRODUCTION_PENDING','Influenza facility inaugurated; production remains conditional',
         sanofi['reason'],sanofi['next_action'],'Toronto, Ontario / Charles Best influenza building','Expansion of an existing biomanufacturing campus; not first entry or a forecast of regional demand.',
         [source_id],'2026-09-16','Inauguration report; prospective production is not actual production'),
        ('Nature Energy','PARTNER_WITHDRAWAL_PROJECT_CONTINUATION','Foreign partner withdrew; the project continued under ÉDI',
         'The retained Énergir report states that Nature Energy withdrew in fiscal 2025 and that ÉDI acquired the Farnham site to continue the project. Development and planned deployment are not verified operation. This corrective history must not be presented as an active new Nature Energy entry.',
         nature['next_action'],'Farnham, Québec / RNG project','Continuing project development must be evaluated under the correct operator, separately from the withdrawn foreign partner.',
         [pdf_evidence['source_id']],None,'Fiscal year 2025 withdrawal; exact publication day unknown'),
    ]
    briefs=[]
    for name,kind,title,summary,action,location,fit,ids,published,period in specs:
        r=rows[name];refs={e['source_id']:e for e in r['evidence']}
        if not set(ids)<=refs.keys():raise ValueError('Case disposition lacks bound source')
        briefs.append(dict(id=r['id'],company_id=r['project_id'] or r['id'],company_name=name,disposition=kind,title=title,
            reviewed_on='2026-09-23',summary=summary,next_action=action,documented_location=location,market_context=fit,
            latest_source_publication_date=published,event_time_basis=period,evidence=[deepcopy(refs[i]) for i in ids],
            remaining_checks=[k for k,v in r['checks'].items() if v!='SUPPORTED'],source_use_state=r['checks']['source_reuse'],
            qualified=False,public_alert_allowed=False,predictive_score_allowed=False,market_fit_score=None))
    if not all(r['decision']=='HOLD' for r in register['decisions']):raise ValueError('No opportunity promotions authorised by these dispositions')
    brief_data=dict(schema_version=1,status='REVIEWED_DISPOSITIONS_NOT_QUALIFIED_LEADS',brief_count=5,briefs=briefs,
        proofs=[{'artifact_id':SIX_ID,'archive_sha256':SIX_SHA},{'artifact_id':PDF_ID,'archive_sha256':PDF_SHA}],
        scope='Five source-bound case dispositions; no independent customer review, legal-use permission, quantified market-fit or predictive validation.')
    return catalog,register,cohort,brief_data
