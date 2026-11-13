import assert from 'node:assert/strict';
import {preservePropertyState} from '../ui/property-state.js';
import {preserveCanvasView} from '../ui/panel-layout.js';

const document={activeElement:null};
const parent={ownerDocument:document,scrollTop:40,nodes:[],contains:n=>!!n&&parent.nodes.includes(n),querySelectorAll(selector){return selector==='details[open]'?this.nodes.filter(n=>n.open):selector==='details'?this.nodes:[];}};
function render(){parent.nodes=[{open:false,querySelector:()=>({textContent:'精确位置'})}];parent.scrollTop=0;}
preservePropertyState(parent,'object-a',render);parent.nodes[0].open=true;parent.scrollTop=70;
preservePropertyState(parent,'object-a',render);assert.equal(parent.nodes[0].open,true);assert.equal(parent.scrollTop,70);
preservePropertyState(parent,'object-b',render);assert.equal(parent.nodes[0].open,false);
let fits=0;
const editor={host:{clientWidth:800,clientHeight:600},scene:{canvas:{width_mm:180,height_mm:120}},zoom:1,fitMode:false,offset:{x:0,y:0},fit(){fits++;}};
preserveCanvasView(editor,()=>editor.host.clientWidth=520);assert.equal(fits,1,'Opening properties retains an overview after dragging a molecule');
console.log('Inspector expansion and overview survive edits and panel changes.');

const {SceneEditor}=await import('../ui/canvas-editor.js');
const originalDocument=globalThis.document;
globalThis.document={querySelectorAll:()=>[],getElementById:()=>null};
try {
  const editor=Object.create(SceneEditor.prototype);
  editor.doc={objects:[{id:'a',x:1,y:2,w:8,h:6,visible:true},{id:'b',x:30,y:2,w:8,h:6,visible:true},{id:'old',source_role:'arrow',visible:true}],relations:[]};
  Object.assign(editor,{host:{style:{},dispatchEvent(){}},selected:new Set(),undoStack:[],redoStack:[],draw(){},drawOverlay(){},onChange(){},onSelection(){},onStatus(){},setSelection(){}});
  editor.commit=function(before){this.undoStack.push(before);this.redoStack=[];};
  editor.replacingArrow='old';editor.tool='connect';editor.key({key:'Escape',target:{isContentEditable:false,tagName:'BUTTON',closest:selector=>selector==='button,summary'}});assert.equal(editor.tool,'select','Esc cancels while a toolbar button has focus');assert.equal(editor.doc.objects[2].visible,true,'Cancelling replacement keeps original arrow');
  editor.replacingArrow='old';assert.equal(editor.finishConnection('a','b'),true);assert.equal(editor.doc.objects[2].visible,false);assert.equal(editor.doc.relations.length,1);
  editor.undo();assert.equal(editor.doc.objects[2].visible,true);assert.equal(editor.doc.relations.length,0,'One undo restores the original arrow');
  editor.redo();assert.equal(editor.doc.objects[2].visible,false);assert.equal(editor.doc.relations[0].target,'b');
} finally {globalThis.document=originalDocument;}
