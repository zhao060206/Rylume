import assert from 'node:assert/strict';
import {setupWorkspace} from '../ui/workspace-ui.js';
import {setupGenerationWorkflow,generationOutcomeText} from '../ui/generation-workflow.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
class Element{
 constructor(){this.value='';this.children=[];this.hidden=false;this.open=false;this.listeners={};this.dataset={};this.classList={add(){},remove(){},toggle(){},contains(){return false;}};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
 querySelector(){return new Element();}
 addEventListener(name,handler){(this.listeners[name]??=[]).push(handler);}
 dispatchEvent(event){for(const handler of this.listeners[event.type]||[])handler(event);this['on'+event.type]?.(event);}
 setAttribute(name,value){this[name]=value;}
 removeAttribute(name){delete this[name];}
 showModal(){this.open=true;}
 close(){this.open=false;}
 getContext(){return {fillRect(){}};}
}
const elements=new Map();
function $(id){if(!elements.has(id))elements.set(id,new Element());return elements.get(id);}
globalThis.document={getElementById:$,querySelector(){return new Element();},querySelectorAll(){return [];},createElement(){return new Element();},activeElement:null};
globalThis.innerWidth=1600;
$('new-size').value='90x150';$('generation-dpi').value='300';
const state={id:'first',revision:1,jobs:[],pending:[],originalBrief:'Author science',enhancedFrom:'Author science',reference:null};
const editor={selectedIds:[],host:new Element(),scene:{source_text:'Author science'}};
const pending=[],messages=[];
const workspace=setupWorkspace({state,editor,api(path,body){const wait=deferred();pending.push({path,body,...wait});return wait.promise;},
 toast(message){messages.push(message);},flush:async()=>true,follow:async()=>{},tab(){},openJob(){},renderAudit(){},renderHistory(){}});
$('brief-input').value='First visual enhancement';
const enhance=$('expand-brief').onclick();
assert.equal(pending[0].body.text,'Author science');
assert.ok(pending[0].body.canvas[1]>pending[0].body.canvas[0],'Optimization must use the selected portrait page');
pending.shift().resolve({text:'Second visual enhancement'});await enhance;
$('use-expanded-brief').onclick();
assert.equal(state.originalBrief,'Author science','Repeated optimization never promotes AI wording into authored science');
assert.equal(workspace.payload($('brief-input').value).original_text,'Author science');
const obsolete=$('expand-brief').onclick();
state.id='second';state.enhancedFrom=null;state.originalBrief='New science';$('brief-input').value='New science';
pending.shift().resolve({text:'Obsolete output'});await obsolete;
assert.equal($('brief-preview-dialog').open,false,'A delayed optimization cannot open over another document');
assert.equal($('brief-input').value,'New science');
assert.ok(messages.some(x=>x.includes('已变化')));
state.originalBrief='Stale cached source';
assert.equal(workspace.payload('Current plain description').original_text,'Current plain description');

const fileReaders=[];
globalThis.FileReader=class{readAsDataURL(){fileReaders.push(this);}};
let calls=0;
setupGenerationWorkflow({state,editor,workspace:{getMode(){return 'image';},payload(){return {text:'New science'};}},
 api:async()=>{calls++;return {job_id:'failed'};},flush:async()=>true,canLeave:async()=>true,
 follow:async()=>({status:'failed',error:'Model disconnected; draft retained'}),checkModels:async()=>true,
 toast(message){messages.push(message);},tab(){}});
const fileLoad=$('reference-file').onchange({target:{files:[{size:100}]}});
assert.equal(state.referenceLoading,true);assert.equal($('generate').disabled,true);
await $('generate').onclick();assert.equal(calls,0,'Generation cannot silently use an old reference during upload');
$('clear-generation-reference').onclick();
fileReaders[0].result='data:image/png;base64,OLD';fileReaders[0].onload();await fileLoad;
assert.equal(calls,0,'A cleared reference cannot return through a delayed FileReader');
await $('generate').onclick();
assert.equal($('generation-inline-status').textContent,'Model disconnected; draft retained');
assert.ok(!generationOutcomeText({status:'cancelled'}).includes('已保留生成版本'));
assert.ok(generationOutcomeText({status:'completed',illustration_result:{state:'draft'}}).includes('未全部完成'));
delete globalThis.FileReader;delete globalThis.document;delete globalThis.innerWidth;
console.log('Real generation controls preserve authored intent, ignore stale optimization and file reads, gate pending references, and report failure accurately');
