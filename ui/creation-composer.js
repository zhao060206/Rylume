/** A single creation surface for home, menus, the rail, references and sketches. */
export function setupCreationComposer({state,toast,workflow,workspace}){
 const $=id=>document.getElementById(id),dialog=$('creation-dialog'),input=$('brief-input'),composer=$('panel-generate'),home=$('home-composer-host');
 let selectedExample=null,homeDraft=null,inlineMounted=null,submission=null;
 function snapshot(){return {text:input.value,originalBrief:state.originalBrief,enhancedFrom:state.enhancedFrom,enhancedBrief:state.enhancedBrief,
  referenceId:state.referenceId,reference:state.reference,referencePurpose:state.referencePurpose,layoutPolicy:state.layoutPolicy,sketchSource:state.sketchSource,
  preview:$('generation-reference-preview').getAttribute('src'),note:$('generation-reference-note').textContent,
  size:$('new-size').value,dpi:$('generation-dpi').value,mode:workspace.getMode()};}
 function restore(){
  const d=homeDraft||{text:'',size:'180x120',dpi:'300',mode:'vector'};
  input.value=d.text;state.originalBrief=d.originalBrief||d.text;state.enhancedFrom=d.enhancedFrom||null;state.enhancedBrief=d.enhancedBrief||null;
  $('new-size').value=d.size;$('generation-dpi').value=d.dpi;$('creation-size-summary').textContent=d.size.replace('x',' × ')+' mm';
  workspace.setMode(d.mode);workflow.restoreInputs(d);input.dispatchEvent(new Event('change'));
 }
 const examples={
  signal:'画一张 JAK–STAT 信号通路图：细胞因子结合膜上的受体，激活 JAK，再激活 STAT。STAT 进入细胞核，调控基因表达。区分胞外、细胞质和细胞核；箭头标明激活与转运。',
  workflow:'画一张实验流程图：样本采集 → 样本预处理 → 测量 → 数据分析。按从左到右的顺序排列，每一步配一个简洁图形和名称。保留步骤间的顺序，不添加未说明的实验条件。',
  cycle:'画一张动物细胞有丝分裂的循环过程图：间期、前期、前中期、中期、后期、末期、胞质分裂。顺时针排列，用箭头连接。每个阶段表现对应的细胞状态，标注阶段名称。'
 };
 function mount(){
  const inline=!$('welcome').hidden;
  if(inline&&dialog.open)dialog.close();
  const target=inline?home:dialog;
  if(composer.parentElement!==target)target.append(composer);
  composer.classList.toggle('home-inline',inline);
  if(inline&&inlineMounted===false)restore();
  inlineMounted=inline;
 }
 function open(){
  mount();
  // Home is ready to type; the same inputs open in a dialog during editing.
  if($('welcome').hidden&&!dialog.open)dialog.showModal();
  input.focus({preventScroll:true});
 }
 $('close-creation').onclick=()=>dialog.close();
 composer.addEventListener('keydown',e=>{
  if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.isComposing){e.preventDefault();$('generate').click();}
 });
 $('composer-attach').onclick=()=>{const expanded=composer.classList.toggle('references-expanded');$('composer-attach').setAttribute('aria-expanded',String(expanded));};
 new MutationObserver(mount).observe($('welcome'),{attributes:true,attributeFilter:['hidden']});mount();
 $('new-size').addEventListener('change',()=>{$('creation-size-summary').textContent=$('new-size').value.replace('x',' × ')+' mm';});
 for(const b of document.querySelectorAll('[data-prompt-example]'))b.onclick=()=>{
  selectedExample=examples[b.dataset.promptExample];
  for(const item of document.querySelectorAll('[data-prompt-example]'))item.setAttribute('aria-pressed',String(item===b));
  $('prompt-example-copy').textContent=selectedExample;$('prompt-example-copy').hidden=false;$('use-prompt-example').hidden=false;
 };
 $('use-prompt-example').onclick=()=>{
  if(!selectedExample)return;
  // The explicit apply action preserves existing research notes.
  input.value=(input.value.trim()?input.value.trim()+'\n\n':'')+selectedExample;
  input.value=input.value.slice(0,input.maxLength);input.dispatchEvent(new Event('input'));input.dispatchEvent(new Event('change'));input.focus();
 };
 const drop=$('upload-sketch');
 drop.addEventListener('dragover',e=>{e.preventDefault();if(!drop.disabled)drop.classList.add('drag-over');});
 drop.addEventListener('dragleave',()=>drop.classList.remove('drag-over'));
 drop.addEventListener('drop',e=>{
  e.preventDefault();drop.classList.remove('drag-over');if(drop.disabled)return;
  const file=e.dataTransfer?.files?.[0];if(!file)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type))return toast('请选择 PNG、JPG 或 WebP 图片',true);
  // Share the upload handler and its stale-read protection with the file picker.
  $('reference-file').onchange({target:{files:[file]}});
 });
 document.addEventListener('generation-submitted',()=>{submission={inline:!$('welcome').hidden,draft:snapshot()};});
 document.addEventListener('generation-presented',()=>{
  if(dialog.open)dialog.close();
  if(submission?.inline&&JSON.stringify(homeDraft)===JSON.stringify(submission.draft)){
   homeDraft=null;try{localStorage.removeItem('rylume-research-brief');}catch{}
  }
  submission=null;
 });
 input.addEventListener('change',()=>{$('brief-count').textContent=input.value.length+' / '+input.maxLength;});
 return {open,close:()=>dialog.close(),leavingHome(){if(!$('welcome').hidden)homeDraft=snapshot();}};
}
