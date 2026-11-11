import {Workbench, noteLength} from './controller.js';
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;};
const display=value=>value===null||value===undefined||value===''?'Not recorded':typeof value==='object'?JSON.stringify(value,null,2):String(value);
function facts(target,values){target.replaceChildren();const dl=node('dl');for(const [k,v] of values){dl.append(node('dt',k),node('dd',display(v)));}target.append(dl);}
let decision=null,shownItem=null,previewPage=1,previewToken=0;
const model=new Workbench(window.fetch.bind(window),render);
function render(s){
  $('list-message').textContent=s.listLoading?'Loading work items…':s.listError||`${s.list.total} work items`;
  $('items').replaceChildren();
  for(const item of s.list.items){const b=node('button',undefined,'item');b.type='button';b.setAttribute('aria-pressed',String(item.work_item_id===s.id));b.append(node('strong',item.title||item.record_id),node('span',`${item.source_id} · ${item.status}`));b.addEventListener('click',()=>go(item.work_item_id));$('items').append(b);}
  if(!s.list.items.length&&!s.listLoading)$('items').append(node('p','No records in this view. No sample records are created.','muted'));
  $('page').textContent=`Page ${s.list.page}`;$('previous').disabled=s.listLoading||s.list.page<=1;$('next').disabled=s.listLoading||s.list.page*s.list.page_size>=s.list.total;
  $('detail-message').textContent=s.message|| (s.loading?'Loading detail…':'');$('close').hidden=!s.id;
  $('detail-title').textContent=s.item?s.item.title||s.item.record_id:s.loading?'Loading record…':s.id?'Record unavailable':'Select a work item';
  $('editor').hidden=!s.item;
  if(shownItem!==s.item){shownItem=s.item;const i=s.item;
    if(i)facts($('facts'),[['Source',i.source_id],['Record identity',i.record_id],['Origin / fixture context',i.origin],['Evidence disposition',i.disposition],['Lead eligible',i.lead_eligible],['Current version first imported at (local)',i.imported_at],['Record last imported at (local)',i.last_imported_at],['Original publication date',i.published_date],['Original event date',i.event_date],['Source facts (read only)',i.facts],['Source URL (text only)',i.source_url],['Coverage',i.coverage],['Attribution',i.attribution],['License',i.license_name],['License URL (text only)',i.license_url],['Analyst revision',i.revision]]);else $('facts').replaceChildren();
  }
  if(s.draft){for(const [id,value] of [['edit-status',s.draft.status],['due',s.draft.due_date||''],['notes',s.draft.notes]])if($(id).value!==value)$(id).value=value;$('review').checked=s.draft.needs_review;$('count').textContent=`${noteLength(s.draft.notes)} / 16,000 characters${s.dirty?' · Unsaved changes':''}`;}
  $('fields').disabled=s.pending;$('save').disabled=!s.dirty||s.pending||s.blocked;$('save').textContent=s.pending?'Saving…':'Save review';$('reload').disabled=s.pending;$('close').disabled=s.pending;
}
function route(id){return id?'#item='+id:'#';}
async function go(id,{discard=false,historyChange=false}={}){
  if(model.state.pending){await model.navigate(id);if(historyChange)history.replaceState(null,'',route(model.state.id));return;}
  if((model.state.dirty||model.state.uncertain)&&!discard){decision={id,historyChange};$('decision').hidden=false;$('decision-text').textContent=model.state.uncertain?'Save result is unknown. Copy your draft if needed. Discard it and read the current persisted record?':'Discard this draft and continue? Copy any notes you need first.';$('keep').focus();if(historyChange)history.replaceState(null,'',route(model.state.id));return;}
  $('decision').hidden=true;decision=null;
  const loading=model.navigate(id,{discard});
  if(!historyChange&&location.hash!==route(id))history.pushState(null,'',route(id));
  await loading;
  if(model.state.id===id)$('detail-title').focus();
}
$('keep').addEventListener('click',()=>{decision=null;$('decision').hidden=true;$('notes').focus();});
$('discard').addEventListener('click',()=>{if(decision){const d=decision;go(d.id,{discard:true,historyChange:false});}});
$('close').addEventListener('click',()=>go(null));$('reload').addEventListener('click',()=>go(model.state.id));
$('editor').addEventListener('submit',e=>{e.preventDefault();model.save();});
$('edit-status').addEventListener('change',e=>model.edit('status',e.target.value));$('due').addEventListener('change',e=>model.edit('due_date',e.target.value||null));$('review').addEventListener('change',e=>model.edit('needs_review',e.target.checked));$('notes').addEventListener('input',e=>model.edit('notes',e.target.value));
for(const id of ['source','status'])$(id).addEventListener('change',()=>model.list({source:$('source').value,status:$('status').value,page:1}));
$('refresh').addEventListener('click',()=>model.list());$('previous').addEventListener('click',()=>model.list({page:model.state.list.page-1}));$('next').addEventListener('click',()=>model.list({page:model.state.list.page+1}));
const hashId=()=>/^#item=([a-f0-9]{64})$/.exec(location.hash)?.[1]||null;
window.addEventListener('popstate',()=>go(hashId(),{historyChange:true}));
window.addEventListener('beforeunload',e=>{if(model.state.dirty||model.state.pending||model.state.uncertain){e.preventDefault();e.returnValue='';}});
async function health(){try{const {sources}=await model.request('/api/sources');$('health').replaceChildren();for(const s of sources){const section=node('article',undefined,'health-row');section.append(node('h3',s.source_id));const content=node('div');facts(content,[['State',s.state],['Last successful import',s.last_success_at],['Last attempt',s.last_attempt_at],['Failures',s.failure_count],['Coverage',s.coverage],['Attribution',s.attribution],['License',s.license_name],['License URL (text only)',s.license_url]]);section.append(content);$('health').append(section);const option=node('option',s.source_id);option.value=s.source_id;$('source').append(option);}if(!sources.length)$('health').textContent='No registered sources.';}catch{$('health').textContent='Source health could not be loaded. Reload this page to retry.';}}
async function previews(page){const token=++previewToken;$('preview-previous').disabled=true;$('preview-next').disabled=true;$('previews').textContent='Loading local previews…';try{const result=await model.request('/api/previews?page='+page);if(token!==previewToken)return;previewPage=result.page;$('previews').replaceChildren();for(const p of result.previews){const section=node('article',undefined,'preview-row');facts(section,Object.entries(p));$('previews').append(section);}if(!result.previews.length)$('previews').textContent=result.configured?'No staged historical previews.':'No existing staging journal was configured.';$('preview-page').textContent=`Page ${result.page}`;$('preview-previous').disabled=result.page<=1;$('preview-next').disabled=result.page*result.page_size>=result.total;}catch{if(token!==previewToken)return;$('previews').textContent='Historical previews could not be loaded. Reload this page to retry.';}}
$('preview-previous').addEventListener('click',()=>previews(previewPage-1));$('preview-next').addEventListener('click',()=>previews(previewPage+1));
model.list();health();previews(1);go(hashId(),{historyChange:true});
