import assert from 'node:assert/strict';
import {workflowHint} from '../ui/novice-guidance.js';
import {SceneEditor} from '../ui/canvas-editor.js';

const scene={objects:[],relations:[]};
assert.equal(workflowHint({scene}).action,'assets','An empty paper must offer a concrete starting action.');
scene.objects.push({id:'a',label:'受体',visible:true});
assert.equal(workflowHint({scene}).action,'assets','One object needs a second object before connecting.');
assert.equal(workflowHint({scene,selectedIds:['a']}).action,'edit');
scene.objects.push({id:'b',label:'激酶',visible:true});
assert.equal(workflowHint({scene}).action,'connect');
assert.ok(workflowHint({scene,tool:'connect',connectStart:'a'}).title.includes('受体'));
assert.equal(workflowHint({scene,tool:'connect'}).action,'cancel','A visible escape from a temporary tool is required.');
scene.relations.push({id:'r',source:'a',target:'b',type:'activates'});
assert.equal(workflowHint({scene,selectedIds:['r']}).action,'meaning');
assert.equal(workflowHint({scene}).action,'export');
assert.equal(workflowHint({scene,selectedIds:['a','b']}).action,'arrange');
scene.objects[0].locked=true;
assert.equal(workflowHint({scene,selectedIds:['a']}).action,'layers');
scene.objects[1].visible=false;
assert.equal(workflowHint({scene}).action,'assets','Hidden objects do not count as usable connection targets.');
assert.equal(workflowHint({scene:null,legacy:true}).action,'export');

// Inserting while zoomed in must pan only enough to reveal the new object.
// Existing object geometry and an already useful viewport must remain intact.
const editor=Object.create(SceneEditor.prototype);
let positions=0;
Object.assign(editor,{doc:{objects:[{id:'a',visible:true,x:30,y:30,w:15,h:10}]},selected:new Set(['a']),zoom:1,offset:{x:0,y:0},host:{clientWidth:900,clientHeight:600},position(){positions++;}});
const before=structuredClone(editor.doc);
editor.ensureSelectionVisible();assert.equal(positions,0);
editor.offset={x:-900,y:-700};editor.ensureSelectionVisible();
assert.equal(editor.zoom,1);assert.equal(positions,1);assert.deepEqual(editor.doc,before);
assert.ok(30*96/25.4+editor.offset.x>=40&&30*96/25.4+editor.offset.y>=80);
const retained={...editor.offset};editor.ensureSelectionVisible();assert.deepEqual(editor.offset,retained);assert.equal(positions,1);
console.log('Novice next actions follow real edits; inserted artwork is revealed without rearranging the document.');
