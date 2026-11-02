/** Exercise real editor commands against an isolated, running application. */
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
import {SceneEditor} from '../ui/canvas-editor.js';
import {applySceneDelta} from '../ui/scene-data.js';
const [url,job,output]=process.argv.slice(2);
assert.ok(url?.startsWith('http://127.0.0.1:')&&job&&output,'Usage: node tools/verify_large_edit.mjs URL JOB REPORT');
async function api(path,body){const r=await fetch(url+path,{method:body?'PATCH':'GET',headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const data=await r.json();assert.ok(r.ok,data.error);return data;}
const path='/api/jobs/'+job+'/scene',before=await api(path),target=before.scene.objects.find(o=>o.type==='text'&&o.text_appearance);
assert.ok(target,'Use a real imported figure with preserved original labels');
const operations=[],editor=Object.create(SceneEditor.prototype);
Object.assign(editor,{doc:structuredClone(before.scene),selected:new Set([target.id]),undoStack:[],redoStack:[],draw(){},onSelection(){},onChange(ops){operations.push(...ops);}});
editor.changeSelection({label:target.label+' (edit test)'});
editor.changeSelection({x:target.x+.5});editor.undo();editor.redo();editor.undo();editor.undo();
assert.equal(operations.length,6);
assert.ok(operations.every(op=>op.op==='update'&&op.id===target.id));
const body={base_revision:before.revision,operations,response:'delta'},size=Buffer.byteLength(JSON.stringify(body));
assert.ok(size<1200,'Art must not be included in a label/position update');
const started=performance.now(),saved=await api(path,body),elapsed=performance.now()-started,reopened=await api(path);
assert.ok(saved.scene_delta&&!saved.scene&&!saved.svg,'The save acknowledgment must not transfer the whole artwork');
assert.deepEqual(applySceneDelta(before.scene,saved.scene_delta),reopened.scene,'Canonical delta matches the pinned revision');
assert.equal(reopened.revision,before.revision+1);
assert.deepEqual(reopened.scene.objects,before.scene.objects,'Undo must recover every object and original glyph');
const report={passed:true,job,revision:reopened.revision,figure_bytes:Buffer.byteLength(JSON.stringify(before.scene)),save_request_bytes:size,
  save_response_bytes:Buffer.byteLength(JSON.stringify(saved)),save_ms:elapsed,command_count:operations.length,real_http_save:true,reopen_verified:true,all_objects_preserved:true};
await writeFile(output,JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
