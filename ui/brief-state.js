/** Keep authored science separate from visual wording, including repeated edits. */
export function originalBrief(state,text){return state.enhancedFrom?state.originalBrief||'':text;}
export function acceptEnhancement(state, original, text){
 state.originalBrief=original;state.enhancedFrom=original;state.enhancedBrief=text;
}
export function authorBrief(state,text){
 state.originalBrief=text;state.enhancedFrom=null;state.enhancedBrief=null;
}
export function generationBrief(state,text){
 return state.enhancedFrom&&state.enhancedBrief?state.enhancedBrief:text;
}
export function briefSnapshot(state,text,context={}){
 return {id:state.id??null,text,original:originalBrief(state,text),enhanced:state.enhancedBrief??null,context};
}
export function sameBriefSnapshot(snapshot,state,text,context={}){
 return JSON.stringify(snapshot)===JSON.stringify(briefSnapshot(state,text,context));
}
