import assert from 'node:assert/strict';
import test from 'node:test';
import {readFile} from 'node:fs/promises';
import {COMMANDS,searchCommands} from '../ui/components/command-palette.js';
import {segmentIndex,setupOptionsDisclosure} from '../ui/components/controls.js';

test('command search finds an operation by Chinese, English and export format',()=>{
 assert.equal(searchCommands('矢量')[0].id,'import');
 assert.equal(searchCommands('PDF 导出')[0].id,'export');
 assert.equal(searchCommands('prompt')[0].id,'generate');
 assert.equal(searchCommands('文档')[0].id,'documents');
 assert.equal(searchCommands('   无此功能  ').length,0);
 assert.equal(searchCommands('').length,COMMANDS.length);
 assert.equal(new Set(COMMANDS.map(c=>c.id)).size,COMMANDS.length);
});

test('document commands have an explicit document gate, creation commands remain available',()=>{
 for(const id of ['rename','save','export','fit','focus','properties','annotations','review']) assert.equal(COMMANDS.find(c=>c.id===id).document,true,id);
 for(const id of ['new','blank','generate','import','assets','templates','documents','settings']) assert.ok(!COMMANDS.find(c=>c.id===id).document,id);
});

test('segmented keyboard navigation wraps and honors Home and End',()=>{
 assert.equal(segmentIndex(0,'ArrowLeft',3),2);
 assert.equal(segmentIndex(2,'ArrowRight',3),0);
 assert.equal(segmentIndex(1,'Home',3),0);
 assert.equal(segmentIndex(0,'End',3),2);
 assert.equal(segmentIndex(1,'Tab',3),1);
 assert.equal(segmentIndex(0,'ArrowRight',0),-1);
});

test('drawing options close on Escape or outside click and keep focus predictable',()=>{
 const previous=globalThis.document,doc=new EventTarget(),root=new EventTarget();
 let focused=false;const summary={focus(){focused=true;}},inside={};
 root.open=true;root.querySelector=()=>summary;root.contains=target=>target===inside;
 globalThis.document=doc;
 try{
  setupOptionsDisclosure(root);
  const key=new Event('keydown',{cancelable:true});Object.assign(key,{key:'Escape'});root.dispatchEvent(key);
  assert.equal(root.open,false);assert.equal(focused,true);assert.equal(key.defaultPrevented,true);
  root.open=true;const internal=new Event('pointerdown');Object.defineProperty(internal,'target',{value:inside});doc.dispatchEvent(internal);assert.equal(root.open,true);
  doc.dispatchEvent(new Event('pointerdown'));assert.equal(root.open,false);
 }finally{globalThis.document=previous;}
});

test('the desktop shell has one local stylesheet, valid targets, and no lost editor IDs',async()=>{
 const html=await readFile(new URL('../ui/canvas-studio.html',import.meta.url),'utf8');
 const links=[...html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*>/g)];
 assert.equal(links.length,1);assert.match(links[0][0],/\/ui\/workbench-ui\.css/);
 const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert.equal(ids.length,new Set(ids).size);
 for(const id of ['welcome','brief-input','creation-dialog','canvas-host','quick-label','asset-library-dialog','properties','save-document','command-dialog','command-results','home-template-examples','rename-document']) assert.ok(ids.includes(id),id);
 for(const id of [...html.matchAll(/(?:data-close|data-command|aria-controls)="([^"]+)"/g)].map(m=>m[1])) assert.ok(ids.includes(id),id);
 const css=await readFile(new URL('../ui/workbench-ui.css',import.meta.url),'utf8');
 assert.match(css,/@layer features, components, workspace, panels/);
 assert.match(css,/\.whats-new-corner \{position:fixed/);
 assert.match(css,/prefers-reduced-motion:reduce/);
});
