import assert from 'node:assert/strict';
import {setupOnboarding,practiceScene} from '../ui/onboarding.js';
const nodes=new Map(),elements=[];let focused=null;
class Element extends EventTarget{
 constructor(tag='div'){super();this.tag=tag;this.hidden=false;this.open=false;this.disabled=false;this.isConnected=true;this.children=[];this.classes=new Set();this.classList={add:n=>this.classes.add(n),remove:n=>this.classes.delete(n),contains:n=>this.classes.has(n)};elements.push(this);}
 set innerHTML(v){for(const match of v.matchAll(/\bid="([^"]+)"/g))get(match[1]);this.html=v;}
 append(...children){this.children.push(...children);}prepend(...children){this.children.unshift(...children);}before(){}
 setAttribute(n,v){this[n]=v;}querySelector(s){if(s==='ol')return this.ol||(this.ol=new Element('ol'));return null;}
 replaceChildren(...children){this.children=children;}focus(){focused=this;}select(){}showModal(){this.open=true;}close(){this.open=false;}click(){return this.onclick?.();}
}
function get(id){if(!nodes.has(id)){const e=new Element();e.id=id;nodes.set(id,e);}return nodes.get(id);}
const nativeCreate=tag=>new Element(tag),doc={body:new Element('body'),createElement:tag=>{const e=nativeCreate(tag);Object.defineProperty(e,'id',{get(){return this._id;},set(v){this._id=v;nodes.set(v,this);}});return e;},getElementById:get,querySelector:s=>s==='dialog[open]'?elements.find(e=>e.open):get(s),querySelectorAll:()=>elements.filter(e=>e.classes.has('onboarding-focus')),get activeElement(){return focused;}};
const documentEvents=new EventTarget();doc.addEventListener=(...args)=>documentEvents.addEventListener(...args);doc.dispatchEvent=(...args)=>documentEvents.dispatchEvent(...args);
globalThis.document=doc;globalThis.MutationObserver=class{observe(){}};
get('welcome').hidden=false;const host=get('canvas-host');host.clientWidth=900;host.clientHeight=500;
const state={id:null,revision:0},editor={host,scene:null,offset:{x:0,y:0},selectedIds:[],position(){},fit(){},setSelection(ids){this.selectedIds=ids;}};
let stored={version:1,status:'unseen',step:'welcome',practice_job_id:null},imports=0,canSave=true,leave=()=>Promise.resolve(true),toasts=[];
const ui=setupOnboarding({state,editor,api:async(path,body)=>{
 if(path==='/api/onboarding'){if(body)stored={...stored,...body};return {state:structuredClone(stored)};}
 if(path==='/api/scene/import'){imports++;assert.deepEqual(body.scene,practiceScene());return {job_id:'practice'};}
 if(path==='/api/jobs/practice/scene')return {scene:editor.scene};throw Error(path);
},flush:async()=>canSave,canLeave:()=>leave(),refreshJobs:async()=>{},openJob:async id=>{state.id=id;state.revision=1;editor.scene=editor.scene||practiceScene();get('welcome').hidden=true;return true;},tab(){},toast:t=>toasts.push(t)});
await ui.ready();assert.equal(get('onboarding-welcome').open,true);
await get('onboarding-start').onclick();assert.equal(imports,1);assert.equal(stored.practice_job_id,'practice');assert.equal(stored.step,'select');assert.equal(get('onboarding-next').disabled,true);
editor.selectedIds=['practice_0'];ui.refresh();assert.equal(get('onboarding-next').disabled,false);
canSave=false;await get('onboarding-next').onclick();assert.equal(stored.step,'select','A save failure cannot advance a lesson');
canSave=true;await get('onboarding-next').onclick();assert.equal(stored.step,'edit');assert.equal(get('onboarding-next').disabled,true);
editor.scene.objects[0].label='采集样本';ui.refresh();await get('onboarding-next').onclick();assert.equal(stored.step,'asset');
state.id='other';ui.refresh();assert.equal(get('onboarding-next').disabled,true,'Other documents cannot satisfy a lesson');
state.id='practice';editor.scene.objects.push({id:'added',type:'vesicle',label:'囊泡'});ui.refresh();await get('onboarding-next').onclick();assert.equal(stored.step,'export');assert.equal(get('onboarding-next').disabled,true);
ui.exported('other');assert.equal(get('onboarding-next').disabled,true,'An unrelated export does not complete the practice');
await get('onboarding-pause').onclick();assert.equal(stored.status,'in_progress');assert.equal(get('onboarding-coach').hidden,true);
get('open-onboarding').onclick();await get('onboarding-start').onclick();assert.equal(imports,1,'Resuming reopens the same practice document');assert.equal(stored.step,'export');
ui.exported('practice');assert.equal(get('onboarding-next').disabled,false);await get('onboarding-next').onclick();assert.equal(stored.status,'completed');assert.equal(get('onboarding-finish').open,true);
get('onboarding-keep').onclick();get('open-onboarding').onclick();let resolveLeave;leave=()=>new Promise(r=>resolveLeave=r);const pending=get('onboarding-start').onclick();await get('onboarding-explore').onclick();resolveLeave(true);await pending;assert.equal(stored.status,'skipped');assert.equal(get('onboarding-welcome').open,false);assert.equal(imports,1,'Dismissing during a slow save never creates or opens a new practice');
delete globalThis.document;delete globalThis.MutationObserver;
console.log('First-run practice, save failure, document isolation, export success, pause/resume and delayed-dismissal behavior passed.');
