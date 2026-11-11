import {CompanyWorkbench, STATUSES} from './controller.js';
const $=id=>document.getElementById(id);
const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=String(text);if(cls)e.className=cls;return e;};
const display=v=>v===null||v===undefined||v===''?'Not recorded':String(v);
function facts(target,values){const dl=node('dl');for(const [key,value] of values)dl.append(node('dt',key),node('dd',display(value)));target.replaceChildren(dl);}
let decision=null,shownCompany=null;
const model=new CompanyWorkbench(window.fetch.bind(window),render);
function render(s){
  $('list-message').textContent=s.listLoading?'Loading companies…':s.listError||`${s.list.total} companies`;
  $('companies').replaceChildren();
  for(const c of s.list.companies){const button=node('button',undefined,'item');button.type='button';button.setAttribute('aria-pressed',String(c.id===s.id));
    button.append(node('strong',c.company_name||'Unnamed company'),node('span',`${c.country||'Country not recorded'} · ${STATUSES[c.status]}`));button.addEventListener('click',()=>go(c.id));$('companies').append(button);}
  if(!s.list.companies.length&&!s.listLoading)$('companies').append(node('p','No companies in this view. No sample or source records are created.','muted'));
  $('page').textContent=`Page ${s.list.page}`;$('previous').disabled=s.listLoading||s.list.page<=1;$('next').disabled=s.listLoading||s.list.page*s.list.page_size>=s.list.total;
  $('detail-message').textContent=s.message||(s.loading?'Loading company…':'');$('close').hidden=!s.id;
  $('detail-title').textContent=s.company?s.company.company_name||'Unnamed company':s.loading?'Loading company…':s.id?'Company unavailable':'Select a company';
  $('editor').hidden=!s.company;
  if(shownCompany!==s.company){shownCompany=s.company;const c=s.company;
    if(c)facts($('facts'),[['Exact company identity',c.id],['Country (imported)',c.country],['Last analyst update',c.updated_at],['Analyst revision',c.revision],
      ['Declared source URL (text only)',c.source_url],['Declared source hash',c.source_sha256],['Imported source observation clock',c.snapshot_observed_at],
      ['Imported latest publication date',c.latest_public_date],['Source evidence independently verified',c.evidence_verified],['Identity mapping performed',c.identity_mapping_performed]]);
    else $('facts').replaceChildren();}
  if(s.draft){for(const [key,value] of [['edit-status',s.draft.status],['notes',s.draft.notes],['next-action',s.draft.next_action],['due',s.draft.due_date]])if($(key).value!==value)$(key).value=value;
    $('count').textContent=`${s.draft.notes.length} / 4,000 note characters · ${s.draft.next_action.length} / 500 next-action characters${s.dirty?' · Unsaved changes':''}`;}
  $('fields').disabled=s.pending;$('save').disabled=!s.dirty||s.pending||s.blocked;$('save').textContent=s.pending?'Saving…':'Save company';$('reload').disabled=s.pending;$('close').disabled=s.pending;
}
const route=id=>id?'#company='+id:'#';
async function go(id,{discard=false,historyChange=false}={}){
  if(model.state.pending){await model.navigate(id);if(historyChange)history.replaceState(null,'',route(model.state.id));return;}
  if((model.state.dirty||model.state.uncertain)&&!discard){decision={id};$('decision').hidden=false;
    $('decision-text').textContent=model.state.uncertain?'Save result is unknown. Copy your draft if needed. Discard it and read the persisted revision?':'Discard this draft and continue? Copy any notes and next action you need first.';
    $('keep').focus();if(historyChange)history.replaceState(null,'',route(model.state.id));return;}
  $('decision').hidden=true;decision=null;const loading=model.navigate(id,{discard});
  if(!historyChange&&location.hash!==route(id))history.pushState(null,'',route(id));await loading;
  if(model.state.id===id)$('detail-title').focus();
}
$('keep').addEventListener('click',()=>{decision=null;$('decision').hidden=true;$('notes').focus();});
$('discard').addEventListener('click',()=>{if(decision)go(decision.id,{discard:true});});
$('close').addEventListener('click',()=>go(null));$('reload').addEventListener('click',()=>go(model.state.id));
$('editor').addEventListener('submit',e=>{e.preventDefault();model.save();});
$('edit-status').addEventListener('change',e=>model.edit('status',e.target.value));$('due').addEventListener('change',e=>model.edit('due_date',e.target.value));
$('notes').addEventListener('input',e=>model.edit('notes',e.target.value));$('next-action').addEventListener('input',e=>model.edit('next_action',e.target.value));
$('status').addEventListener('change',()=>model.list({status:$('status').value,page:1}));$('refresh').addEventListener('click',()=>model.list());
$('previous').addEventListener('click',()=>model.list({page:model.state.list.page-1}));$('next').addEventListener('click',()=>model.list({page:model.state.list.page+1}));
const hashId=()=>/^#company=([a-f0-9]{64})$/.exec(location.hash)?.[1]||null;
window.addEventListener('popstate',()=>go(hashId(),{historyChange:true}));
window.addEventListener('beforeunload',e=>{if(model.state.dirty||model.state.pending||model.state.uncertain){e.preventDefault();e.returnValue='';}});
model.list();go(hashId(),{historyChange:true});
