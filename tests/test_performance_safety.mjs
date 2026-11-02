import test from 'node:test';
import assert from 'node:assert/strict';
import {applySceneDelta,SceneSaveCache} from '../ui/scene-data.js';
import {DraftStore} from '../ui/draft-store.js';
import {SceneEditor} from '../ui/canvas-editor.js';

test('A canonical save acknowledgment preserves artwork, removes stale fields and respects server ordering',()=>{
 const art='vector'.repeat(1000000),scene={revision:2,objects:[{id:'a',label:'A',asset_snapshot:{svg:art},stroke:'red'},{id:'b',label:'B'}],relations:[]};
 const next=applySceneDelta(scene,{fields:{revision:3},objects:{updated:[{id:'a',changes:{label:'New',rotation:90},unset:['stroke']}],added:[{id:'c',label:'C'}],removed:['b'],order:['c','a']},relations:{updated:[],added:[],removed:[]}});
 assert.deepEqual(next.objects.map(o=>o.id),['c','a']);assert.equal(next.objects[1].asset_snapshot.svg,art);
 assert.equal(next.objects[1].label,'New');assert.ok(!('stroke'in next.objects[1]));assert.equal(scene.objects[0].label,'A');
 next.objects[1].asset_snapshot.svg='edited';assert.equal(scene.objects[0].asset_snapshot.svg,art);
});

test('Recovery snapshots capture the gesture immediately and coalesce queued writes without stale resurrection',async()=>{
 const old=globalThis.indexedDB;globalThis.indexedDB={};
 try{
  const local=new Map(),storage={setItem(k,v){assert.ok(v.length<300000,'Large art must not block synchronous storage');local.set(k,v);},getItem:k=>local.get(k),removeItem:k=>local.delete(k)};
  const store=new DraftStore(storage),written=[];let gate;store.chain=new Promise(resolve=>gate=resolve);
  store.transaction=async(mode,work)=>work({put(snapshot){written.push(snapshot);},delete(id){written.push({deleted:id});}});
  const record={id:'same',base_revision:1,scene:{objects:[{id:'art',label:'First',svg:'path'.repeat(300000)}]}};
  const first=store.write(record);record.scene.objects[0].label='Second';const second=store.write(record);record.scene.objects[0].label='After queued write';
  gate();await Promise.all([first,second]);assert.equal(written.length,1);assert.equal(written[0].scene.objects[0].label,'Second');
  store.chain=new Promise(resolve=>gate=resolve);const pending=store.write(record),clear=store.clear('same');gate();await Promise.all([pending,clear]);
  assert.deepEqual(written.at(-1),{deleted:'same'});assert.equal(written.length,2);
 }finally{globalThis.indexedDB=old;}
});

test('A structural save followed by a small save retains the authoritative glyph while preserving newer text',()=>{
 const cache=new SceneSaveCache(),scene={revision:1,objects:[{id:'a',label:'First',state:'resting'}],relations:[]};cache.reset(scene);
 const structural={revision:2,scene:{...scene,revision:2,objects:[{...scene.objects[0],state:'activated'}]},svg:'<svg>canonical activated glyph</svg>'};
 cache.accept(structural); // Preview is deferred because the author is typing.
 const delta={revision:3,scene_delta:{fields:{revision:3},objects:{added:[],removed:[],updated:[{id:'a',changes:{label:'Still typing'},unset:[]}]},relations:{added:[],removed:[],updated:[]}}};
 cache.accept(delta);const [display,svg,base]=cache.consumePreview(delta);
 assert.equal(display.objects[0].label,'Still typing');assert.equal(svg,structural.svg);assert.equal(base.objects[0].state,'activated');assert.equal(base.objects[0].label,'First');
 assert.equal(cache.consumePreview(delta)[1],undefined);cache.reset(scene);assert.equal(cache.canonicalBase,null);
});

test('Failed large recovery writes retain an earlier durable local recovery copy',async()=>{
 const old=globalThis.indexedDB;globalThis.indexedDB={};
 try{
  const values=new Map(),storage={getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)},store=new DraftStore(storage);
  store.transaction=async()=>{throw Error('Disk full');};
  await store.write({id:'safe',scene:{label:'Earlier recovery'}});
  await assert.rejects(store.write({id:'safe',scene:{svg:'path'.repeat(300000)}}),/Disk full/);
  assert.equal((await store.read('safe')).scene.label,'Earlier recovery');
 }finally{globalThis.indexedDB=old;}
});

test('Fast pointer input renders once per frame, releases at the final location and cancels pending motion',()=>{
 const raf=globalThis.requestAnimationFrame,caf=globalThis.cancelAnimationFrame,callbacks=new Map();let id=0;
 globalThis.requestAnimationFrame=callback=>{callbacks.set(++id,callback);return id;};globalThis.cancelAnimationFrame=key=>callbacks.delete(key);
 try{
  const editor=Object.create(SceneEditor.prototype),moves=[];editor.gesture={kind:'move'};editor.move=e=>moves.push(e.clientX);
  for(let x=1;x<=100;x++)editor.queueMove({clientX:x});assert.equal(callbacks.size,1);assert.equal(moves.length,0);
  const callback=[...callbacks.values()][0];callbacks.clear();callback();assert.deepEqual(moves,[100]);
  editor.queueMove({clientX:101});editor.flushMove({clientX:110});assert.deepEqual(moves,[100,110]);assert.equal(callbacks.size,0);
  editor.queueMove({clientX:120});editor.cancelQueuedMove();assert.equal(callbacks.size,0);assert.equal(editor.pendingMove,null);
 }finally{globalThis.requestAnimationFrame=raf;globalThis.cancelAnimationFrame=caf;}
});
