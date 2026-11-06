// No storage, network scheduling or source mutation. fetch is injected for offline tests.
export const STATUSES = ['TRIAGE', 'ACTIVE', 'HOLD', 'DONE'];
export const noteLength = value => Array.from(value).length;
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const validDate = value => value === null || (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value));
const validSummary = item => object(item) && typeof item.work_item_id === 'string' && /^[a-f0-9]{64}$/.test(item.work_item_id)
  && ['source_id','record_id','title'].every(key=>typeof item[key] === 'string')
  && STATUSES.includes(item.status) && validDate(item.due_date) && typeof item.needs_review === 'boolean'
  && Number.isSafeInteger(item.revision) && item.revision >= 1;
const validDetail = item => validSummary(item) && typeof item.notes === 'string' && noteLength(item.notes) <= 16000;
const validList = data => object(data) && Array.isArray(data.items) && data.items.every(validSummary)
  && ['page','total','page_size'].every(key=>Number.isSafeInteger(data[key]))
  && data.page >= 1 && data.total >= 0 && data.page_size >= 1 && data.page_size <= 100
  && data.items.length <= data.page_size && data.items.length <= data.total;
const draftOf = item => ({status:item.status, notes:item.notes, due_date:item.due_date, needs_review:item.needs_review});
export class Workbench {
  constructor(fetcher, changed = () => {}) {
    this.fetcher=fetcher; this.changed=changed; this.sequence=0; this.listSequence=0;
    this.state={id:null,item:null,draft:null,dirty:false,pending:false,loading:false,uncertain:false,blocked:false,message:'',list:{items:[],page:1,total:0,page_size:25},filters:{source:'',status:'',page:1},listLoading:false,listError:''};
  }
  emit(){this.changed(this.state);}
  async request(path, options){
    const abort=new AbortController();const timeout=setTimeout(()=>abort.abort(),30000);
    try{const r=await this.fetcher(path,{credentials:'omit',cache:'no-store',redirect:'error',signal:abort.signal,...options});
      if(!r.ok){const e=new Error('Request rejected');e.status=r.status;throw e;}return await r.json();
    }finally{clearTimeout(timeout);}
  }
  async list(filters={}){
    const token=++this.listSequence;
    this.state.filters={...this.state.filters,...filters};this.state.listLoading=true;this.state.listError='';this.emit();
    try {const data=await this.request('/api/items?'+new URLSearchParams(this.state.filters));if(token!==this.listSequence)return;if(!validList(data))throw new Error('Invalid list response');this.state.list=data;}
    catch {if(token!==this.listSequence)return;this.state.listError='Work items could not be loaded. Retry the list.';}
    this.state.listLoading=false;this.emit();
  }
  async navigate(id,{discard=false}={}) {
    if(id!==null && !/^[a-f0-9]{64}$/.test(id))return false;
    if(this.state.pending){this.state.message='Save is still pending. Stay here until its result is known.';this.emit();return false;}
    if((this.state.dirty||this.state.uncertain)&&!discard){this.state.message='Unsaved draft: choose Keep editing or Discard draft and continue.';this.emit();return false;}
    const token=++this.sequence;
    Object.assign(this.state,{id,item:null,draft:null,dirty:false,loading:!!id,blocked:false,uncertain:false,message:''});this.emit();
    if(!id)return true;
    try{const {item}=await this.request('/api/items/'+id);if(token!==this.sequence)return false;
      if(!validDetail(item)||item.work_item_id!==id)throw new Error('Invalid detail response');
      this.state.item=item;this.state.draft=draftOf(item);
    }catch{if(token!==this.sequence)return false;this.state.message='Detail could not be loaded. Retry without changing records.';}
    this.state.loading=false;this.emit();return true;
  }
  edit(field,value){if(!this.state.draft||this.state.pending||!Object.hasOwn(this.state.draft,field))return;
    this.state.draft={...this.state.draft,[field]:value};this.state.dirty=JSON.stringify(this.state.draft)!==JSON.stringify(draftOf(this.state.item));this.emit();}
  async save(){
    const s=this.state;if(!s.item||!s.dirty||s.pending||s.blocked)return false;
    const d=s.draft;
    if(!STATUSES.includes(d.status)||typeof d.notes!=='string'||noteLength(d.notes)>16000||typeof d.needs_review!=='boolean'||!(d.due_date===null||/^\d{4}-\d{2}-\d{2}$/.test(d.due_date))){s.message='Check the status, date and notes (maximum 16,000 characters). Draft retained.';this.emit();return false;}
    s.pending=true;s.message='Saving…';this.emit();
    try{
      const {item}=await this.request('/api/items/'+s.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({expected_revision:s.item.revision,...d})});
      if(!validDetail(item)||item.work_item_id!==s.id||item.revision!==s.item.revision+1||Object.keys(d).some(key=>item[key]!==d[key]))throw new Error('Unconfirmed result');
      s.item=item;s.draft=draftOf(item);s.dirty=false;s.message='Saved to the private foundation.';
      this.list();
    }catch(e){
      if(e.status===409){s.blocked=true;s.message='Another edit was saved first. Your draft is retained. Copy it if needed, then explicitly reload the latest record before editing again.';}
      else if(e.status>=400&&e.status<500){s.message='Save was rejected. Check your fields and retry. Draft retained.';}
      else {s.uncertain=true;s.blocked=true;s.message='Save result unknown. The server may have saved it. Your draft is retained; do not retry blindly. Copy it if needed, then reload to check the persisted record.';}
    }
    s.pending=false;this.emit();return !s.dirty;
  }
}
