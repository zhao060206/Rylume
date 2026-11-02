/** Durable recovery copies are independent of server HEAD and never overwrite it. */
import {copySceneData} from './scene-data.js';
// Stop inspecting as soon as the synchronous-storage budget is exhausted.
function smallRecord(value,budget=256*1024){
  const visit=v=>{if(budget<0)return;if(typeof v==='string')budget-=v.length*2;else if(v&&typeof v==='object')for(const [k,item]of Object.entries(v)){budget-=k.length*2+8;visit(item);if(budget<0)break;}else budget-=16;};visit(value);return budget>=0;
}
export class DraftStore{
  constructor(storage=globalThis.localStorage){this.storage=storage;this.chain=Promise.resolve();this.pending=new Map();}
  key(id){return 'rylume-scene-draft-'+id;}
  async database(){
    if(!globalThis.indexedDB)return null;
    return new Promise((resolve,reject)=>{const r=indexedDB.open('rylume-recovery',1);r.onupgradeneeded=()=>r.result.createObjectStore('drafts',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
  }
  async transaction(mode,work){const db=await this.database();if(!db)return undefined;try{return await new Promise((resolve,reject)=>{const tx=db.transaction('drafts',mode),request=work(tx.objectStore('drafts'));let result;request.onsuccess=()=>result=request.result;tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}}
  write(record){
    const snapshot=copySceneData(record);snapshot.updated_at=Date.now();this.pending.set(record.id,snapshot);
    const asynchronousOnly=globalThis.indexedDB&&!smallRecord(snapshot);
    let synchronous=false;try{if(!asynchronousOnly){this.storage?.setItem(this.key(record.id),JSON.stringify(snapshot));synchronous=!!this.storage;}}catch{}
    this.chain=this.chain.catch(()=>{}).then(async()=>{
      if(this.pending.get(record.id)!==snapshot)return;
      try{if(!globalThis.indexedDB&&!synchronous)throw Error('恢复存储不可用');await this.transaction('readwrite',s=>s.put(snapshot));if(asynchronousOnly&&this.pending.get(record.id)===snapshot)try{this.storage?.removeItem(this.key(record.id));}catch{}}catch(e){if(!synchronous)throw e;}
      finally{if(this.pending.get(record.id)===snapshot)this.pending.delete(record.id);}
    });return this.chain;
  }
  async read(id){let cached;try{cached=JSON.parse(this.storage?.getItem(this.key(id))||'null');}catch{}try{await this.chain;const stored=await this.transaction('readonly',s=>s.get(id));return (stored?.updated_at||0)>(cached?.updated_at||0)?stored:cached;}catch{return cached;}}
  clear(id){this.pending.delete(id);try{this.storage?.removeItem(this.key(id));}catch{}this.chain=this.chain.catch(()=>{}).then(()=>this.transaction('readwrite',s=>s.delete(id)));return this.chain;}
}
