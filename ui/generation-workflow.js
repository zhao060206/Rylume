import {sanitizedSvg} from './canvas-editor.js';
import {setupSketchPad} from './sketch-pad.js';

/** Generation has one document model; references and sketches are first-class inputs. */
export function setupGenerationWorkflow({state,editor,api,flush,follow,canLeave,workspace,checkModels,toast,tab}){
 const $=id=>document.getElementById(id);let preview=null,version=0,busy=false,referenceEpoch=0;
 function invalidate(){version++;preview=null;}
 function status(text){$('generation-inline-status').textContent=text;}
 function refresh(){
  $('generation-origin-card').hidden=!state.enhancedFrom;
  if(document.activeElement!==$('generation-original-input'))$('generation-original-input').value=state.originalBrief||'';
  $('use-canvas-sketch').disabled=!editor.scene?.objects?.length||!!state.active;
  $('canvas-sketch-card').hidden=!state.sketchSource;
  if(state.sketchSource)$('canvas-sketch-note').textContent='使用画布草稿 · '+(state.sketchSource.title||state.sketchSource.id)+' · 位置和连接保持';
  $('generation-reference-card').hidden=!state.referenceId;
 }
 function removeReference(){referenceEpoch++;$('upload-sketch').disabled=false;state.referenceId=null;state.reference=null;state.referencePurpose='layout';$('reference-file').value='';$('reference-status').hidden=true;$('remove-reference').hidden=true;$('generation-reference-preview').removeAttribute('src');invalidate();refresh();}
 async function upload(image,purpose='layout'){
  const epoch=++referenceEpoch;status('正在保留原图并识别对象与位置…');$('upload-sketch').disabled=true;
  try{const result=await api('/api/references',{image,purpose,text:$('brief-input').value});if(epoch!==referenceEpoch)return;
   state.referenceId=result.reference_id;state.reference=result.style_dna;state.referencePurpose=purpose;state.sketchSource=null;
   $('generation-reference-preview').src=result.preview_url;$('reference-purpose').value=purpose;
   $('generation-reference-note').textContent=result.reference_contract?.summary||result.analysis_message||'原图已保存，生成时会提供原图。';
   status(result.analysis_status==='ready'?'已保留原图与识别布局。可以先看结构，也可以直接生成。':result.analysis_message||'原图已保存。');invalidate();refresh();tab('generate');
  }finally{if(epoch===referenceEpoch)$('upload-sketch').disabled=false;}
 }
 const paper=setupSketchPad({onUse:image=>upload(image,'sketch'),toast});
 $('draw-sketch').onclick=()=>paper.open();$('upload-sketch').onclick=$('reference-button').onclick=()=>$('reference-file').click();
 $('reference-file').onchange=async e=>{const file=e.target.files?.[0];if(!file)return;if(file.size>10*1024*1024)return toast('参考图请小于 10 MB');try{const image=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(file);});await upload(image,'layout');}catch(error){status('参考图未载入：'+error.message);toast(error.message,true);}};
 $('remove-reference').onclick=$('clear-generation-reference').onclick=removeReference;
 $('reference-purpose').onchange=e=>{state.referencePurpose=e.target.value;invalidate();};
 $('use-canvas-sketch').onclick=async()=>{if(!editor.scene?.objects.length)return toast('先在画布放置对象，写上名称并连接');if(!await flush())return;
  state.sketchSource={id:state.id,revision:state.revision,title:editor.scene.title};invalidate();refresh();status('草稿的位置、大小和连接将保持，AI 只细化对象。');};
 $('clear-canvas-sketch').onclick=()=>{state.sketchSource=null;invalidate();refresh();status('已移除画布草稿。');};
 $('brief-input').addEventListener('input',invalidate);
 $('brief-input').addEventListener('change',()=>{invalidate();refresh();});
 $('generation-original-input').oninput=e=>{state.originalBrief=e.target.value;state.enhancedFrom=e.target.value;invalidate();};
 for(const id of ['new-size','generation-dpi'])$(id).addEventListener('change',invalidate);
 document.querySelectorAll('[data-generation-mode]').forEach(b=>b.addEventListener('click',invalidate));
 async function payload(){
  if(state.sketchSource?.id===state.id){if(!await flush())throw Error('请先保存草稿');state.sketchSource.revision=state.revision;}
  return workspace.payload($('brief-input').value.trim());
 }
 async function run(previewOnly=false,fromPreview=false){
  if(busy||state.active)return;busy=true;state.submitting=true;$('generate').disabled=true;$('preview-generation').disabled=true;
  try{
   if(!await canLeave())return;if(!await checkModels(workspace.getMode()))return;
   const body=await payload();if(!body.text&&!body.sketch_job_id&&!body.reference_id)throw Error('写下研究内容，或上传/绘制一张带名称的草稿');
   if(previewOnly){const epoch=version;status('正在提取对象与关系，并按草稿保留布局…');const result=await api('/api/generation/preview',body);
    if(epoch!==version)throw Error('输入已变化，请重新查看结构预览');preview={id:result.preview_id,body,version:epoch};
    $('generation-preview-stage').replaceChildren(sanitizedSvg(result.svg));$('generation-preview-findings').replaceChildren();
    for(const text of result.unresolved||[]){const li=document.createElement('li');li.textContent=text;$('generation-preview-findings').append(li);}
    if(!result.unresolved?.length){const li=document.createElement('li');li.textContent='请核对科学内容；文字、图形和箭头在生成后仍可移动。';$('generation-preview-findings').append(li);}
    $('generation-preview-dialog').showModal();status('结构预览已就绪。');
   }else{
    if(fromPreview){if(!preview||preview.version!==version)throw Error('输入已变化，请重新查看结构预览');body.preview_id=preview.id;}
    status('正在生成可编辑对象…');$('generation-preview-dialog').close();const result=await api('/api/generate',body);await follow(result.job_id);preview=null;status('已保留生成版本。请在画布核对、拖动和修改。');
   }
  }catch(error){status(error.message);toast(error.message,true);}finally{busy=false;state.submitting=false;$('generate').disabled=false;$('preview-generation').disabled=false;refresh();}
 }
 $('generate').onclick=()=>run();$('preview-generation').onclick=()=>run(true);$('generate-from-preview').onclick=()=>run(false,true);
 let redrawSnapshot=null;
 $('redraw-object-submit').onclick=async()=>{
  if(busy||state.active||!redrawSnapshot)return;const button=$('redraw-object-submit');button.disabled=true;
  try{if(!await checkModels('image'))return;if(!await flush())return;
   if(state.id!==redrawSnapshot.id||state.revision!==redrawSnapshot.revision)throw Error('图版已变化，请重新选择要重绘的对象');
   const instruction=$('redraw-object-instruction').value.trim();if(!instruction)throw Error('请填写重绘要求');
   const result=await api(`/api/jobs/${state.id}/redraw`,{base_revision:state.revision,target_ids:redrawSnapshot.ids,instruction,request_id:crypto.randomUUID()});$('redraw-object-dialog').close();await follow(result.job_id);
  }catch(error){toast(error.message,true);}finally{button.disabled=false;}
 };
 return {refresh,invalidate,async redraw(){if(!await flush())return;const ids=editor.selectedIds.filter(id=>editor.scene.objects.some(o=>o.id===id&&o.type!=='text'&&!o.locked));if(!ids.length)return toast('先选择要重绘的图形');redrawSnapshot={id:state.id,revision:state.revision,ids};$('redraw-object-instruction').value='';$('redraw-object-dialog').showModal();},async opened(scene){
  invalidate();
  const openedEpoch=++referenceEpoch;$('upload-sketch').disabled=false;const openedId=state.id;
  const contract=scene?.generation_contract||{};
  if(contract.original_text){state.originalBrief=contract.original_text;state.enhancedFrom=contract.generation_brief!==state.originalBrief?state.originalBrief:null;$('brief-input').value=contract.generation_brief||contract.original_text;$('brief-count').textContent=$('brief-input').value.length+' / 8000';}
  if(state.sketchSource&&state.sketchSource.id!==state.id)state.sketchSource=null;
  if(contract.reference_id&&contract.reference_id!==state.referenceId){
   try{const result=await api('/api/references/'+contract.reference_id);if(state.id!==openedId||referenceEpoch!==openedEpoch)return;state.referenceId=result.reference_id;state.reference=result.style_dna;state.referencePurpose=contract.reference_purpose||result.purpose;$('generation-reference-preview').src=result.preview_url;$('reference-purpose').value=state.referencePurpose;$('generation-reference-note').textContent=result.reference_contract?.summary||'原图已保存';}catch{if(state.id===openedId&&referenceEpoch===openedEpoch){removeReference();status('当前图版的参考原图暂不可用。');}}
  }else if(!contract.reference_id&&state.referenceId)removeReference();
  else if(contract.reference_id){state.referencePurpose=contract.reference_purpose||state.referencePurpose;$('reference-purpose').value=state.referencePurpose;}
  refresh();
 }};
}
