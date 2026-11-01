import test from 'node:test';
import assert from 'node:assert/strict';
import {createDocumentSaver,documentSaveState,saveBeforeDestructiveAction} from '../ui/save-state.js';

const dirty=()=>({id:'job-a',revision:3,pending:[{op:'update',id:'o1',changes:{label:'First'}}],dirty:1,saving:false,conflict:false});
const response=revision=>({revision,scene:{},svg:'<svg/>',audit:{}});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};

test('Home, clean and original-image previews need no scene write',async()=>{
  let writes=0;
  for(const state of [{id:null,pending:[]},{id:'old-image',revision:0,pending:[]},{id:'clean',revision:2,pending:[],conflict:true}]){
    assert.equal(await saveBeforeDestructiveAction(state,async()=>{writes++;return false;}),true);
  }
  assert.equal(writes,0);
  assert.equal(await saveBeforeDestructiveAction({id:null,pending:[{}]},()=>true),false);
});

test('Concurrent save and restart wait for edits made during an earlier save',async()=>{
  const state=dirty(),first=deferred(),second=deferred(),calls=[];
  const saver=createDocumentSaver({state,write(id,revision,operations){calls.push({id,revision,operations});return calls.length===1?first.promise:second.promise;}});
  const auto=saver.flush(),manual=saver.flush(),gate=saveBeforeDestructiveAction(state,saver.flush);
  assert.equal(auto,manual);assert.equal(state.saving,true);
  state.pending.push({op:'update',id:'o1',changes:{label:'Latest'}});state.dirty++;
  first.resolve(response(4));await new Promise(r=>setImmediate(r));
  assert.equal(calls.length,2);assert.equal(calls[1].revision,4);assert.equal(state.saving,true);
  let done=false;gate.then(()=>{done=true;});await Promise.resolve();assert.equal(done,false);
  second.resolve(response(5));assert.equal(await gate,true);assert.equal(await auto,true);
  assert.equal(state.revision,5);assert.equal(state.saving,false);assert.deepEqual(state.pending,[]);
});

test('A failed save keeps the full operation order and prevents restart; retry persists it',async()=>{
  const state=dirty(),first=deferred();let calls=0;
  const saver=createDocumentSaver({state,write(){calls++;return calls===1?first.promise:Promise.resolve(response(4));},failed(error){state.saveError=error.message;}});
  const saving=saver.flush();state.pending.push({op:'remove',id:'o2'});
  first.reject(Error('本机服务连接失败'));assert.equal(await saving,false);
  clearTimeout(state.timer);
  assert.equal(documentSaveState(state).kind,'error');assert.deepEqual(state.pending.map(x=>x.op),['update','remove']);
  assert.equal(state.revision,3);assert.equal(await saveBeforeDestructiveAction(state,saver.flush),true);
  assert.equal(documentSaveState(state).kind,'saved');
});

test('Conflict retains edits and does not blindly retry the stale revision',async()=>{
  const state=dirty();let calls=0;
  const saver=createDocumentSaver({state,write(){calls++;throw Error('版本冲突');},failed(){state.conflict=true;}});
  assert.equal(await saver.flush(),false);assert.equal(await saver.flush(),false);assert.equal(calls,1);
  assert.equal(documentSaveState(state).kind,'conflict');assert.equal(state.pending.length,1);
});

test('A document switch cannot acknowledge old edits or append failures to the new document',async()=>{
  const state=dirty(),request=deferred();
  const saver=createDocumentSaver({state,write:()=>request.promise});
  const saving=saver.flush();state.id='job-b';state.revision=8;state.pending=[];
  request.reject(Error('late failure'));assert.equal(await saving,false);assert.deepEqual(state.pending,[]);assert.equal(state.revision,8);
});

test('A preview exception never replays a server-acknowledged add',async()=>{
  const state=dirty();state.pending=[{op:'add',object:{id:'new'}}];let calls=0;
  const saver=createDocumentSaver({state,write:async()=>{calls++;return response(4);},applied(){throw Error('preview unavailable');}});
  assert.equal(await saver.flush(),false);assert.equal(state.pending.length,0);assert.equal(state.revision,4);
  assert.equal(await saver.flush(),true);assert.equal(calls,1);
});

test('A save that returns before draining changes cannot authorize a restart',async()=>{
  const state=dirty();assert.equal(await saveBeforeDestructiveAction(state,async()=>true),false);
});

test('An uncommitted text field must be finished before the restart save gate',async()=>{
  const state={id:'job-a',revision:4,pending:[],saving:false,inlineEditing:true};let committed=false;
  assert.equal(documentSaveState(state).label,'文字待保存');
  assert.equal(await saveBeforeDestructiveAction(state,async()=>{state.inlineEditing=false;committed=true;return true;}),true);
  assert.equal(committed,true);
});
