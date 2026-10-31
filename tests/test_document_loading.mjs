import assert from 'node:assert/strict';
import {latestDocumentLoader} from '../ui/document-loader.js';
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const pending=new Map(),applied=[],errors=[],saves=[];
let current='old',dirty=false;
const open=latestDocumentLoader({async canLeave(){saves.push(current);dirty=false;return true;},
 load(id){const wait=deferred();pending.set(id,wait);return wait.promise;},
 apply(result){assert.equal(dirty,false,'Edits made during loading must be flushed before switching');current=result;applied.push(result);},
 onError(error){errors.push(error.message);}});
const first=open('first');await Promise.resolve();
const second=open('second');await Promise.resolve();
assert.equal(current,'old','A partial response never changes the current document identity');
pending.get('second').resolve('second');await second;
pending.get('first').resolve('first');assert.equal(await first,false);
assert.deepEqual(applied,['second'],'A delayed earlier response never replaces a newer document');
const third=open('third');await Promise.resolve();dirty=true;
pending.get('third').resolve('third');assert.equal(await third,true);
assert.equal(current,'third');assert.equal(saves.at(-1),'second');
const broken=open('broken');await Promise.resolve();pending.get('broken').reject(Error('metadata unavailable'));
assert.equal(await broken,false);assert.equal(current,'third');assert.deepEqual(errors,['metadata unavailable']);
let revision=1,edited=false,loads=0,reopened;
const reopen=latestDocumentLoader({readVersion:()=>revision,async canLeave(){if(edited){revision++;edited=false;}return true;},
 async load(){loads++;const response={revision};if(loads===1)edited=true;return response;},
 apply(result){reopened=result;},onError(error){throw error;}});
assert.equal(await reopen('same-document'),true);assert.equal(loads,2);assert.equal(reopened.revision,2,'A reopen cannot apply a scene fetched before the last save');
console.log('Atomic document switching preserves edits, ignores stale responses and retains the current document on load failure');

let lessonActive=true;const delayedLesson=deferred();let lessonOpened=false;
const openLesson=latestDocumentLoader({canLeave:async()=>true,load:()=>delayedLesson.promise,apply(){lessonOpened=true;},onError(){throw Error('Cancelled loads should not show errors');}});
const lesson=openLesson('practice',{isCurrent:()=>lessonActive});await Promise.resolve();lessonActive=false;delayedLesson.resolve('practice');
assert.equal(await lesson,false);assert.equal(lessonOpened,false,'Dismissing a guide while its document loads keeps the current document');

const slowStartup=deferred();let initialApplied=false;
const restoreInitial=latestDocumentLoader({canLeave:async()=>true,load:()=>slowStartup.promise,apply(){initialApplied=true;},onError(){throw Error('Explicit home navigation should cancel quietly');}});
const startup=restoreInitial('previous-document');await Promise.resolve();restoreInitial.cancel();slowStartup.resolve('previous-document');
assert.equal(await startup,false);assert.equal(initialApplied,false,'A late startup response cannot replace an explicitly opened home screen');
