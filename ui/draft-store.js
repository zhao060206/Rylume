/** Durable recovery copies are independent of server HEAD and never overwrite it. */
export class DraftStore{
  constructor(storage=globalThis.localStorage){this.storage=storage;this.chain=Promise.resolve();}
  key(id){return 'rylume-scene-draft-'+id;}
  async database(){
    if(!globalThis.indexedDB)return null;
    return new Promise((resolve,reject)=>{const r=indexedDB.open('rylume-recovery',1);r.onupgradeneeded=()=>r.result.createObjectStore('drafts',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});
  }
  async transaction(mode,work){const db=await this.database();if(!db)return undefined;try{return await new Promise((resolve,reject)=>{const tx=db.transaction('drafts',mode),request=work(tx.objectStore('drafts'));let result;request.onsuccess=()=>result=request.result;tx.oncomplete=()=>resolve(result);tx.onerror=()=>reject(tx.error);tx.onabort=()=>reject(tx.error);});}finally{db.close();}}
  write(record){
    const snapshot=structuredClone(record);snapshot.updated_at=Date.now();
    let synchronous=false;try{this.storage?.setItem(this.key(record.id),JSON.stringify(snapshot));synchronous=!!this.storage;}catch{}
    this.chain=this.chain.catch(()=>{}).then(async()=>{try{if(!globalThis.indexedDB&&!synchronous)throw Error('恢复存储不可用');await this.transaction('readwrite',s=>s.put(snapshot));}catch(e){if(!synchronous)throw e;}});return this.chain;
  }
  async read(id){let cached;try{cached=JSON.parse(this.storage?.getItem(this.key(id))||'null');}catch{}try{await this.chain;const stored=await this.transaction('readonly',s=>s.get(id));return (stored?.updated_at||0)>(cached?.updated_at||0)?stored:cached;}catch{return cached;}}
  clear(id){try{this.storage?.removeItem(this.key(id));}catch{}this.chain=this.chain.catch(()=>{}).then(()=>this.transaction('readwrite',s=>s.delete(id)));return this.chain;}
}
