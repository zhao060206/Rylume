/** Load every dependency before switching documents; the latest request wins. */
export function latestDocumentLoader({canLeave,load,apply,onError,readVersion=()=>null}){
 let epoch=0;
 return async function open(id){
  const request=++epoch,current=()=>request===epoch;
  try{
   if(!await canLeave()||!current())return false;
   for(let attempt=0;attempt<4;attempt++){
    const version=readVersion(),result=await load(id);
    if(!current())return false;
    // A flush after loading can advance HEAD, including the document being
    // reopened. Refetch instead of applying the pre-save revision.
    if(!await canLeave()||!current())return false;
    if(readVersion()!==version)continue;
    await apply(result,current);return current();
   }
   throw Error('图版仍在持续修改，请完成当前编辑后重新打开');
  }catch(error){if(current())onError(error);return false;}
 };
}
