import assert from 'node:assert/strict';
import {preserveCanvasView,syncPanelButtons} from '../ui/panel-layout.js';

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
const empty={host:{clientWidth:800,clientHeight:600},scene:null};
let changed=false;preserveCanvasView(empty,()=>changed=true);assert.equal(changed,true);

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
console.log('Panel reflow preserves document center and zoom; disclosure state follows visibility.');
