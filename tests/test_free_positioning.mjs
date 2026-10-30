import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../ui/canvas-editor.js',import.meta.url),'utf8');
const {SceneEditor,boundaryPoint,nearestBoundary,connectionTarget,edgeGeometry,relationParts}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const object=(id,x,y,w=20,h=12)=>({id,x,y,w,h,label:id,type:'protein',visible:true,rotation:0,font_size_pt:8});
const scene={canvas:{width_mm:180,height_mm:120},style:{},objects:[object('a',10,20),object('b',100,30)],relations:[{id:'r',source:'a',target:'b',type:'activates',label:'Activation'}]};
for(const rotation of [0,31,90,180,289])for(const side of ['n','e','s','w'])for(const t of [.031,.29,.77,.984]){
  const o={...scene.objects[0],rotation},anchor={side,t},p=boundaryPoint(o,anchor),picked=nearestBoundary(o,p);
  assert.equal(picked.side,side);assert.ok(Math.abs(picked.t-t)<1e-9);
  const moved={...o,x:o.x+13,y:o.y-8,w:o.w*1.8,h:o.h*.7};
  assert.deepEqual(nearestBoundary(moved,boundaryPoint(moved,anchor)).side,side);
}
const anchor={side:'w',t:.23},target=boundaryPoint(scene.objects[1],anchor);
assert.equal(connectionTarget(scene,{x:target.x-.5,y:target.y},1,'a').object.id,'b');
assert.equal(connectionTarget(scene,{x:60,y:110},1,'a'),null);
assert.equal(connectionTarget(scene,{x:target.x-3,y:target.y},4,'a'),null,'Snap tolerance scales with zoom');
const doc=structuredClone(scene);Object.assign(doc.relations[0],{source_anchor:{side:'e',t:.17},target_anchor:anchor,label_position:{x:72,y:80}});
let g=edgeGeometry(doc,doc.relations[0]);assert.deepEqual(g.start,{x:30,y:22.04});assert.deepEqual(g.end,target);assert.deepEqual(g.label,{x:72,y:80});
const parts=relationParts('activates',g.start,g.end,g.control,'#333333',1,false,{start:true,end:true});
assert.ok(parts[0][1].d.startsWith('M 30 22.04 '));

const editor=Object.create(SceneEditor.prototype);
Object.assign(editor,{doc:structuredClone(scene),selected:new Set(),zoom:1,snap:false,tool:'select',undoStack:[],redoStack:[],draw(){},drawOverlay(){},onSelection(){},onChange(){},onStatus(){},world:e=>({x:e.clientX,y:e.clientY}),host:{focus(){},setPointerCapture(){},querySelector(){return null;}}});
const event=(x,y,target={closest(){return null;}})=>({button:0,pointerId:1,clientX:x,clientY:y,target,preventDefault(){}});
const labelTarget={dataset:{labelFor:'a'},closest(selector){return selector==='[data-label-for],[data-relation-label-for]'?this:null;}};
editor.down(event(20,36,labelTarget));assert.equal(editor.gesture.kind,'label');
editor.move(event(29,41));editor.up(event(29,41));
assert.deepEqual([editor.doc.objects[0].x,editor.doc.objects[0].y],[10,20]);assert.deepEqual([editor.doc.objects[0].label_dx,editor.doc.objects[0].label_dy],[9,5]);assert.equal(editor.undoStack.length,1);
editor.undo();assert.equal(editor.doc.objects[0].label_dx,undefined);editor.redo();assert.equal(editor.doc.objects[0].label_dx,9);
const relTarget={dataset:{relationLabelFor:'r'},closest(selector){return selector==='[data-label-for],[data-relation-label-for]'?this:null;}};
const origin=edgeGeometry(editor.doc,editor.doc.relations[0]).label,before=structuredClone(editor.doc);
editor.down(event(origin.x,origin.y,relTarget));editor.move(event(origin.x+17,origin.y-11));editor.up(event(origin.x+17,origin.y-11));
assert.deepEqual(editor.doc.relations[0].label_position,{x:origin.x+17,y:origin.y-11});assert.deepEqual(editor.doc.objects,before.objects);
editor.key({key:'ArrowRight',target:{closest(){return null;}},preventDefault(){}});assert.equal(editor.doc.relations[0].label_position.x,origin.x+17.5);
// A cancelled drag and a drop in empty space preserve the original endpoint.
editor.activeLabel=null;editor.doc=structuredClone(scene);
const edgeDown={dataset:{edgeHandle:'end',owner:'r'},closest(selector){return selector==='[data-edge-handle]'?this:null;}};
editor.down(event(100,36,edgeDown));editor.move(event(target.x,target.y));
assert.deepEqual(editor.geometry(editor.doc.relations[0]).end,target,'The endpoint tracks the exact snapped position during dragging');
editor.up(event(target.x,target.y));assert.equal(editor.doc.relations[0].target_anchor.side,'w');assert.ok(Math.abs(editor.doc.relations[0].target_anchor.t-.23)<1e-9);
const pinned=structuredClone(editor.doc);
let renderedEnd;editor.draw=function(){renderedEnd=this.geometry(this.doc.relations[0]).end;};
editor.down(event(target.x,target.y,edgeDown));editor.move(event(60,110));editor.up(event(60,110));assert.deepEqual(editor.doc,pinned);
assert.deepEqual(renderedEnd,edgeGeometry(pinned,pinned.relations[0]).end,'Dropping in empty space removes the transient visual preview');
editor.down(event(target.x,target.y,edgeDown));editor.move(event(101,31));editor.cancelGesture();assert.deepEqual(editor.doc,pinned);
assert.deepEqual(renderedEnd,edgeGeometry(pinned,pinned.relations[0]).end,'Escape redraws the saved endpoint, not the cancelled preview');
console.log('Free edge anchors, rotated/resized targets, label drag/nudge, live preview, undo and cancelled drops passed');
