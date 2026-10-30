import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
async function module(path){const s=await readFile(new URL(path,import.meta.url),'utf8');return import('data:text/javascript;base64,'+Buffer.from(s).toString('base64'));}
const {filterAssets}=await import('../ui/library-ui.js');
const assets=[{domain:'biology',category:'细胞',label:'T cell',type:'cell'},{domain:'biology',category:'实验器材',label:'Pipette',type:'equipment'},{domain:'materials',category:'细胞',label:'T cell scaffold',type:'mesh'},{category:'细胞',label:'Legacy cell',type:'cell'}];
assert.equal(filterAssets(assets).length,3);
assert.deepEqual(filterAssets(assets,{category:'细胞',query:'T CELL'}).map(a=>a.label),['T cell']);
assert.equal(filterAssets(assets,{category:'实验器材',query:'cell'}).length,0);
assert.equal(filterAssets(assets,{domain:'materials'}).length,1);
const {canApplySavedScene}=await module('../ui/workspace-ui.js');
assert.equal(canApplySavedScene({epoch:1,dirty:1,pending:0,gesture:null}),true);
assert.equal(canApplySavedScene({epoch:1,dirty:1,pending:0,gesture:{kind:'move'}}),false,'A previous save response must not overwrite an uncommitted drag');
assert.equal(canApplySavedScene({epoch:1,dirty:2,pending:1,gesture:null}),false);
assert.equal(canApplySavedScene({epoch:1,dirty:1,pending:1,gesture:null}),false);
console.log('8 taxonomy and autosave regression checks passed');
