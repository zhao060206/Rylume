import assert from 'node:assert/strict';
import {SceneEditor} from '../ui/canvas-editor.js';
import {reviewCounts} from '../ui/review-ui.js';

assert.deepEqual(reviewCounts({findings:[],vision:{findings:[{message:'缺少独立编号'}]}}),{local:0,visual:1,total:1});
assert.equal(reviewCounts({findings:[{status:'acknowledged'}],vision:{findings:[{status:'dismissed'}]}}).total,0);

const editor=Object.create(SceneEditor.prototype);
editor.doc={canvas:{width_mm:180,height_mm:120},provenance:{method:'import-semantic-vector'},objects:[
  {id:'cell',type:'cell',visible:true,x:0,y:0,w:120,h:100},
  {id:'golgi',type:'golgi',visible:true,x:30,y:30,w:20,h:16}
],relations:[]};
Object.assign(editor,{selected:new Set(['golgi']),tool:'select',zoom:1,offset:{x:0,y:0},
  host:{focus(){},setPointerCapture(){}},world:e=>({x:e.clientX,y:e.clientY}),
  semanticHit:()=>editor.doc.objects[0],drawOverlay(){},draw(){},onSelection(){}});
function event(x,y,extra={}){return {clientX:x,clientY:y,button:0,pointerId:1,preventDefault(){},target:{closest(){return null;}},...extra};}
editor.down(event(32,32));editor.move(event(42,42));
assert.equal(editor.doc.objects[1].x,40,'Dragging transparent selected bounds moves the selected organelle');
assert.equal(editor.doc.objects[0].x,0,'Underlying cell stays put');
editor.down(event(1,1));assert.equal(editor.selected.has('cell'),true,'Outside bounds selects another structure');
editor.selected=new Set(['golgi']);editor.down(event(42,42,{ctrlKey:true}));
assert.equal(editor.selected.has('cell'),true,'Ctrl allows a deliberate new pick through selected bounds');
editor.selected=new Set(['cell']);editor.semanticHit=()=>editor.doc.objects[1];editor.down(event(43,43));
assert.equal(editor.selected.has('golgi'),true,'A selected cell must not trap clicks on a smaller foreground organelle');
console.log('Visual review counts and transparent selection drag behavior passed.');
