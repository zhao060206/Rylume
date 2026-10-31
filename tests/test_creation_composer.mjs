import assert from 'node:assert/strict';
import {setupCreationComposer} from '../ui/creation-composer.js';

class Element extends EventTarget {
 constructor(){super();this.value='';this.textContent='';this.hidden=false;this.open=false;this.maxLength=8000;this.attrs=new Map();this.classes=new Set();this.classList={toggle:(n,v)=>{const on=v??!this.classes.has(n);on?this.classes.add(n):this.classes.delete(n);return on;},contains:n=>this.classes.has(n)};}
 getAttribute(n){return this.attrs.get(n)??null;} setAttribute(n,v){this.attrs.set(n,String(v));}
 append(child){child.parentElement=this;}
 close(){this.open=false;} showModal(){this.open=true;}
 focus(){} select(){} click(){this.onclick?.();}
}
const nodes=new Map(),element=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
const observers=[];
globalThis.MutationObserver=class {constructor(f){this.f=f;}observe(){observers.push(this.f);}};
const doc=new EventTarget();doc.getElementById=element;doc.querySelectorAll=()=>[];globalThis.document=doc;
const storage=new Map();globalThis.localStorage={removeItem:k=>storage.delete(k),setItem:(k,v)=>storage.set(k,v)};
const input=element('brief-input'),welcome=element('welcome');
element('new-size').value='180x120';element('generation-dpi').value='300';
let mode='vector',restored;
const state={originalBrief:'',referencePurpose:'layout'};
const composer=setupCreationComposer({state,toast(){},workflow:{restoreInputs(d){restored=d;Object.assign(state,{referenceId:d.referenceId,referencePurpose:d.referencePurpose});}},workspace:{getMode:()=>mode,setMode:v=>mode=v}});
const mount=()=>observers.forEach(f=>f());
function leave(){composer.leavingHome();welcome.hidden=true;mount();}
function home(){welcome.hidden=false;mount();}
function write(text){input.value=text;state.originalBrief=text;}
assert.equal(element('panel-generate').parentElement,element('home-composer-host'));
write('my unfinished mechanism');state.enhancedFrom=input.value;state.enhancedBrief='clearer mechanism';state.referenceId='ref-my-draft';mode='image';element('new-size').value='90x150';
leave();write('opened old document');state.enhancedBrief=null;state.referenceId='old-reference';mode='vector';home();
assert.equal(input.value,'my unfinished mechanism');assert.equal(state.enhancedBrief,'clearer mechanism');assert.equal(restored.referenceId,'ref-my-draft');assert.equal(mode,'image');assert.equal(element('new-size').value,'90x150');assert.equal(element('creation-dialog').open,false);
// Completing the submitted home draft clears only that draft.
doc.dispatchEvent(new Event('generation-submitted'));leave();doc.dispatchEvent(new Event('generation-presented'));home();assert.equal(input.value,'');
// The author can write the next draft after submission. Completion must retain it.
write('first submitted figure');doc.dispatchEvent(new Event('generation-submitted'));write('next unsubmitted figure');leave();write('generated document');doc.dispatchEvent(new Event('generation-presented'));home();assert.equal(input.value,'next unsubmitted figure');
// A failure never emits presented and therefore retains the original inputs.
write('retry this figure');doc.dispatchEvent(new Event('generation-submitted'));leave();home();assert.equal(input.value,'retry this figure');
let generated=0;element('generate').onclick=()=>generated++;
const shortcut=new Event('keydown',{cancelable:true});Object.assign(shortcut,{key:'Enter',ctrlKey:true});element('panel-generate').dispatchEvent(shortcut);assert.equal(generated,1);assert.equal(shortcut.defaultPrevented,true);

// Document suggestions are explicit draft replacements, with a recoverable original.
write('original research with reference');state.referenceId='original-ref';state.archetype='original-type';mode='image';
element('generation-literature').checked=true;element('review-brief-candidate').hidden=false;
assert.equal(composer.usePrompt('Document suggestion one'),true);
assert.equal(input.value,'Document suggestion one');assert.equal(mode,'vector');assert.equal(state.referenceId,undefined);
assert.equal(state.archetype,null);assert.equal(element('generation-literature').checked,false);
assert.equal(element('review-brief-candidate').hidden,true);
assert.equal(element('restore-document-brief').hidden,false);
assert.equal(composer.usePrompt('Document suggestion two'),true);
element('restore-document-brief').click();
assert.equal(input.value,'original research with reference');assert.equal(state.referenceId,'original-ref');
assert.equal(storage.get('rylume-research-brief'),'original research with reference');
assert.equal(mode,'image');assert.equal(state.archetype,'original-type');assert.equal(element('generation-literature').checked,true);
// An author-edited suggestion becomes the next restorable draft.
composer.usePrompt('suggestion');write('author edited suggestion');composer.usePrompt('another');element('restore-document-brief').click();
assert.equal(input.value,'author edited suggestion');
state.active=true;assert.equal(composer.usePrompt('blocked'),false);assert.equal(input.value,'author edited suggestion');state.active=false;
assert.equal(composer.usePrompt('x'.repeat(8001)),false);assert.equal(composer.usePrompt('  '),false);
// A restore control must never inject another document's draft.
leave();state.id='doc-a';write('document A draft');composer.usePrompt('new A prompt');state.id='doc-b';mount();
assert.equal(element('restore-document-brief').hidden,true);
delete globalThis.document;delete globalThis.MutationObserver;delete globalThis.localStorage;
console.log('Home creation preserves unfinished text, enhancement and references; completed submissions clear only their own draft; shortcuts work inline.');
