// Same-origin company API only. No browser persistence, source access or delivery.
export const STATUSES = {new:'To review',researching:'Researching',contacted:'Contacted',follow_up:'Follow up',closed:'Closed'};
const object=v=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const id=v=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const text=(v,n)=>typeof v==='string'&&v.length<=n&&!Array.from(v).some(c=>c.length===1&&c.charCodeAt(0)>=0xD800&&c.charCodeAt(0)<=0xDFFF);
const date=v=>v===''||(typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&Number.isFinite(Date.parse(v))&&new Date(v).toISOString().slice(0,10)===v);
const instant=v=>typeof v==='string'&&v.length<=40&&Number.isFinite(Date.parse(v));
const validSummary=c=>object(c)&&id(c.id)&&text(c.company_name,1000)&&text(c.country,100)&&typeof c.status==='string'&&Object.hasOwn(STATUSES,c.status)
  &&date(c.due_date)&&Number.isSafeInteger(c.revision)&&c.revision>=1;
const validDetail=c=>validSummary(c)&&text(c.notes,4000)&&text(c.next_action,500)&&instant(c.updated_at)
  &&text(c.source_url,2000)&&(c.source_url===''||/^https?:\/\//i.test(c.source_url))
  &&(c.source_sha256===''||id(c.source_sha256))&&(c.snapshot_observed_at===''||instant(c.snapshot_observed_at))
  &&date(c.latest_public_date)&&c.evidence_verified===false&&c.identity_mapping_performed===false;
const validList=d=>object(d)&&d.mode==='PRIVATE_COMPANY_ANALYST_STATE_ONLY'&&d.evidence_verified===false&&d.identity_mapping_performed===false
  &&Array.isArray(d.companies)&&d.companies.every(validSummary)&&new Set(d.companies.map(c=>c.id)).size===d.companies.length
  &&['page','total','page_size'].every(k=>Number.isSafeInteger(d[k]))&&d.page>=1&&d.total>=0&&d.total<=500
  &&d.page_size===25&&d.companies.length<=d.page_size&&d.companies.length<=d.total;
const draftOf=c=>({status:c.status,notes:c.notes,next_action:c.next_action,due_date:c.due_date});
const immutable=['id','company_name','country','source_url','source_sha256','snapshot_observed_at','latest_public_date'];
export class CompanyWorkbench {
  constructor(fetcher,changed=()=>{}){this.fetcher=fetcher;this.changed=changed;this.sequence=0;this.listSequence=0;
    this.state={id:null,company:null,draft:null,dirty:false,pending:false,loading:false,uncertain:false,blocked:false,message:'',
      list:{companies:[],page:1,total:0,page_size:25},filters:{status:'',page:1},listLoading:false,listError:''};}
  emit(){this.changed(this.state);}
  async request(path,options){const abort=new AbortController();const timeout=setTimeout(()=>abort.abort(),30000);
    try{const r=await this.fetcher(path,{credentials:'omit',cache:'no-store',redirect:'error',signal:abort.signal,...options});
      if(!r.ok){const e=new Error('Request rejected');e.status=r.status;throw e;}return await r.json();
    }finally{clearTimeout(timeout);}}
  async list(filters={}){const token=++this.listSequence;this.state.filters={...this.state.filters,...filters};this.state.listLoading=true;this.state.listError='';this.emit();
    try{const d=await this.request('/api/companies?'+new URLSearchParams(this.state.filters));if(token!==this.listSequence)return;
      if(!validList(d)||d.page!==Number(this.state.filters.page))throw new Error('Invalid company list');this.state.list=d;
    }catch{if(token!==this.listSequence)return;this.state.listError='Company worklist could not be loaded. Retry the list.';}
    this.state.listLoading=false;this.emit();}
  async navigate(companyId,{discard=false}={}){
    if(companyId!==null&&!id(companyId))return false;
    if(this.state.pending){this.state.message='Save is still pending. Stay here until its result is known.';this.emit();return false;}
    if((this.state.dirty||this.state.uncertain)&&!discard){this.state.message='Unsaved draft: choose Keep editing or Discard draft and continue.';this.emit();return false;}
    const token=++this.sequence;
    Object.assign(this.state,{id:companyId,company:null,draft:null,dirty:false,loading:!!companyId,blocked:false,uncertain:false,message:''});this.emit();
    if(!companyId)return true;
    try{const {company}=await this.request('/api/companies/'+companyId);if(token!==this.sequence)return false;
      if(!validDetail(company)||company.id!==companyId)throw new Error('Invalid company response');this.state.company=company;this.state.draft=draftOf(company);
    }catch{if(token!==this.sequence)return false;this.state.message='Company could not be loaded. Retry without changing records.';}
    this.state.loading=false;this.emit();return true;}
  edit(field,value){const s=this.state;if(!s.draft||s.pending||!Object.hasOwn(s.draft,field))return;
    s.draft={...s.draft,[field]:value};s.dirty=JSON.stringify(s.draft)!==JSON.stringify(draftOf(s.company));this.emit();}
  async save(){const s=this.state;if(!s.company||!s.dirty||s.pending||s.blocked)return false;const d={...s.draft};
    if(typeof d.status!=='string'||!Object.hasOwn(STATUSES,d.status)||!text(d.notes,4000)||!text(d.next_action,500)||!date(d.due_date)){
      s.message='Check status, date, notes (4,000 characters) and next action (500 characters). Draft retained.';this.emit();return false;}
    s.pending=true;s.message='Saving…';this.emit();
    try{const {company}=await this.request('/api/companies/'+s.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:s.company.revision,...d})});
      if(!validDetail(company)||company.id!==s.id||company.revision!==s.company.revision+1||Object.keys(d).some(k=>company[k]!==d[k])
        ||immutable.some(k=>company[k]!==s.company[k]))throw new Error('Unconfirmed result');
      s.company=company;s.draft=draftOf(company);s.dirty=false;s.message='Saved to the private company workspace.';this.list();
    }catch(e){if(e.status===409){s.blocked=true;s.message='Another edit was saved first or the company changed. Your draft is retained. Copy it if needed, then explicitly reload before editing again.';}
      else if(e.status>=400&&e.status<500){s.message='Save was rejected. Check your fields and retry. Draft retained.';}
      else{s.uncertain=true;s.blocked=true;s.message='Save result unknown. It may have committed. Your draft is retained; do not retry blindly. Copy it if needed, then reload to check the persisted revision.';}}
    s.pending=false;this.emit();return !s.dirty;}
}
