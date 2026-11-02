import assert from 'node:assert/strict';
import {vectorDetailSources} from '../ui/vector-details.js';
const svg=id=>({id,asset_snapshot:{svg:`<svg viewBox="0 0 10 10"><path d="M0 0L1 1"/></svg>`},visible:true});
const scene={objects:[svg('arrow-group'),svg('icon-group'),{id:'plain',type:'protein',visible:true}]};
assert.deepEqual(vectorDetailSources(scene,[]).map(o=>o.id),['arrow-group','icon-group']);
assert.deepEqual(vectorDetailSources(scene,['icon-group']).map(o=>o.id),['icon-group'],'A selected imported group focuses the detail editor');
assert.deepEqual(vectorDetailSources(scene,['plain']).map(o=>o.id),['arrow-group','icon-group'],'Non-vector selection falls back to all imported groups');
console.log('Focused vector detail selection keeps arrows and icons individually editable.');
