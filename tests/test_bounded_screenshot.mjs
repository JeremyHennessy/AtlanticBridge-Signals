import test from 'node:test';
import assert from 'node:assert/strict';
import {planCapture} from './bounded_screenshot.mjs';
test('ordinary capture remains full resolution and full page',()=>assert.deepEqual(planCapture(9000,852,3,393),{mode:'full',offsets:[0]}));
test('iPhone long capture covers every vertical position without reducing DPR',()=>{const h=14000,v=852,p=planCapture(h,v,3,393);assert.equal(p.mode,'viewport-sections');assert.equal(p.offsets[0],0);assert.equal(p.offsets.at(-1)+v,h);assert.ok(p.offsets.every((y,i)=>!i||y<=p.offsets[i-1]+v));});
test('transport threshold is explicit',()=>{assert.equal(planCapture(10000,852,3,393).mode,'full');assert.equal(planCapture(10001,852,3,393).mode,'viewport-sections');});
test('invalid or excessive captures fail, never truncate',()=>{assert.throws(()=>planCapture(0,852,3,393));assert.throws(()=>planCapture(1000,852,100,393));assert.throws(()=>planCapture(1e8,852,3,393));});
