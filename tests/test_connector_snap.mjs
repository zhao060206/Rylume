import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const source=await readFile(new URL('../ui/canvas-editor.js',import.meta.url),'utf8');
const {SceneEditor,boundaryPoint,connectionKeypoints,connectionTarget,edgeGeometry}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const a={id:'a',x:20,y:20,w:30,h:20,type:'process',state:'flow_process',visible:true,rotation:0,label:'A'};
const b={...a,id:'b',x:100,y:70,label:'B'};
const scene={canvas:{width_mm:180,height_mm:120},style:{},objects:[a,b],relations:[{id:'r',source:'a',target:'b',type:'sequence',label:''}]};
assert.equal(connectionKeypoints(a).length,8);
assert.equal(connectionKeypoints({...a,type:'protein'}).length,4);
assert.equal(connectionKeypoints({...a,state:'flow_decision'}).length,4);
for(const rotation of [0,37,90,213])for(const zoom of [.25,1,4]){
  const o={...b,rotation},doc={...scene,objects:[a,o]};
  for(const k of connectionKeypoints(o)){
    const p=k.point,near={x:p.x+1/(96/25.4*zoom),y:p.y};
    const snap=connectionTarget(doc,near,zoom,'a');
    assert.equal(snap?.keypoint,k.kind,`rotation ${rotation}, zoom ${zoom}`);
    assert.deepEqual(boundaryPoint(o,snap.anchor),p);
  }
  const p=boundaryPoint(o,{side:'w',t:.31}),free=connectionTarget(doc,p,zoom,'a',true);
  assert.equal(free.keypoint,undefined);assert.ok(Math.abs(free.anchor.t-.31)<1e-9);
}
const near={x:b.x+.25,y:b.y+b.h/2+.6};
assert.deepEqual(connectionTarget(scene,near,1,'a').anchor,{side:'w',t:.5});
assert.ok(Math.abs(connectionTarget(scene,near,1,'a',true).anchor.t-.53)<1e-9);
assert.equal(connectionTarget({...scene,objects:[a,{...b,locked:true}]},near,1,'a'),null);
assert.equal(connectionTarget({...scene,objects:[a,{...b,visible:false}]},near,1,'a'),null);
// Use the actual pointer handlers for start, finish, reattachment and undo.
const editor=Object.create(SceneEditor.prototype);
Object.assign(editor,{doc:structuredClone(scene),selected:new Set(),zoom:1,snap:false,tool:'connect',undoStack:[],redoStack:[],draw(){},drawOverlay(){},onSelection(){},onChange(){},onStatus(){},world:e=>({x:e.clientX,y:e.clientY}),host:{focus(){},setPointerCapture(){},querySelector(){return null;},dispatchEvent(){}}});
const event=(x,y,altKey=false,target={closest(){return null;}})=>({button:0,pointerId:1,clientX:x,clientY:y,altKey,target,preventDefault(){}});
editor.finishConnection=function(source,target,port,anchor,start){this.result={source,target,port,anchor,start};};
editor.down(event(a.x+.2,a.y+.2));assert.deepEqual(editor.gesture.anchor,{side:'n',t:0});
editor.move(event(b.x+b.w-.2,b.y+b.h-.2));editor.up(event(b.x+b.w-.2,b.y+b.h-.2));
assert.deepEqual(editor.result.start,{side:'n',t:0});assert.deepEqual(editor.result.anchor,{side:'s',t:1});
editor.tool='select';editor.connectStart=null;
const handle={dataset:{edgeHandle:'end',owner:'r'},closest(s){return s==='[data-edge-handle]'?this:null;}};
editor.down(event(100,80,false,handle));editor.move(event(near.x,near.y));
assert.deepEqual(editor.geometry(editor.doc.relations[0]).end,{x:100,y:80});
editor.up(event(near.x,near.y));assert.deepEqual(editor.doc.relations[0].target_anchor,{side:'w',t:.5});
assert.equal(editor.undoStack.length,1);editor.undo();assert.equal(editor.doc.relations[0].target_anchor,undefined);editor.redo();
editor.down(event(100,80,false,handle));editor.move(event(near.x,near.y,true));editor.up(event(near.x,near.y,true));
assert.ok(Math.abs(editor.doc.relations[0].target_anchor.t-.53)<1e-9);
const saved=JSON.parse(JSON.stringify(editor.doc));saved.objects[1].x+=11;saved.objects[1].rotation=90;
assert.deepEqual(edgeGeometry(saved,saved.relations[0]).end,boundaryPoint(saved.objects[1],saved.relations[0].target_anchor));
assert.equal(JSON.stringify(editor.doc).includes('keypoint'),false,'Transient helper UI never enters saved/exported scenes');
console.log('CAD keypoint snap: midpoints/corners, view scales, rotation, Alt, pointer start/end, undo and persistent bindings passed');
