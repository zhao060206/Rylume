import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
async function module(path){const s=await readFile(new URL(path,import.meta.url),'utf8');return import('data:text/javascript;base64,'+Buffer.from(s).toString('base64'));}
const {SceneEditor,wheelIntent,clampView}=await module('../ui/canvas-editor.js');
assert.equal(wheelIntent({}), 'pan');assert.equal(wheelIntent({ctrlKey:true}),'zoom');assert.equal(wheelIntent({metaKey:true}),'zoom');assert.equal(wheelIntent({shiftKey:true}),'horizontal');
const editor=Object.create(SceneEditor.prototype);let ops=[],tool='connect';
Object.assign(editor,{doc:{objects:[{id:'a'},{id:'b'}]},relationType:'inhibits',applyOperations(v){ops=v;},setTool(v){tool=v;},onStatus(){}});
assert.equal(editor.finishConnection('a','b','e'),true);assert.equal(ops[0].relation.type,'inhibits');assert.equal(ops[0].relation.source_port,'e');assert.equal(tool,'select');
assert.equal(editor.finishConnection('a','a'),false,'Self links never create a draft');assert.equal(editor.finishConnection('a','missing'),false);
editor.relationType='associates';editor.finishConnection('a','b');assert.equal(ops[0].relation.uncertain,true,'A plain arrow must not invent a scientific meaning');
const {findingPresentation}=await module('../ui/review-ui.js');const scene={objects:[{id:'a',label:'STAT'},{id:'b',label:'AKT'}],relations:[]};
const overlap=findingPresentation({code:'label-overlap',object_ids:['a','b']},scene);assert.ok(overlap.detail.includes('STAT')&&overlap.detail.includes('AKT'));assert.equal(overlap.canPreview,true);assert.equal(overlap.section,'layout');
const science=findingPresentation({code:'uncertain-relation',object_ids:[]},scene);assert.equal(science.canPreview,false);assert.equal(science.section,'content');
assert.equal(findingPresentation({code:'overlap',object_ids:['a','b']},scene).canPreview,false,'An intentional binding cannot be rearranged silently');
assert.deepEqual(clampView({x:-999,y:-999},{width:600,height:400},{width:900,height:470}),{x:24,y:24},'A fitted paper cannot disappear after scrolling');
assert.deepEqual(clampView({x:999,y:999},{width:1200,height:800},{width:900,height:470}),{x:24,y:24});
assert.deepEqual(clampView({x:-999,y:-999},{width:1200,height:800},{width:900,height:470}),{x:-324,y:-354});
// Pointer capture retargets dblclick to the host. Coordinates must still open
// the actual object's label editor and commit the typed value.
const inline={style:{},setAttribute(){},focus(){},select(){},remove(){}};
globalThis.document={createElement(){return inline;}};
const label={dataset:{labelFor:'a'},getBoundingClientRect(){return {left:20,top:20,width:50,height:12};}};
const captured=Object.create(SceneEditor.prototype);let committed;
Object.assign(captured,{doc:{objects:[{id:'a',x:0,y:0,w:10,h:10,visible:true,label:'Before'}]},host:{querySelectorAll(){return [label];},querySelector(){return null;},getBoundingClientRect(){return {left:0,top:0};},append(){}},world(){return {x:5,y:5};},applyOperations(ops){committed=ops;}});
captured.editLabel({target:{closest(){return null;}},clientX:5,clientY:5,preventDefault(){}});
assert.equal(inline.value,'Before');inline.value='After';inline.onkeydown({key:'Enter',preventDefault(){},stopPropagation(){}});assert.equal(committed[0].changes.label,'After');
delete globalThis.document;
console.log('10 novice workflow regression scenarios passed');
