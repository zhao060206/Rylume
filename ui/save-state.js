/** One source of truth for saving, navigation and restart safety. */
export function documentSaveState(state){
  const pending=state?.pending?.length||0;
  if(state?.saving)return {kind:'saving',label:'正在保存…'};
  if(state?.inlineEditing)return {kind:'dirty',label:'文字待保存'};
  if(pending&&state?.conflict)return {kind:'conflict',label:'版本冲突 · 请另存副本'};
  if(pending&&state?.saveError)return {kind:'error',label:'保存失败 · 点击重试'};
  if(pending)return {kind:'dirty',label:'有修改待保存'};
  if(!state?.id)return {kind:'empty',label:'无需保存'};
  if(!state?.revision)return {kind:'readonly',label:'原图已保留'};
  return {kind:'saved',label:'已保存到本机'};
}

export async function saveBeforeDestructiveAction(state,flush){
  // Home and saved original-image previews have no scene operations to save.
  if(!state?.pending?.length&&!state?.saving&&!state?.inlineEditing)return true;
  const id=state?.id;
  if(!id)return false;
  const ok=await flush();
  return !!ok&&state.id===id&&!state.saving&&!state.inlineEditing&&!state.pending.length;
}

/** Drain all edits, including edits made while a PATCH is in flight. Concurrent
 * save callers share a promise; an earlier successful batch is never mistaken
 * for a fully saved document. Failed batches remain in order for recovery. */
export function createDocumentSaver({state,write,status=()=>{},applied=()=>{},failed=()=>{},settled=()=>{},changed=()=>{}}){
  let inFlight=null;
  function flush(){
    clearTimeout(state.timer);
    if(inFlight)return inFlight;
    if(!state.pending.length)return Promise.resolve(true);
    if(!state.id||!state.revision||state.conflict)return Promise.resolve(false);
    const id=state.id;
    state.saving=true;status('正在保存…',true);
    inFlight=(async()=>{
      let ok=false;
      try{
        while(state.pending.length){
          if(state.id!==id||state.conflict)return false;
          const batch=state.pending.splice(0),epoch=state.dirty;
          let data;
          try{
            data=await write(id,state.revision,batch);
          }catch(error){
            if(state.id===id){state.pending.unshift(...batch);failed(error);}
            return false;
          }
          if(state.id!==id)return false;
          state.revision=data.revision;state.audit=data.audit;state.svg=data.svg;
          state.saveError=null;state.saveFailures=0;
          // Rendering is separate from persistence. Never replay an acknowledged
          // add/remove operation if updating the preview raises a UI error.
          try{applied(data,epoch);}catch(error){failed(error);return false;}
        }
        ok=state.id===id&&!state.pending.length;
        if(ok)status('已保存 · r'+state.revision);
        return ok;
      }finally{
        state.saving=false;inFlight=null;
        if(ok)settled();
        changed();
        if(state.id===id&&state.pending.length&&!state.conflict){
          clearTimeout(state.timer);
          state.timer=setTimeout(flush,Math.min(30000,1000*2**Math.min(state.saveFailures||0,5)));
        }
      }
    })();
    return inFlight;
  }
  return {flush};
}
