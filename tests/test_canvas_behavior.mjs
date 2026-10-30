// Run with node tests/test_canvas_behavior.mjs; no window or model required.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../ui/canvas-editor.js',import.meta.url),'utf8');
const {edgeGeometry,SceneEditor,resizedObject,hitObjects}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const object=(id,x,y,w=10,h=10,type='protein')=>({id,x,y,w,h,type,visible:true,rotation:0,label:'',font_size_pt:8});
const scene={canvas:{width_mm:180,height_mm:120},objects:[object('a',10,20),object('b',70,20),object('block',40,20)]};
let g=edgeGeometry(scene,{source:'a',target:'b',source_port:'auto',target_port:'auto'});
assert.notEqual(g.control.y,25,'Curve must avoid the intervening molecule');
scene.objects[0]=object('a',10,4,10,8,'ligand');scene.objects[1]=object('b',10,30,10,20,'receptor_dimer');
g=edgeGeometry(scene,{source:'a',target:'b'});
assert.deepEqual(g.start,{x:15,y:12});assert.deepEqual(g.end,{x:15,y:30});
const editor=Object.create(SceneEditor.prototype);
Object.assign(editor,{doc:{objects:[object('a',10,20)],relations:[]},selected:new Set(['a']),undoStack:[],redoStack:[],draw(){},onSelection(){},events:[],onChange(ops,doc){this.events.push({ops,doc});}});
const before=structuredClone(editor.doc);editor.doc.objects[0].x=30;editor.commit(before,'drag');
assert.equal(editor.undoStack.length,1,'A completed drag is one undo step');
editor.undo();assert.equal(editor.doc.objects[0].x,10);editor.redo();assert.equal(editor.doc.objects[0].x,30);
assert.equal(editor.events.length,3);assert.ok(editor.events.every(e=>e.ops[0].op==='replace'));
console.log('4 editor behavior checks passed');

// Library insertion respects drop coordinates and avoids existing artwork on click.
Object.assign(editor,{doc:{canvas:{width_mm:180,height_mm:120},style:{stroke_pt:.8},compartments:[],objects:[object('existing',78,53,24,18)],relations:[]},selected:new Set(),setSelection(ids){this.selected=new Set(ids);}});
editor.insertObject('immune_cell','T cell',{asset_id:'bio_t_lymphocyte',default_dim:[20,24]},{x:40,y:40});
let inserted=editor.doc.objects.at(-1);assert.equal(inserted.x,30);assert.equal(inserted.y,28);assert.equal(inserted.asset_id,'bio_t_lymphocyte');
editor.insertObject('immune_cell','Macrophage',{default_dim:[24,24]});inserted=editor.doc.objects.at(-1);
assert.ok(editor.doc.objects.slice(0,-1).every(o=>inserted.x+inserted.w<=o.x||inserted.x>=o.x+o.w||inserted.y+inserted.h<=o.y||inserted.y>=o.y+o.h),'Click insertion finds free space');
editor.doc.objects[0].x=10;editor.doc.objects[1].x=40;editor.doc.objects[2].x=90;
editor.selected=new Set(editor.doc.objects.map(o=>o.id));editor.distributeSelection('x');
const sorted=[...editor.doc.objects].sort((a,b)=>a.x-b.x);
assert.ok(Math.abs((sorted[1].x-sorted[0].x-sorted[0].w)-(sorted[2].x-sorted[1].x-sorted[1].w))<1e-5);
editor.selected=new Set([sorted[0].id,sorted[1].id]);editor.connectSelection('inhibits');assert.equal(editor.doc.relations.at(-1).type,'inhibits');
console.log('4 library interaction checks passed');

// Resizing rotated artwork holds the opposite corner in place, including shrink.
function corner(o,x,y){const a=(o.rotation||0)*Math.PI/180,c=Math.cos(a),s=Math.sin(a);return {x:o.x+o.w/2+c*(x-.5)*o.w-s*(y-.5)*o.h,y:o.y+o.h/2+s*(x-.5)*o.w+c*(y-.5)*o.h};}
for(const rotation of [0,35,90,180])for(const handle of ['nw','ne','sw','se']){
  const old={...object('resize',10,20,20,10),rotation},before=corner(old,handle.includes('w')?1:0,handle.includes('n')?1:0);
  const changed={...old,...resizedObject(old,handle,-3,2,true)},after=corner(changed,handle.includes('w')?1:0,handle.includes('n')?1:0);
  assert.ok(Math.hypot(before.x-after.x,before.y-after.y)<1e-8,'Opposite corner remains anchored');assert.equal(changed.w/changed.h,2);
}
assert.equal(resizedObject(object('x',0,0,20,10),'se',-5,0,true).w,15,'Proportional artwork can shrink horizontally');
const hitScene={objects:[{...object('context',0,0,100,100),role:'context'},object('free',5,5),{...object('locked',5,5),locked:true},{...object('hidden',5,5),visible:false}]};
assert.deepEqual(hitObjects(hitScene,{x:8,y:8}).map(o=>o.id),['free']);
assert.deepEqual(hitObjects(hitScene,{x:8,y:8},true).map(o=>o.id),['locked','free','context']);
assert.equal(hitObjects({objects:[{...object('rotated',0,0,20,4),rotation:90}]},{x:10,y:10}).length,1);

// A click is not a move; one constrained drag is a single undo transaction.
const drag=Object.create(SceneEditor.prototype);
Object.assign(drag,{doc:{objects:[object('a',10,20)],relations:[]},selected:new Set(['a']),zoom:1,snap:false,undoStack:[],redoStack:[],draw(){},drawOverlay(){},onSelection(){},events:[],onChange(ops){this.events.push(ops);},world:e=>({x:e.clientX,y:e.clientY}),host:{querySelector(){return null;}}});
function gesture(){drag.gesture={kind:'move',start:{x:0,y:0},px:0,py:0,before:structuredClone(drag.doc),ids:['a']};}
gesture();drag.move({clientX:1,clientY:1});drag.up({});assert.equal(drag.undoStack.length,0);
gesture();drag.move({clientX:12,clientY:4,shiftKey:true});drag.up({});assert.deepEqual([drag.doc.objects[0].x,drag.doc.objects[0].y],[22,20]);assert.equal(drag.undoStack.length,1);
gesture();drag.move({clientX:30,clientY:5});drag.cancelGesture();assert.equal(drag.doc.objects[0].x,22);assert.equal(drag.undoStack.length,1);

// Copy/paste preserves internal edges and grouping while assigning fresh IDs.
const paste=Object.create(SceneEditor.prototype);
Object.assign(paste,{doc:{objects:[{...object('a',0,0),group_id:'g'},{...object('b',20,0),group_id:'g'},object('outside',60,0)],relations:[{id:'ab',source:'a',target:'b',type:'activates',control:{x:15,y:10}},{id:'out',source:'b',target:'outside',type:'inhibits'}]},selected:new Set(['a','b']),applyOperations(ops){this.ops=ops;},setSelection(ids){this.ids=ids;}});
const key=k=>({key:k,ctrlKey:true,target:{closest(){return null;}},preventDefault(){}});
paste.key(key('c'));paste.key(key('v'));const added=paste.ops.filter(o=>o.op==='add'),edge=paste.ops.find(o=>o.op==='add_relation').relation;
assert.equal(added.length,2);assert.equal(paste.ops.length,3);assert.notEqual(added[0].object.id,'a');assert.equal(added[0].object.group_id,added[1].object.group_id);assert.notEqual(added[0].object.group_id,'g');assert.equal(edge.source,added[0].object.id);assert.equal(edge.target,added[1].object.id);assert.deepEqual(edge.control,{x:20,y:15});
// Sparse artwork must be selectable inside its logical bounds, even where no
// painted SVG path receives the pointer (e.g. a dimer's central gap).
Object.assign(drag,{tool:'select',host:{focus(){},setPointerCapture(){},querySelector(){return null;}},selected:new Set(),world:()=>({x:25,y:25})});
drag.down({button:0,pointerId:1,clientX:25,clientY:25,target:{closest(){return null;}},preventDefault(){}});
assert.deepEqual(drag.selectedIds,['a']);assert.equal(drag.gesture.kind,'move');drag.up({});
// Alt clicks cycle overlaps; Alt drags keep the current object and bypass snap.
Object.assign(drag,{doc:{objects:[object('lower',0,0),object('upper',0,0)],relations:[]},selected:new Set(['upper']),setSelection(ids){this.selected=new Set(ids);},world:e=>({x:e.clientX,y:e.clientY})});
const altDown={button:0,pointerId:1,clientX:5,clientY:5,altKey:true,target:{closest(){return null;}},preventDefault(){}};
drag.down(altDown);drag.up({});assert.deepEqual(drag.selectedIds,['lower']);
drag.down(altDown);drag.move({clientX:15,clientY:5,altKey:true});drag.up({});assert.equal(drag.doc.objects[0].x,10);assert.equal(drag.doc.objects[1].x,0);assert.deepEqual(drag.selectedIds,['lower']);
console.log('10 canvas ergonomics regression scenarios passed');
