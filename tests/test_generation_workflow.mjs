import assert from 'node:assert/strict';
import {pointOnPaper} from '../ui/sketch-pad.js';
import {generationPayload} from '../ui/workspace-ui.js';
import {setupGenerationWorkflow} from '../ui/generation-workflow.js';
for(const scale of [.3,.5,.9,1.2]){
 const rect={left:110,top:140,width:1200*scale,height:800*scale};
 for(const p of [{x:0,y:0},{x:340,y:285},{x:1200,y:800}]){
  const result=pointOnPaper({clientX:rect.left+p.x*scale,clientY:rect.top+p.y*scale},rect,1200,800);
  assert.ok(Math.abs(result.x-p.x)<1e-8&&Math.abs(result.y-p.y)<1e-8,'The stroke must stay directly under the pointer at every display scale');
 }
}
for(const mode of ['vector','image']){
 const payload=generationPayload({text:'增强布局',originalText:'原始科学内容',mode,referenceId:'ref_saved',referencePurpose:'sketch',sketch:{id:'j_sketch',revision:13},previewId:'gp_saved'});
 assert.equal(payload.scene_engine,'v2');assert.equal(payload.original_text,'原始科学内容');assert.equal(payload.generation_brief,'增强布局');
 assert.equal(payload.reference_id,'ref_saved');assert.equal(payload.sketch_job_id,'j_sketch');assert.equal(payload.base_revision,13);assert.equal(payload.preview_id,'gp_saved');
  assert.equal(payload.layout_policy,'preserve','An editable canvas keeps exact positions unless the author opts into cleanup');
  assert.equal(generationPayload({text:'rough sketch',referenceId:'ref_saved'}).layout_policy,'regularize');
  assert.equal(generationPayload({text:'rough sketch',sketch:{id:'draft',revision:1},layoutPolicy:'regularize'}).layout_policy,'regularize');
}
console.log('Sketch pointer mapping, both editable render styles, original intent and revision-pinned inputs passed');

// A delayed reference load must not restore a reference the author removed,
// or place a previous document's reference in the newly opened document.
const elements=new Map();
function element(id){
 if(!elements.has(id))elements.set(id,{value:'',disabled:false,hidden:false,textContent:'',
  classList:{toggle(){}},addEventListener(){},removeAttribute(name){delete this[name];},getContext(){return {fillRect(){}};}});
 return elements.get(id);
}
globalThis.document={getElementById:element,querySelectorAll(){return [];},activeElement:null};
const loads=[];
const state={id:'first',referenceId:null};
const workflow=setupGenerationWorkflow({state,editor:{scene:{objects:[]}},
 api(path){return new Promise(resolve=>loads.push({path,resolve}));},
 flush:async()=>true,follow:async()=>{},canLeave:async()=>true,workspace:{},
 checkModels:async()=>true,toast(){},tab(){}});
const removed=workflow.opened({generation_contract:{reference_id:'removed'}});
element('clear-generation-reference').onclick();
loads.shift().resolve({reference_id:'removed',preview_url:'/removed.png'});
await removed;
assert.equal(state.referenceId,null,'Removing a reference wins over a pending load');
const first=workflow.opened({generation_contract:{reference_id:'first-ref'}});
state.id='second';
const second=workflow.opened({generation_contract:{reference_id:'second-ref',reference_purpose:'sketch'}});
loads[1].resolve({reference_id:'second-ref',preview_url:'/second.png'});
await second;
loads[0].resolve({reference_id:'first-ref',preview_url:'/first.png'});
await first;
assert.equal(state.referenceId,'second-ref');
assert.equal(element('generation-reference-preview').src,'/second.png');
await workflow.opened({generation_contract:{reference_id:'second-ref',reference_purpose:'style'}});
assert.equal(state.referencePurpose,'style','Reusing a reference keeps the current document purpose');
const lateDocument=workflow.opened({generation_contract:{reference_id:'late-document'}});
workflow.restoreInputs({referenceId:'home-draft',referencePurpose:'sketch',layoutPolicy:'regularize',note:'my draft'});
loads.at(-1).resolve({reference_id:'late-document',preview_url:'/late-document.png'});
await lateDocument;
assert.equal(state.referenceId,'home-draft','Returning to a new draft cancels an old document reference read');
assert.equal(state.referencePurpose,'sketch');
assert.equal(state.referenceLoading,false);
assert.equal(state.layoutPolicy,'regularize');
assert.equal(element('generation-reference-note').textContent,'my draft');

delete globalThis.document;
console.log('Delayed reference loads preserve author removal, document isolation and reference purpose');
