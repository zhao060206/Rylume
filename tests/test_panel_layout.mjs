import assert from 'node:assert/strict';
import {preserveCanvasView,syncPanelButtons} from '../ui/panel-layout.js';
import {SceneEditor} from '../ui/canvas-editor.js';

// Collapsing a 292 px library must preserve the same scientific content at the
// center of the viewport, including while the author is zoomed into a detail.
let calls=0;
const editor={host:{clientWidth:700,clientHeight:600},scene:{},offset:{x:-180,y:-90},zoom:2.2,fitMode:true,position(){calls++;}};
const contentCenter=()=>[(editor.host.clientWidth/2-editor.offset.x)/editor.zoom,(editor.host.clientHeight/2-editor.offset.y)/editor.zoom];
const before=contentCenter();
preserveCanvasView(editor,()=>{editor.host.clientWidth+=292;});
assert.deepEqual(contentCenter(),before);
assert.equal(editor.zoom,2.2);
assert.equal(editor.fitMode,false,'ResizeObserver must not refit the document after a panel change');
preserveCanvasView(editor,()=>{editor.host.clientWidth-=284;editor.host.clientHeight-=50;});
assert.deepEqual(contentCenter(),before);
assert.equal(calls,2);
// Mode changes open both sidebars through helpers that also preserve the view.
// The outer transaction must account for each pixel once, even when nested.
const nestedBefore=contentCenter();
preserveCanvasView(editor,()=>{
  preserveCanvasView(editor,()=>{editor.host.clientWidth-=260;});
  preserveCanvasView(editor,()=>{editor.host.clientWidth-=278;editor.host.clientHeight+=18;});
});
assert.deepEqual(contentCenter(),nestedBefore,'Nested chrome changes preserve the same world-space center');
const empty={host:{clientWidth:800,clientHeight:600},scene:null};
let changed=false;preserveCanvasView(empty,()=>changed=true);assert.equal(changed,true);
let fits=0;const fitted={scene:{},fitMode:true,host:{clientWidth:800,clientHeight:600},offset:{x:0,y:0},fit(){fits++;},position(){throw Error('A fitted document must refit');}};
preserveCanvasView(fitted,()=>{fitted.host.clientWidth-=260;});
assert.equal(fits,1);assert.equal(fitted.fitMode,true,'Fit-to-window remains active when opening properties');
let left=260;
fitted.host.getBoundingClientRect=()=>({left,top:100});
fitted.position=()=>{};
preserveCanvasView(fitted,()=>{left=40;fitted.host.clientWidth+=220;},{keepScreenPosition:true});
assert.equal(fits,1,'Automatic properties must not force a new fit');
assert.equal(fitted.fitMode,false);
assert.equal(left+fitted.offset.x,260,'The same canvas point remains under the pointer while the sidebar changes');
const narrow=Object.create(SceneEditor.prototype);
const object={id:'far-right',x:130,y:70,w:20,h:10,visible:true};
Object.assign(narrow,{doc:{objects:[object]},selected:new Set([object.id]),host:{clientWidth:420,clientHeight:800},offset:{x:0,y:0},zoom:1,position(){}});
narrow.ensureSelectionVisible({onlyIfCenterHidden:true});
assert.equal(narrow.zoom,1);
assert.ok(narrow.offset.x+(object.x+object.w)*96/25.4<narrow.host.clientWidth,'A selected box obscured by the inspector is panned into view');
assert.equal(narrow.offset.y,0,'An already visible axis does not move');

const classes=new Set(['left-collapsed','properties-hidden']);
const workspace={classList:{contains:x=>classes.has(x)}};
const button=active=>({classList:{contains:x=>x==='active'&&active},attrs:{},setAttribute(k,v){this.attrs[k]=v;}});
const assets=button(true),layers=button(false),properties=button(false);
const root={querySelectorAll:()=>[assets,layers],getElementById:()=>properties};
syncPanelButtons(workspace,root);
assert.equal(assets.attrs['aria-expanded'],'false');
assert.equal(properties.attrs['aria-pressed'],'false');
classes.delete('left-collapsed');classes.delete('properties-hidden');
syncPanelButtons(workspace,root);
assert.equal(assets.attrs['aria-expanded'],'true');
assert.equal(layers.attrs['aria-expanded'],'false');
assert.equal(properties.attrs['aria-pressed'],'true');
// The asset library is a dialog, independent of the old left-panel state.
assets.dataset={tab:'assets'};
const assetWindow={open:true,classList:{contains:()=>false}};
root.getElementById=id=>id==='asset-library-dialog'?assetWindow:properties;
classes.add('left-collapsed');syncPanelButtons(workspace,root);
assert.equal(assets.attrs['aria-expanded'],'true','An open asset window remains expanded while the old sidebar is closed');
assetWindow.classList.contains=()=>true;syncPanelButtons(workspace,root);
assert.equal(assets.attrs['aria-expanded'],'false','Minimizing the asset window updates its toolbar disclosure');
assetWindow.open=false;syncPanelButtons(workspace,root);assert.equal(assets.attrs['aria-expanded'],'false');
console.log('Panel reflow preserves document center and zoom; disclosure state follows visibility.');
