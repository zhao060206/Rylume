import {preserveCanvasView,syncPanelButtons} from './panel-layout.js';
/** Unified generation, model settings and inspection around the native canvas. */
export function canApplySavedScene({epoch,dirty,pending,gesture}){return epoch===dirty&&!pending&&!gesture;}
export function generationPayload({text,mode='vector',width=180,height=120,dpi=300,reference=null,literature=false,originalText,archetype}) {
  const base={text,original_text:originalText||text,canvas_mm:[width,height],dpi,style_dna:reference||{},request_id:crypto.randomUUID()};
  if(mode==='vector')return {...base,scene_engine:'v2',illustration_mode:'vector'};
  return {...base,illustration_mode:'image',canvas:[Math.round(width*dpi/25.4),Math.round(height*dpi/25.4)],literature,
    ...(archetype?{archetype}:{}),...(reference?.layout_analysis?{reference_layout:reference.layout_analysis}:{})};
}

export function modelPatch(values){
  const patch={};
  for(const key of ['text','image','vision']){
    const v=values[key];if(!v)continue;
    patch[key]={base_url:v.base_url.trim(),model:v.model.trim()};
    if(v.api_key)patch[key].api_key=v.api_key;
  }
  return patch;
}

export function historyMatches(job,query,filter){
  if(query&&!((job.title||'')+' '+job.id).toLowerCase().includes(query.toLowerCase()))return false;
  if(filter==='editable')return job.scene_engine==='v2';
  if(filter==='illustration')return job.scene_engine!=='v2';
  if(filter==='active')return ['queued','processing','running'].includes(job.status);
  return true;
}

export function setupWorkspace({state,editor,api,toast,flush,follow,tab,openJob,renderAudit,renderHistory,renderReview=()=>{}}){
  const $=id=>document.getElementById(id);
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  let modelConfig={},mode='vector',rightTab='properties',questions=[],answers={},wizardSource='',proposed=null,originalZoom=1;

  function showRight(name='properties',compact=true){
    $('workspace').dispatchEvent(new Event('workspace-panel-request'));
    preserveCanvasView(editor,()=>{
    rightTab=name;$('workspace').classList.remove('properties-hidden');
    if(innerWidth<1440)$('workspace').classList.add('left-collapsed');
    
    for(const n of document.querySelectorAll('[data-inspector]'))n.setAttribute('aria-selected',String(n.dataset.inspector===name));
    $('property-content').hidden=name!=='properties';$('inspector-review').hidden=name!=='review';$('inspector-task').hidden=name!=='task';
    });syncPanelButtons($('workspace'));
    refresh();
  }
  document.querySelectorAll('[data-inspector]').forEach(b=>b.onclick=()=>showRight(b.dataset.inspector));
  $('toggle-properties').onclick=()=>{if(rightTab==='properties'&&!$('workspace').classList.contains('properties-hidden')){preserveCanvasView(editor,()=>$('workspace').classList.add('properties-hidden'));syncPanelButtons($('workspace'));}else showRight('properties',false);};
  $('open-audit').onclick=()=>showRight('review');
  $('process-check').onclick=()=>showRight('review');
  $('process-create').onclick=()=>tab('generate');
  $('process-edit').onclick=()=>showRight('properties');
  $('process-export').onclick=()=>$('toggle-export').click();
  $('history-filter').onchange=renderHistory;

  function setMode(next){
    mode=next==='image'?'image':'vector';
    for(const b of document.querySelectorAll('[data-generation-mode]'))b.setAttribute('aria-pressed',String(b.dataset.generationMode===mode));
    $('generation-mode-note').textContent=mode==='vector'?'图形、文字和连线都能单独修改。':'由 AI 绘制插画，单独编辑图中对象的能力取决于生成结果。';
    $('image-options').hidden=mode!=='image';$('generate').textContent=mode==='vector'?'生成可编辑初稿':'生成 AI 插画';
    document.querySelector('.input-meta span:last-child').textContent=mode==='vector'?'原生矢量':'AI 科研插画';
    $('brief-input').maxLength=mode==='vector'?8000:4000;
    $('brief-count').textContent=`${$('brief-input').value.length} / ${$('brief-input').maxLength}`;
  }
  document.querySelectorAll('[data-generation-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.generationMode));

  function refresh(){
    const job=state.currentJob||state.jobs.find(j=>j.id===state.id),a=state.audit;
    $('properties').querySelector('h2').textContent=rightTab==='review'?'排版与内容建议':rightTab==='task'?'任务与来源':editor.selectedIds.length?'所选对象属性':'图版设置';
    $('document-kind').textContent=state.revision?'可编辑图版':state.id?'插画 / 历史图版':'新建图版';
    $('process-status').textContent=state.conflict?'版本冲突 · 本机恢复副本已保留':state.saveError?'保存未完成 · 等待重试，恢复副本保留':state.active?'正在生成 · 可继续查看已有图版':state.revision?(state.pending.length||state.saving?'正在自动保存…':`已自动保存 · ${editor.selectedIds.length} 个所选对象`):state.id?'原图预览 · 可导出或重建可编辑副本':'选择创作方式，或从模板开始';
    document.querySelector('.process-bar').classList.toggle('generating',!!state.active);
    $('process-edit').disabled=!state.id;$('process-check').disabled=!state.id;$('process-export').disabled=!state.id;
    renderReview();
    const task=$('inspector-task');task.replaceChildren();
    if(!state.id){task.append(el('p','muted','生成方式、任务进度和原始描述会显示在这里。'));return;}
    task.append(el('h3','',job?.title||editor.scene?.title||'当前图版'),el('p','muted small',state.id));
    if(job?.stages?.length){const stages=el('ol','task-stages');for(const s of job.stages){stages.append(el('li',s.state==='done'?'done':'',s.label||s.name||s.title||s.id||s.stage));}task.append(stages);}
    const brief=el('details','task-brief');brief.append(el('summary','','原始研究描述'),el('p','muted small',job?.original_text||job?.text||editor.scene?.source_text||'未填写'));task.append(brief);
    const folder=el('button','button full secondary','打开任务文件夹');folder.onclick=()=>api('/api/open-folder',{kind:'job',job_id:state.id}).catch(e=>toast(e.message,true));task.append(folder);
    if(!state.revision){
      const copy=el('button','button primary full','重建为可编辑图版');copy.onclick=()=>rebuild();task.append(copy,el('p','muted small','根据原始描述重新规划，原图和历史任务保留。'));
      const revise=el('button','button full','AI 修改原图');revise.disabled=!!job?.report?.raster;
      revise.title=revise.disabled?'整幅位图请调整描述后重新生成':'通过原有修订服务创建新任务';
      revise.onclick=()=>{$('original-revise-text').value='';$('original-revise-dialog').showModal();};task.append(revise);
    }
  }
  async function rebuild(){if(state.active)return toast('已有生成任务，请等待完成或先取消');try{if(!await flush()&&state.revision)return;await follow((await api(`/api/jobs/${state.id}/editable-copy`,{})).job_id);}catch(e){toast(e.message,true);}}
  $('original-revise-submit').onclick=async()=>{
    const instruction=$('original-revise-text').value.trim();if(!instruction)return;
    const b=$('original-revise-submit');b.disabled=true;
    try{const result=await api(`/api/jobs/${state.id}/revise`,{instruction});$('original-revise-dialog').close();await follow(result.job_id);}catch(e){toast(e.message,true);}finally{b.disabled=false;}
  };

  function field(parent,label,value,type='text'){
    const wrapper=el('label','settings-field',label),input=el('input');input.type=type;input.value=value||'';input.autocomplete='off';input.setAttribute('aria-label',label);wrapper.append(input);parent.append(wrapper);return input;
  }
  let modelInputs={},advancedInputs={};
  function settingsValues(){return Object.fromEntries(Object.entries(modelInputs).map(([key,v])=>[key,Object.fromEntries(Object.entries(v).map(([name,n])=>[name,n.value]))]));}
  function settingsPatch(){
    const patch=modelPatch(settingsValues()),v=advancedInputs;
    if(v.engine)patch.vectorize={engine:v.engine.value};
    if(v.render)patch.render_mode=v.render.value;
    if(v.quality)patch.quality=v.quality.value;
    if(v.font)patch.font=v.font.value.trim()||'Arial';
    if(v.ocr)patch.ocr={mode:v.ocr.value};
    return patch;
  }
  async function settings(){
    $('model-status').textContent='正在读取配置…';$('models-dialog').showModal();
    try{
      modelConfig=(await api('/api/state')).config||{};const body=$('model-settings');body.replaceChildren();modelInputs={};
      for(const [key,title,role] of [['text','文本模型','机制规划与 AI 修改'],['image','生图模型','科研插画与素材生成'],['vision','视觉模型','参考图分析与视觉审阅']]){
        const item=modelConfig[key]||{},section=el('section','settings-group');section.append(el('h3','',title),el('p','muted small',role));
        modelInputs[key]={base_url:field(section,`${title}服务地址`,item.base_url),model:field(section,`${title}名称`,item.model),api_key:field(section,`${title}密钥`,'','password')};
        modelInputs[key].api_key.placeholder=item.api_key_set?'已保存，留空保持不变':'粘贴 API Key';
        const test=el('button','button secondary','测试连接'),status=el('span','connection-result','尚未测试');
        test.onclick=async()=>{test.disabled=true;status.textContent='测试中…';try{const r=await api('/api/test',{target:key,config:settingsPatch()});status.textContent=r.configured===false?'尚未配置':r.ok?'连接正常':r.error||'连接失败';}catch(e){status.textContent=e.message;}finally{test.disabled=false;}};
        section.append(test,status);body.append(section);
      }
      const advanced=el('details','advanced-model-settings');advanced.append(el('summary','','高级插画与输出设置'));
      const grid=el('div','advanced-settings-grid');advancedInputs={};
      for(const [key,title,value,options] of [
        ['engine','插画素材矢量化',modelConfig.vectorize?.engine||'hifi',[['hifi','高保真自动'],['vtracer','快速矢量化'],['starvector','StarVector']]],
        ['render','插画生成方式',modelConfig.render_mode||'compose',[['compose','素材装配'],['fidelity','保真优先'],['vector','整图矢量化']]],
        ['quality','插画质量',modelConfig.quality||'hd',[['hd','高清'],['standard','标准']]],
        ['ocr','插画文字识别',typeof modelConfig.ocr==='string'?modelConfig.ocr:modelConfig.ocr?.mode||'auto',[['auto','自动'],['off','关闭']]]]){
        const label=el('label','settings-field',title),select=el('select');select.setAttribute('aria-label',title);
        for(const [v,t] of options){const o=el('option','',t);o.value=v;select.append(o);}select.value=value;label.append(select);grid.append(label);advancedInputs[key]=select;
      }
      advancedInputs.font=field(grid,'插画导出字体',modelConfig.font||'Arial');advanced.append(grid);body.append(advanced);
      $('model-status').textContent='三种模型与原有服务配置共用，留空的密钥不会覆盖已保存值。';
    }catch(e){$('model-status').textContent=e.message;}
  }
  $('open-settings').onclick=settings;$('empty-model-settings').onclick=settings;
  $('save-model-settings').onclick=async()=>{
    const b=$('save-model-settings');b.disabled=true;
    try{await api('/api/config',settingsPatch());$('models-dialog').close();toast('模型设置已保存');}catch(e){$('model-status').textContent=e.message;}finally{b.disabled=false;}
  };

  async function busy(button,work){button.disabled=true;try{await work();}catch(e){toast(e.message,true);}finally{button.disabled=false;}}
  $('expand-brief').onclick=()=>busy($('expand-brief'),async()=>{
    const text=$('brief-input').value.trim();if(!text)return toast('先写一句研究构想');
    const r=await api('/api/optimize',{text,canvas:[1800,1200]});
    proposed={text:r.text||text,original:text};$('brief-candidate').value=proposed.text;$('brief-preview-dialog').showModal();
  });
  $('use-expanded-brief').onclick=()=>{if(!proposed)return;$('brief-input').value=$('brief-candidate').value.slice(0,8000);$('brief-input').dispatchEvent(new Event('input'));state.originalBrief=proposed.original;$('brief-preview-dialog').close();toast('扩写已放入研究描述，可继续修改');};

  function wizardFields(){
    const list=$('guide-questions');list.replaceChildren();
    for(const q of questions){
      const group=el('fieldset','guide-question');group.append(el('legend','',q.title));
      for(const option of q.options||[]){
        const row=el('label','guide-option'),radio=el('input');radio.type='radio';radio.name=q.id;radio.value=option.value;radio.checked=answers[q.id]===option.value;
        radio.onchange=()=>answers[q.id]=option.value;const text=el('span');text.append(el('strong','',option.label),el('small','',option.desc||''));row.append(radio,text);group.append(row);
      }
      list.append(group);
    }
  }
  $('open-guide').onclick=()=>{
    $('guide-seed').value=$('brief-input').value;$('guide-dialog').showModal();$('guide-result').hidden=true;$('guide-status').textContent='先描述要表达的科学内容，再让 AI 提出必要选项。';
  };
  $('guide-load').onclick=()=>busy($('guide-load'),async()=>{
    wizardSource=$('guide-seed').value.trim();if(!wizardSource)return toast('先填写研究内容');
    $('guide-status').textContent='正在读取研究描述…';
    const r=await api('/api/assist/clarify',{text:wizardSource,style_dna:state.reference||null});questions=r.data?.questions||[];
    if(!questions.length)throw Error('未返回引导选项，请直接编辑研究描述');
    answers={};for(const q of questions)answers[q.id]=((q.options||[]).find(o=>o.recommended)||q.options?.[0])?.value;
    wizardFields();$('guide-compose').hidden=false;$('guide-status').textContent='核对下面的选项，再生成描述。';
  });
  $('guide-compose').onclick=()=>busy($('guide-compose'),async()=>{
    const result=await api('/api/assist/compose-prompt',{text:wizardSource,answers,style_dna:state.reference||null});
    if(!result.enhanced_text)throw Error('未返回描述，请稍后重试');
    state.archetype=answers.archetype;$('guide-output').value=result.enhanced_text;$('guide-result').hidden=false;$('guide-status').textContent='候选尚未应用；请检查对象和关系。';
  });
  $('guide-use').onclick=()=>{$('brief-input').value=$('guide-output').value.slice(0,8000);$('brief-input').dispatchEvent(new Event('input'));state.originalBrief=wizardSource;$('guide-dialog').close();tab('generate');toast('引导描述已应用，请检查后生成');};
  $('remove-reference').onclick=()=>{state.reference=null;$('remove-reference').hidden=true;$('reference-status').hidden=true;$('reference-file').value='';toast('已移除本次构图参考');};
  $('show-all-templates').onclick=()=>$('welcome-gallery').click();
  function legacyZoom(value,factor=1){
    if(state.revision)return;
    originalZoom=Math.max(.2,Math.min(5,value??originalZoom*factor));
    const art=$('legacy-art');if(art){art.style.width=`${Math.max(260,editor.host.clientWidth-80)*originalZoom}px`;art.style.height='auto';}
    $('zoom-100').textContent=Math.round(originalZoom*100)+'%';
  }
  editor.host.addEventListener('wheel',e=>{if(!state.revision&&$('legacy-art')){e.preventDefault();legacyZoom(null,e.deltaY<0?1.1:1/1.1);}},{passive:false});
  setMode('vector');refresh();
  return {refresh,showRight,setMode,legacyZoom,getMode:()=>mode,selection(){refresh();},payload(text){
    if(mode==='image'&&text.length>4000)throw Error('科研插画描述请控制在 4000 字以内；当前描述已保留。');
    const [width,height]=$('new-size').value.split('x').map(Number);
    return generationPayload({text,mode,width,height,dpi:Number($('generation-dpi').value),reference:state.reference,literature:$('generation-literature').checked,originalText:state.originalBrief,archetype:state.archetype});
  }};
}
