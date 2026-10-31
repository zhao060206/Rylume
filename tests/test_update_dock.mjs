import assert from 'node:assert/strict';
import {setupUpdateDock,newerRelease,dockLabel} from '../ui/update-dock.js';

class Node extends EventTarget {
 constructor(tag){super();this.tagName=tag;this.children=[];this.attrs={};this.style={};this.hidden=false;this.classList={add:()=>{}};this.textContent='';}
 append(...nodes){this.children.push(...nodes);}
 prepend(node){this.children.unshift(node);}
 setAttribute(key,value){this.attrs[key]=String(value);}
 contains(node){return node===this||this.children.some(child=>child.contains(node));}
 getBoundingClientRect(){return {left:12,right:212,bottom:650};}
}
const body=new Node('body'),footer=new Node('footer');
globalThis.document=new class extends EventTarget {
 constructor(){super();this.body=body;this.activeElement=null;}
 createElement(tag){return new Node(tag);}
 querySelector(){return footer;}
};
globalThis.window=new EventTarget();globalThis.innerWidth=1280;globalThis.innerHeight=720;
const opened=[],dock=setupUpdateDock({openUpdate:info=>opened.push(info)});
const root=footer.children[0],button=root.children[0],preview=body.children[0];
const status={state:'available',current_version:'4.4.0',latest_version:'4.4.1',notes:'本次更新\n- 左下角常驻更新入口\n- 悬停查看日志'};
dock.render({state:'idle',current_version:'4.4.0'});assert.equal(root.hidden,true);
dock.render(status);assert.equal(root.hidden,false);assert.equal(preview.hidden,true);
button.dispatchEvent(new Event('mouseenter'));assert.equal(preview.hidden,false);
assert.equal(preview.children[1].textContent,status.notes);assert.equal(opened.length,0,'Hover must never start a download or restart');
preview.dispatchEvent(new Event('mouseenter'));
const escape=new Event('keydown');escape.key='Escape';document.dispatchEvent(escape);assert.equal(preview.hidden,true);
button.dispatchEvent(new Event('focus'));assert.equal(preview.hidden,false,'Keyboard focus exposes the same notes');
button.onclick();assert.equal(opened.length,1);assert.equal(preview.hidden,true);
dock.render({...status,state:'downloading',progress:41});assert.equal(root.hidden,false);assert.equal(button.children[1].children[0].textContent,'正在下载 · 41%');
dock.render({state:'checking',current_version:'4.4.0'});assert.equal(root.hidden,false,'Transient checks cannot dismiss a known newer release');
dock.render({state:'failed',current_version:'4.4.0'});assert.equal(root.hidden,false);
button.dispatchEvent(new Event('mouseenter'));assert.equal(preview.children[1].textContent,status.notes,'A failed recheck retains the actual target release notes');
dock.render({...status,state:'ready',can_apply:true});assert.equal(button.children[1].children[0].textContent,'重启更新');
assert.equal(opened.length,1,'Finishing a download must not restart by itself');
dock.render({...status,state:'cancelled'});assert.equal(root.hidden,false);
dock.render({state:'up_to_date',current_version:'4.4.1',latest_version:'4.4.1'});assert.equal(root.hidden,true);assert.equal(preview.hidden,true);
assert.equal(newerRelease({current_version:'4.9.0',latest_version:'4.10.0'}),true);
assert.equal(newerRelease({current_version:'4.4.1',latest_version:'bad'}),false);
assert.equal(dockLabel({state:'ready',can_apply:false}),'下载已完成');
dock.render({...status,notes:'<img src=x onerror=alert(1)>'});button.dispatchEvent(new Event('mouseenter'));
assert.equal(preview.children[1].textContent,'<img src=x onerror=alert(1)>','Untrusted release notes remain literal text');
assert.equal(preview.children[1].children.length,0);
console.log('Persistent update dock, hover/focus notes, Esc, progress, retry, explicit click and upgrade completion passed');
