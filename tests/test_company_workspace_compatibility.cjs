const assert=require('node:assert/strict');
const {test}=require('node:test');
const fs=require('fs');
const W=require('../ui/workspace.js');
const fixture=JSON.parse(fs.readFileSync('tests/fixtures/company_workspace/browser-export.json','utf8'));
function store(){const map=new Map();const s=new W.Store({getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,v)});s.load();return s;}
test('migration fixture is accepted losslessly by the unchanged public workspace',()=>{
  assert.deepEqual(W.validateBackup(fixture).entries,fixture.entries);
  const s=store();assert.deepEqual(s.mergeNew(fixture),{added:5,kept:0});
  assert.deepEqual(s.backup().entries,fixture.entries);
});
test('migration fixture covers every existing analyst status and same-name distinct identities',()=>{
  assert.deepEqual(fixture.entries.map(e=>e.status).sort(),Object.keys(W.STATUSES).sort());
  assert.equal(new Set(fixture.entries.map(e=>e.company_name)).size,1);
  assert.equal(new Set(fixture.entries.map(e=>e.id)).size,5);
});
test('fixture preserves next actions, Unicode and untrusted note text without execution',()=>{
  const s=store();s.mergeNew(fixture);
  assert.equal(s.entries()[0].notes,'Private invented note 🦞 <script>not executable</script>\n=1+1');
  assert.ok(s.entries().every(e=>e.next_action==='Review, do not contact'));
});
