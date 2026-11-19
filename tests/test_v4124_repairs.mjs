import assert from 'node:assert/strict';
import {SceneEditor,resizeHandles,fitEditedText} from '../ui/canvas-editor.js';
import {uploadSummary} from '../ui/document-assistant.js';
import {groupFindings,findingPresentation} from '../ui/review-ui.js';

globalThis.document={querySelectorAll:()=>[],getElementById:()=>null};
function editor(){
 const e=Object.create(SceneEditor.prototype);
 Object.assign(e,{doc:{canvas:{width_mm:180,height_mm:120},objects:[{id:'membrane',type:'process',x:0,y:0,w:100,h:80,visible:true},{id:'source',type:'protein',label:'STAT',x:20,y:20,w:10,h:8,visible:true},{id:'target',type:'protein',label:'pSTAT',x:60,y:20,w:10,h:8,visible:true},{id:'arrow',source_role:'arrow',visible:true}],relations:[]},host:{style:{},focus(){},setPointerCapture(){},hasPointerCapture(){return false;},dispatchEvent(){}},selected:new Set(),zoom:1,undoStack:[],redoStack:[],tool:'connect',replacingArrow:'arrow',world:e=>({x:e.clientX,y:e.clientY}),draw(){},drawOverlay(){},onSelection(){},onStatus(){},onChange(){}});
 e.commit=function(before){this.undoStack.push(before);this.redoStack=[];};return e;
}
const click=(e,x,y)=>({clientX:x,clientY:y,button:0,pointerId:1,preventDefault(){},target:{closest:()=>null}});
{
 const e=editor(),a=click(e,25,24);e.down(a);e.up(a);
 assert.equal(e.connectStart,'source');assert.equal(e.doc.relations.length,0,'First click cannot bind the overlapping membrane');assert.equal(e.doc.objects.at(-1).visible,true);
 const b=click(e,65,24);e.down(b);e.up(b);
 assert.equal(e.doc.relations.length,1);assert.equal(e.doc.relations[0].source,'source');assert.equal(e.doc.relations[0].target,'target');assert.equal(e.doc.objects.at(-1).visible,false);
 e.undo();assert.equal(e.doc.relations.length,0);assert.equal(e.doc.objects.at(-1).visible,true);
 e.redo();assert.equal(e.doc.relations.length,1);
}
{
 const e=editor();e.down(click(e,25,24));e.up(click(e,65,24));assert.equal(e.doc.relations[0].target,'target','Drag-to-connect still works');
 const cancel=editor();cancel.down(click(cancel,25,24));cancel.up(click(cancel,25,24));cancel.key({key:'Escape',target:{tagName:'DIV',closest:()=>null}});assert.equal(cancel.doc.objects.at(-1).visible,true);assert.equal(cancel.doc.relations.length,0);
}
{
 const o={x:10,y:20,w:9,h:1.2};const handles=resizeHandles(o,1/(3.78*.52));assert.equal(handles.length,4);
 for(const [,x,y] of handles)assert.ok(Math.abs(x-(o.x+o.w/2))>4/(3.78*.52)||Math.abs(y-(o.y+o.h/2))>4/(3.78*.52),'No resize handle covers the body centre');
 assert.ok(fitEditedText({type:'text',label:'外膜',w:8,font_size_pt:8},{label:'线粒体外膜'}).w>8);
 assert.equal(fitEditedText({type:'text',label:'外膜',w:8},{label:'线粒体外膜',w:7}).w,7);
 const fitted=fitEditedText({id:'label',type:'text',label:'外膜',x:20,w:8,font_size_pt:8},{label:'线粒体外膜'},{relations:[{source:'label',callout:true,source_port:'e'}]});assert.equal(fitted.x+fitted.w,28);
}
{
 const e=editor();e.doc.objects.push({id:'point',type:'protein',depiction:'anchor',parent_id:'membrane',x:20,y:20,w:.5,h:.5});e.doc.relations.push({id:'leader',source:'target',target:'point',type:'associates',callout:true});
 e.gesture={kind:'edge',id:'leader',handle:'end',before:structuredClone(e.doc)};e.up(click(e,30,35));assert.equal(e.doc.objects.at(-1).x,29.75);assert.equal(e.doc.objects.at(-1).y,34.75);assert.equal(e.doc.relations[0].target,'point');e.undo();assert.equal(e.doc.objects.at(-1).x,20);
}
assert.match(uploadSummary([{id:'a',status:'ready'}],new Set(['a'])).text,/已结束.*已就绪/);
assert.match(uploadSummary([{id:'a',status:'converting'}],new Set(['a'])).text,/正在转换/);
assert.equal(uploadSummary([{id:'a',status:'failed'}],new Set(['a'])).error,true);
assert.match(uploadSummary([{id:'a',status:'ready'}],new Set(['a']),['b 超过 16 MB']).text,/超过/);
const findings=[{code:'overlap',severity:'warning',object_ids:['a','b']},{code:'overlap',severity:'warning',object_ids:['a','c']}];assert.equal(groupFindings(findings).length,1);
assert.match(findingPresentation(findings[0],{objects:[{id:'a',display_name:'受体'},{id:'b',display_name:'细胞膜'}]}).detail,/受体.*细胞膜/);
console.log('4.12.4 pointer, undo, small-object, callout, upload, and review regressions passed.');
