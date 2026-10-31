import assert from 'node:assert/strict';
import {clampPosition,fitWindow,setupFloatingWindows,showFloatingWindow} from '../ui/floating-windows.js';
assert.equal(clampPosition(-20,100,600),0);
assert.equal(clampPosition(580,100,600),500);
assert.deepEqual(fitWindow({left:580,top:-3,width:800,height:400},{width:600,height:300}),{left:0,top:0,width:600,height:300});
// A small DOM double exercises the shipped event handlers and shared restore strip.
// Geometry and actual pointer gestures are additionally checked in the real browser.
class Node extends EventTarget {
 constructor(tag){super();this.tagName=tag.toUpperCase();this.children=[];this.style={};this.dataset={};this.attrs={};this.hidden=false;this.open=false;this.isConnected=true;this.className='';this.textContent='';this.classList={contains:c=>this.className.split(' ').includes(c),add:c=>{if(!this.classList.contains(c))this.className+=' '+c;},remove:c=>{this.className=this.className.split(' ').filter(v=>v!==c).join(' ');},toggle:(c,force)=>{const active=force??!this.classList.contains(c);active?this.classList.add(c):this.classList.remove(c);return active;}};}
 append(...nodes){for(const node of nodes){node.remove();node.parentElement=this;this.children.push(node);}}
 remove(){if(this.parentElement)this.parentElement.children=this.parentElement.children.filter(n=>n!==this);this.parentElement=null;}
 setAttribute(k,v){this.attrs[k]=String(v);}
 get childElementCount(){return this.children.length;}
 contains(n){return n===this||this.children.some(c=>c.contains(n));}
 closest(selector){if(selector.startsWith('.')&&this.classList.contains(selector.slice(1)))return this;return this.parentElement?.closest(selector)||null;}
 querySelectorAll(selector){let all=this.children.flatMap(c=>[c,...c.querySelectorAll('*')]);if(selector==='*')return all;return all.filter(n=>selector.split(',').some(s=>s.startsWith('.')?n.classList.contains(s.slice(1)):n.tagName===s.toUpperCase()));}
 querySelector(s){return this.querySelectorAll(s)[0]||null;}
 focus(){document.activeElement=this;}
 getBoundingClientRect(){return {left:parseFloat(this.style.left)||100,top:parseFloat(this.style.top)||80,width:parseFloat(this.style.width)||640,height:parseFloat(this.style.height)||400};}
 show(){this.open=true;this.shows=(this.shows||0)+1;}
 close(){this.open=false;this.dispatchEvent(new Event('close'));}
 click(){this.onclick?.();}
}
const body=new Node('body'),opener=new Node('button');body.append(opener);
globalThis.innerWidth=1280;globalThis.innerHeight=900;
globalThis.document={body,activeElement:opener,createElement:t=>new Node(t),getElementById:()=>null,querySelector:()=>null};
globalThis.MutationObserver=class {observe(){}};
function makeWindow(name){const win=new Node('dialog'),head=new Node('div'),title=new Node('h2'),close=new Node('button');head.className='dialog-heading';title.textContent=name;close.onclick=()=>win.close();head.append(title,close);win.append(head);body.append(win);return win;}
const first=makeWindow('素材详情'),second=makeWindow('资源与更新');
setupFloatingWindows(first);setupFloatingWindows(second);setupFloatingWindows(first);
assert.equal(first.querySelectorAll('.floating-minimize').length,1,'Repeated initialization cannot add duplicate controls');
showFloatingWindow(first);const original={...first.style},shows=first.shows;
first.querySelector('.floating-minimize').click();
assert.ok(first.open,'Minimizing does not close the library or cancel its work');
assert.ok(first.classList.contains('is-minimized'));
let strip=body.querySelector('.window-restore-strip');assert.equal(strip.children.length,1);assert.equal(strip.hidden,false);
showFloatingWindow(second);second.querySelector('.floating-minimize').click();assert.equal(strip.children.length,2);
strip.children[0].querySelector('.window-restore-button').click();
assert.ok(!first.classList.contains('is-minimized'));assert.equal(first.shows,shows,'Restoring reuses the open window');
for(const key of ['left','top','width','height'])assert.equal(first.style[key],original[key]);
assert.equal(strip.children.length,1);
first.querySelector('.floating-minimize').click();showFloatingWindow(first);
assert.ok(!first.classList.contains('is-minimized'),'The original entry also restores a minimized window');
assert.ok(Number(first.style.zIndex)>Number(second.style.zIndex),'Separate initializers share a stacking order');
second.close();assert.equal(strip.children.length,0);assert.ok(strip.hidden,'Closing a minimized window removes its restore entry');
first.querySelector('.floating-minimize').click();globalThis.innerWidth=320;globalThis.innerHeight=300;showFloatingWindow(first);
assert.ok(parseFloat(first.style.width)<=304 && parseFloat(first.style.height)<=284,'Restore after resizing remains reachable');
first.querySelector('.floating-minimize').click();strip.children[0].querySelector('.window-restore-close').click();assert.ok(!first.open && strip.hidden);
for(const key of ['document','MutationObserver','innerWidth','innerHeight'])delete globalThis[key];
console.log('Window minimize, same-instance restore, multiple windows, stacking, close, resize and duplicate setup passed');
