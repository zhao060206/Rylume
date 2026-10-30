/** Keep authored science separate from visual wording, including repeated edits. */
export function originalBrief(state,text){return state.enhancedFrom?state.originalBrief||'':text;}
export function briefSnapshot(state,text,context={}){
 return {id:state.id??null,text,original:originalBrief(state,text),context};
}
export function sameBriefSnapshot(snapshot,state,text,context={}){
 return JSON.stringify(snapshot)===JSON.stringify(briefSnapshot(state,text,context));
}
