import {setupFloatingWindows,showFloatingWindow} from './floating-windows.js';
import {setupPersonalAssets} from './personal-assets.js';
import {setupReleaseNotes} from './release-notes.js';
import {setupDocumentAssistant} from './document-assistant.js';
import {setupOnboarding} from './onboarding.js';
import {setupWorkspaceNavigation} from './workspace-navigation.js';
import {creationProject} from './project-ui.js';
import {setupNovice} from './novice-guidance.js';
import {setupCreationComposer} from './creation-composer.js';
import {authorBrief} from './brief-state.js';
import {setupGenerationWorkflow} from './generation-workflow.js';
import {latestDocumentLoader} from './document-loader.js';
import {setupWorkspaceModes} from './workspace-modes.js';
import {preserveCanvasView,syncPanelButtons} from './panel-layout.js';
import {setupDocumentWorkflows} from './document-workflows.js';
import {setupDelivery} from './delivery-ui.js';
import {createDocumentSaver} from './save-state.js';
import {setupSaveControls} from './save-ui.js';
import {setupAnnotations} from './annotation-ui.js';
import {setupRelations,relationChoices} from './relation-ui.js';
import {RELATION_DEFINITIONS} from './canvas-editor.js';
import {setupReview} from './review-ui.js';
import {setupWorkspace,historyMatches,canApplySavedScene} from './workspace-ui.js';
import {setupWorkbench} from './editor-workbench.js';
import {setupLibrary} from './library-ui.js';
import {SceneEditor,sanitizedSvg} from './canvas-editor.js';
import {installUiContract} from './ui-contract.js';
const $=id=>document.getElementById(id),clone=x=>JSON.parse(JSON.stringify(x));
const S={id:null,revision:0,jobs:[],assets:[],examples:[],audit:null,svg:'',pending:[],saving:false,dirty:0,inlineEditing:false,conflict:false,timer:null,reference:null,candidate:null,active:null};
let startupNavigationCancelled=false;
const ws=$('workspace');
const floatingWindows=setupFloatingWindows();
new MutationObserver(()=>syncPanelButtons(ws)).observe(ws,{attributes:true,attributeFilter:['class']});
new MutationObserver(()=>syncPanelButtons(ws)).observe($('asset-library-dialog'),{attributes:true,attributeFilter:['open','class']});
let workspaceUI,workbenchUI,reviewUI,relationsUI,annotationUI,documentUI,deliveryUI,noviceUI,modesUI,generationUI,composerUI,navigationUI,onboardingUI,documentsUI;
function el(tag,cls,text){const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;}
let toastTimer;function toast(message,error=false){$('toast').textContent=message;$('toast').className='toast'+(error?' error':'');$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,4500);}
async function api(path,body,method){
 const creation=body?creationProject(path,S):null;
 const controller=new AbortController(),timer=(method==='PATCH'||path==='/api/updates/apply')?setTimeout(()=>controller.abort(),30000):null;let response,data;
 try{response=await fetch(path,{method:method||(body?'POST':'GET'),headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,signal:controller.signal});
  try{data=await response.json();}catch{throw Error(`本机服务返回异常（HTTP ${response.status}），修改已保留，请重试保存。`);}
 }catch(error){if(error.name==='AbortError')throw Error('连接本机服务超时，修改已保留。请重试保存或另存副本。');throw error;}finally{clearTimeout(timer);}
 if(!response.ok||data.ok===false){const error=new Error(data.error||'请求未完成');error.status=response.status;error.data=data;throw error;}
 if(data.job_id&&creation?.projectId&&data.job_id!==creation.parentId&&navigationUI){try{await navigationUI.attachNew(data.job_id,creation.projectId);}catch(error){toast('图版已创建，但归入项目未成功：'+error.message,true);}}
 return data;
}
function saveStatus(text,dirty=false){$('save-status').title=text;$('save-status').textContent=text;$('save-status').classList.toggle('dirty',dirty);document.dispatchEvent(new Event('document-save-state'));}
function showError(error){S.saveError=error.message==='Failed to fetch'?'暂时连接不上本机服务。修改已留在恢复副本中，可以重试或另存图版。':error.message;S.saveFailures=(S.saveFailures||0)+1;documentUI?.changed();$('error-banner').hidden=false;$('error-text').textContent=S.saveError;S.conflict=error.status===409;saveStatus(S.conflict?'版本冲突 · 恢复副本保留':'保存未完成 · 恢复副本保留',true);}
const editor=new SceneEditor({host:$('canvas-host'),onChange(operations){S.pending.push(...clone(operations));S.dirty++;documentUI?.changed();saveStatus('正在编辑 · 待保存',true);clearTimeout(S.timer);S.timer=setTimeout(()=>saver.flush(),500);renderTools();renderLayers();renderProperties();onboardingUI?.refresh();},onSelection(){noviceUI?.selection();renderProperties();renderLayers();workspaceUI?.selection();if(editor.selectedIds.length)editor.fitMode=false;renderTools();onboardingUI?.refresh();},onZoom(value){$('zoom-100').textContent=Math.round(value*100)+'%';},onStatus:toast});
const saver=createDocumentSaver({state:S,status:saveStatus,
 write:(id,revision,operations)=>api('/api/jobs/'+id+'/scene',{base_revision:revision,operations},'PATCH'),
 applied(data,epoch){if(canApplySavedScene({epoch,dirty:S.dirty,pending:S.pending.length,gesture:editor.gesture||editor.finishEditing}))editor.updateDocument(data.scene,data.svg);$('error-banner').hidden=true;renderAudit();workspaceUI?.refresh();},
 failed:showError,settled(){documentUI?.saved();},changed(){workspaceUI?.refresh();document.dispatchEvent(new Event('document-save-state'));}
});
async function flush(){editor.finishEditing?.();return saver.flush();}
const saveControls=setupSaveControls({state:S,flush,toast});
async function canLeave(){return !S.pending.length&&!S.saving&&!S.inlineEditing||await flush();}
async function refreshJobs(){S.jobs=(await api('/api/jobs?limit=1000')).jobs||[];await navigationUI?.refresh();renderHistory();navigationUI?.render();}
const loadDocument=latestDocumentLoader({canLeave,readVersion:()=>S.id+':'+S.revision,onError:error=>toast(error.message,true),async load(id){
 let data,legacy=false,svg='';
 try{data=await api(`/api/jobs/${id}/scene`);}catch(error){if(!error.data?.legacy)throw error;legacy=true;}
 const job=S.jobs.find(j=>j.id===id)||await api(`/api/jobs/${id}`);
 if(legacy&&job.svg_url){const response=await fetch(job.svg_url);if(!response.ok)throw Error('原图文件暂不可用');svg=await response.text();}
 return {id,data,job,legacy,svg};
},async apply({id,data,job,legacy,svg},current){
 if(legacy)return openLegacy(job,svg);
 S.id=id;S.currentJob=job;S.revision=data.revision;S.svg=data.svg;S.audit=data.audit;S.pending=[];S.conflict=false;S.saveError=null;S.saveFailures=0;S.dirty=0;
 $('error-banner').hidden=true;$('canvas-host').classList.remove('legacy-preview');$('canvas-hint').textContent='V 选择 · H 平移 · C 连线 · 双击改字';editor.setDocument(data.scene,data.svg);
 $('welcome').hidden=true;$('toggle-export').disabled=false;$('project-title').textContent=data.scene.title;$('brief-input').value=data.scene.source_text;authorBrief(S,data.scene.source_text);updateCount();
 $('canvas-size').textContent=`${data.scene.canvas.width_mm} × ${data.scene.canvas.height_mm} mm · ${data.scene.objects.some(o=>o.illustration)?'对象插画':'矢量对象'}`;saveStatus(`已保存 · r${S.revision}`);history.replaceState(null,'',`/#${id}`);
 renderProperties();renderAudit();renderLayers();renderTools();workspaceUI?.refresh();annotationUI?.load(id);
 const generationOpened=generationUI?.opened(data.scene);
 await documentUI?.opened(data);if(!current())return;
 await generationOpened;if(!current())return;noviceUI?.opened(data);modesUI?.opened();
}});
async function openJob(id,options){startupNavigationCancelled=true;composerUI?.leavingHome();return loadDocument(id,options);}
async function openLegacy(job,svg=''){
  editor.clear();annotationUI?.load(null);S.id=job.id;S.currentJob=job;S.revision=0;S.pending=[];S.audit=null;S.svg='';S.conflict=false;
  const host=$('canvas-host');host.classList.add('legacy-preview');
  if(job.svg_url){S.svg=svg;const art=sanitizedSvg(S.svg);art.id='legacy-art';host.append(art);}
  else if(job.png_url||job.preview_url){const art=el('img');art.src=job.png_url||job.preview_url;art.id='legacy-art';art.alt=job.title||'科研插画';host.append(art);}
  else host.append(el('p','legacy-placeholder',job.error||job.message||'此任务尚无可预览的成图，可在右侧查看任务信息。'));
  $('welcome').hidden=true;$('toggle-export').disabled=!job.svg_url&&!job.png_url;$('project-title').textContent=job.title||'历史图版';
  $('brief-input').value=job.original_text||job.text||'';authorBrief(S,$('brief-input').value);updateCount();saveStatus('原图预览 · 历史版本保留');
  generationUI?.opened({});
  history.replaceState(null,'',`/#${job.id}`);$('canvas-size').textContent='原图预览 · '+(job.canvas_mm?job.canvas_mm.join(' × ')+' mm':'尺寸见任务信息');$('canvas-hint').textContent='原图预览 · 滚轮缩放 · 右侧查看任务或重建可编辑副本';renderTools();$('canvas-hint').textContent='原图预览 · 滚轮缩放 · 右侧查看任务或重建可编辑副本';renderProperties();renderAudit();workspaceUI?.legacyZoom(1);workspaceUI?.showRight('task');
}
let followPromise=null;
function follow(id){
 if(followPromise){if(S.active===id)return followPromise;toast('已有生成任务正在处理，新任务已保留在最近图版',true);return Promise.resolve({status:'error',message:'已有任务正在处理，请在最近图版查看新任务。'});}
 followPromise=trackGeneration(id).finally(()=>{followPromise=null;});return followPromise;
}
async function trackGeneration(id){
 S.active=id;workspaceUI?.refresh();$('generation-status').hidden=false;$('generate').disabled=true;let terminal=null;
 try{for(;;){
  const job=await api(`/api/jobs/${id}`);const recentIndex=S.jobs.findIndex(j=>j.id===job.id);if(recentIndex<0)S.jobs.unshift(job);else S.jobs[recentIndex]=job;navigationUI?.render();$('generation-text').textContent=job.message||'正在生成';$('generation-progress').value=job.progress||0;
  $('generation-stage-list').replaceChildren(...(job.stages||[]).map(stage=>el('span','stage-pill '+stage.state,stage.label||stage.name||stage.title||stage.id||stage.stage||'处理中')));
  if(job.status==='completed'){terminal=job;await refreshJobs();const opened=await openJob(id);if(job.illustration_result?.state==='partial')toast('插画没有全部完成，已保留可编辑草稿。请查看内容建议。',true);return {...job,opened};}
  if(['failed','cancelled','error'].includes(job.status)){terminal=job;if(job.scene_revision){await refreshJobs();await openJob(id);}throw Error(job.error||job.message||'任务未完成');}
  await new Promise(r=>setTimeout(r,800));
 }}catch(error){toast(error.message,true);return terminal||{status:'error',error:error.message};}
 finally{S.active=null;workspaceUI?.refresh();$('generation-status').hidden=true;generationUI?.refresh();}
}
async function sample(id){if(S.active)return toast('已有生成任务，请等待完成或先取消');if(!await canLeave())return;try{const dims=$('new-size').value.split('x').map(Number);await follow((await api('/api/scene/example',{example:id,template:({egfr:'signal_lipid',jak_stat:'signal_relay',tgf_smad:'signal_nucleus',exosome:'process_strip',wound:'process_grid',tme:'network_orbit',nlrp3:'assembly_tiers',workflow:'workflow_strip'}[id]),canvas_mm:dims})).job_id);}catch(e){toast(e.message,true);}}
async function blank(){if(S.active)return toast('已有生成任务，请等待完成或先取消');if(!await canLeave())return;try{const result=await api('/api/scene/blank',{});await refreshJobs();await openJob(result.job_id);tab('assets');editor.fit();}catch(e){toast(e.message,true);}}
function tab(name, toggle=false){
 if(name==='generate'&&composerUI){composerUI.open();return;}
 ws.dispatchEvent(new Event('workspace-panel-request'));
 if(name==='assets'){showFloatingWindow($('asset-library-dialog'));syncPanelButtons(ws);return;}
 if(name==='templates')libraryUI.renderTemplates();
 const wasMinimized=document.querySelector('.left-panel')?.classList.contains('is-minimized');
 const collapse=toggle&&!wasMinimized&&!ws.classList.contains('left-collapsed')&&document.querySelector(`[data-tab="${name}"]`)?.classList.contains('active');
 preserveCanvasView(editor,()=>{
  if(innerWidth<1440)ws.classList.add('properties-hidden');
  document.querySelectorAll('[data-tab]').forEach(n=>n.classList.toggle('active',n.dataset.tab===name));
  document.querySelectorAll('.left-tab').forEach(n=>n.hidden=n.id!==`panel-${name}`);
  ws.classList.toggle('left-collapsed',collapse);
 });floatingWindows.restorePanel();floatingWindows.constrainPanel();syncPanelButtons(ws);
}
function renderExamples(){const list=$('example-list');list.replaceChildren();(S.templates||[]).filter(t=>t.recommended&&t.library_group==='science').forEach(item=>{const b=el('button','example-card');const img=el('img','example-thumb');img.src=item.thumbnail;img.alt='';b.append(img);const text=el('span');text.append(el('span','example-name',item.title),el('span','example-description',item.usage));b.append(text);b.onclick=()=>libraryUI.showTemplate(item);list.append(b);});}
function renderAssets(){libraryUI.renderAssets();}
function renderLayers(){const list=$('layer-list');list.replaceChildren();if(!S.revision||!editor.scene)return;const selected=new Set(editor.selectedIds);for(const o of [...editor.scene.objects].reverse()){const row=el('div','layer-row'+(selected.has(o.id)?' selected':'')),name=el('button','layer-name',o.label||o.id);name.onclick=e=>editor.setSelection(e.shiftKey?[...selected,o.id]:[o.id]);row.append(name);for(const [key,title,active,inactive]of [['visible','可见性','◉','○'],['locked','锁定','L','·']]){const b=el('button','layer-toggle'+(o[key]?' on':''),o[key]?active:inactive);b.setAttribute('aria-label',`${title} ${o.label}`);b.onclick=()=>editor.applyOperations([{op:'update',id:o.id,changes:{[key]:!o[key]}}],title);row.append(b);}list.append(row);}}
function input(parent,label,value,type,change,options){const wrapper=el('label','',label),n=el(type==='select'?'select':'input');if(type==='select'){for(const [v,t]of options){const opt=el('option','',t);opt.value=v;n.append(opt);}n.value=value;}else{n.type=type||'text';n.value=value??'';if(type==='number')n.step='.1';if(type==='color')n.className='color-input';}n.setAttribute('aria-label',label);const commit=()=>{const v=type==='number'?Number(n.value):n.value;if(type==='number'&&!Number.isFinite(v))return;change(v);};n.onchange=commit;n.onkeydown=e=>{if(e.key==='Enter'){commit();n.blur();}};wrapper.append(n);parent.append(wrapper);return n;}
function section(parent,title){const n=el('div','property-section');n.append(el('h3','',title));parent.append(n);const grid=el('div','property-grid');n.append(grid);return grid;}
function renderProperties(){
 const parent=$('property-content');parent.replaceChildren();
 if(!S.revision||!editor.scene){parent.append(el('p','empty-properties','先打开样板或创建空白图版。添加素材后，单击选中即可编辑。'));return;}
 const scene=editor.scene,ids=editor.selectedIds,objects=scene.objects.filter(o=>ids.includes(o.id)),relations=scene.relations.filter(r=>ids.includes(r.id));
 function advanced(title){const details=el('details','property-advanced');details.append(el('summary','',title));parent.append(details);return details;}
 if(objects.length){
  const o=objects[0];parent.append(el('p','property-description',objects.length>1?`已选 ${objects.length} 个对象。颜色和字号会同时应用到这些对象。`:o.locked?'此对象已锁定。可以在图层中解锁后编辑。':'在这里修改文字、颜色和状态；拖动图形调整位置。'));
  const basic=section(parent,'文字与外观');
  if(objects.length===1)input(basic,'名称',o.label,'text',v=>editor.changeSelection({label:v}));
  input(basic,'字号 · pt',o.font_size_pt,'number',v=>{if(v<7||v>48){toast('字号可设为 7–48 pt');return renderProperties();}editor.changeSelection({font_size_pt:v});});
  input(basic,'填充颜色',o.fill||'#dae8ed','color',v=>editor.changeSelection({fill:v}));input(basic,'轮廓颜色',o.stroke||'#326c82','color',v=>editor.changeSelection({stroke:v}));
  const bio=section(parent,'状态与说明');
  if(o.type==='cell'){
   const plant=o.state?.startsWith('plant_'),prefix=plant?'plant_':'',phaseChoices=[['interphase','间期'],['prophase','前期'],['prometaphase','前中期'],['metaphase','中期'],['anaphase','后期'],['telophase','末期'],['cytokinesis','胞质分裂']].map(([value,label])=>[prefix+value,label]);
   const options=[['',plant?'通用细胞':'默认细胞'],...phaseChoices,...(plant?[]:[['apoptotic','凋亡']])];
   if(o.state&&!options.some(([value])=>value===o.state))options.push([o.state,'当前自定义状态']);
   input(bio,plant?'植物细胞分期':'细胞分期',o.state,'select',v=>editor.changeSelection({state:v,illustration:null}),options);
  }
  input(bio,'状态文字',o.state,'text',v=>editor.changeSelection({state:v,illustration:null}));
  if(o.illustration)parent.append(el('p','muted small','这是独立插画对象，可移动和缩放。更改分期将恢复对应矢量形态；像素内部结构不能直接拖动。'));
  const detail=advanced('精确位置、尺寸与文字偏移'),dims=section(detail,'位置与尺寸 · mm');
  for(const[key,label]of [['x','X'],['y','Y'],['w','宽度'],['h','高度'],['rotation','旋转角度'],['stroke_pt','线宽 · pt'],['label_dx','文字左右偏移'],['label_dy','文字上下偏移']])input(dims,label,Number(o[key]??(key==='stroke_pt'?scene.style.stroke_pt:0)).toFixed(1),'number',v=>editor.changeSelection({[key]:v}));
  const actions=el('div','property-actions');for(const[label,fn]of [['移到最前',()=>order(true)],['移到最后',()=>order(false)]]){const b=el('button','button',label);b.onclick=fn;actions.append(b);}detail.append(actions);
  const ai=el('button','button full','用 AI 修改所选对象');ai.onclick=openAI;parent.append(ai);
  const redraw=el('button','button full','重绘所选插画');redraw.disabled=objects.some(o=>o.locked)||!!S.active;redraw.onclick=()=>generationUI?.redraw();parent.append(redraw);
 }else if(relations.length){
  const r=relations[0],grid=section(parent,'连线表达什么'),change=c=>editor.applyOperations([{op:'update_relation',id:r.id,changes:c}]);
  grid.append(relationChoices(editor,{compact:true}));
  input(grid,'线上文字',r.label,'text',v=>change({label:v}));parent.append(el('p','property-description','拖动两端圆点，可连接对象边缘任意位置；中间圆点调整弯曲。线上文字可以单独拖动或双击改字。'));
  const meaning=section(parent,'作用方式与核对');
  input(meaning,'作用方式',String(!!r.indirect),'select',v=>change({indirect:v==='true'}),[['false','直接 · 实线'],['true','间接 · 虚线']]);
  input(meaning,'含义状态',String(!!r.uncertain),'select',v=>change({uncertain:v==='true'}),[['true','待作者核对'],['false','已核对并保存定义']]);
  const extra=section(advanced('更多连线设置'),'端点');
  for(const[key,label]of [['source_port','从哪里连出'],['target_port','连接到哪里']]){
    const anchorKey=key.replace('_port','_anchor'),a=r[anchorKey];
    input(extra,label,a?'custom':r[key]||'auto','select',v=>{if(v!=='custom')change({[key]:v,[anchorKey]:null});},[['custom','自定义 · 拖动端点'],['auto','自动'],['n','上方中点'],['e','右侧中点'],['s','下方中点'],['w','左侧中点']]);
    if(a){input(extra,label+' · 所在边',a.side,'select',v=>change({[anchorKey]:{...a,side:v}}),[['n','上边'],['e','右边'],['s','下边'],['w','左边']]);input(extra,label+' · 沿边位置 %',a.t*100,'number',v=>{if(v>=0&&v<=100)change({[anchorKey]:{...a,t:v/100}});else toast('沿边位置为 0–100%，上/下边从左到右，左/右边从上到下。');});}
  }
  const reset=el('button','button','文字回到连线旁');reset.onclick=()=>change({label_position:null});extra.append(reset);
  input(extra,'线宽 · pt',r.stroke_pt||1.05,'number',v=>change({stroke_pt:v}));
  input(extra,'连线颜色',r.stroke||scene.style.palette.primary,'color',v=>change({stroke:v}));
 }else{
  parent.append(el('p','property-description','选中图形后可以修改文字、颜色和状态；多选后，可在“排列”中对齐或组合。'));
  const grid=section(parent,'纸张大小');input(grid,'宽度 · mm',scene.canvas.width_mm,'number',v=>canvas(v,scene.canvas.height_mm));input(grid,'高度 · mm',scene.canvas.height_mm,'number',v=>canvas(scene.canvas.width_mm,v));
  const presets=el('div','canvas-presets');for(const[label,w,h]of [['论文双栏',180,120],['论文单栏',90,150]]){const b=el('button','button',label);b.onclick=()=>canvas(w,h);presets.append(b);}parent.append(presets);
  const colors=section(advanced('整张图的配色与字号'),'统一样式');for(const[key,label]of [['primary','主色'],['secondary','辅色'],['accent','强调色']])input(colors,label,scene.style.palette[key],'color',v=>editor.applyOperations([{op:'style',changes:{palette:{[key]:v}}}]));
  input(colors,'统一字号 · pt',scene.style.font_size_pt,'number',v=>{if(v<7||v>48)return toast('字号可设为 7–48 pt');editor.applyOperations([{op:'style',changes:{font_size_pt:v}},...scene.objects.map(o=>({op:'update',id:o.id,changes:{font_size_pt:v}}))]);});
 }
}
function canvas(w,h){if(w<40||h<40||w>1000||h>1000)return toast('画布尺寸范围为 40–1000 mm');editor.setCanvasSize(w,h);$('canvas-size').textContent=`${w} × ${h} mm · ${editor.scene.objects.some(o=>o.illustration)?'对象插画':'矢量对象'}`;}
function order(front){const a=editor.scene.objects.filter(o=>editor.selectedIds.includes(o.id)).map(o=>o.id),b=editor.scene.objects.filter(o=>!editor.selectedIds.includes(o.id)).map(o=>o.id);editor.applyOperations([{op:'reorder',ids:front?[...b,...a]:[...a,...b]}]);}
function renderTools(){ws.classList.toggle('has-document',!!S.id);const count=editor.selectedIds.length,objects=editor.scene?.objects.filter(o=>editor.selectedIds.includes(o.id))||[];if(editor.scene)$('canvas-size').textContent=`${editor.scene.canvas.width_mm} × ${editor.scene.canvas.height_mm} mm · ${editor.scene.objects.some(o=>o.illustration)?'对象插画':'矢量对象'}`;$('duplicate').disabled=!objects.length;$('delete').disabled=!count;$('quick-connect').disabled=!objects.length||objects.length>2;$('undo').disabled=!S.revision||!editor.hasUndo;$('redo').disabled=!S.revision||!editor.hasRedo;$('group').disabled=objects.length<2;$('ungroup').disabled=!objects.some(o=>o.group_id);$('align').disabled=objects.length<2;$('add-text').disabled=!S.revision;workbenchUI?.refresh();relationsUI?.refresh();noviceUI?.refresh();generationUI?.refresh();}
function renderHistory(){noviceUI?.refresh();return documentUI?documentUI.renderHistory():renderLegacyHistory();}
function renderLegacyHistory(){
 const list=$('history-list');list.replaceChildren();const q=$('history-search').value,filter=$('history-filter')?.value||'all';
 for(const job of S.jobs.filter(j=>historyMatches(j,q,filter))){
  const row=el('button','history-row'),text=el('span'),img=el('img','history-thumb');
  img.src=job.svg_url||job.png_url||'/ui/library/signal_relay.svg';img.alt='';img.loading='lazy';row.append(img);
  text.append(el('strong','',job.title||'未命名图版'),el('small','',`${new Date((job.created||0)*1000).toLocaleString()} · ${{completed:'已生成',processing:'生成中',queued:'排队中',failed:'失败',error:'失败',cancelled:'已取消'}[job.status]||job.status}`));
  row.append(text,el('span','history-tag',job.scene_engine==='v2'?`可编辑 · r${job.scene_revision||'—'}`:'插画 / 历史'));
  row.onclick=()=>{$('history-dialog').close();['queued','processing'].includes(job.status)?follow(job.id):openJob(job.id);};list.append(row);
 }
 if(!list.children.length)list.append(el('p','muted','没有匹配的图版，可以更换关键词或分类。'));
}
function renderAudit(){
 const a=S.audit,content=$('audit-content');content.replaceChildren();
 const findings=a?.findings||[],pending=findings.filter(f=>f.status!=='acknowledged').length;
 $('open-audit').textContent=pending?`排版与内容建议 · ${pending}`:'查看排版建议';
 $('open-audit').classList.toggle('warning',!!pending);
 const repairable=findings.some(f=>f.object_ids?.length&&['error','warning'].includes(f.severity));
 $('repair-geometry').hidden=!repairable;
 $('repair-geometry').disabled=!S.revision||!!S.saving||!!S.pending.length;
 $('repair-geometry').textContent=repairable?'自动修复可确认的几何问题':'没有可自动修复的几何问题';
 const visionButton=$('vision-review'),v=a?.vision||{};
 visionButton.textContent=v.status==='running'?'正在获取视觉建议…':v.status==='completed'?'重新获取视觉建议':'获取视觉建议';
 visionButton.disabled=!S.revision||v.status==='running';
 $('confirm-author').disabled=!S.revision||!!a?.author_confirmed;
 if(!a){workspaceUI?.refresh();return;}
 content.append(el('div','check-summary',`修订 r${S.revision} · ${a.errors||0} 项错误 · ${a.warnings||0} 项提示`));
 for(const f of findings){const card=el('div','finding '+f.severity);card.append(el('strong','','对象与几何检查'),el('div','',f.message));if(f.object_ids?.length){const b=el('button','',`定位 ${f.object_ids.join(' · ')}`);b.onclick=()=>{$('audit-dialog').close();editor.setSelection(f.object_ids);editor.revealSelection?.();};card.append(b);}content.append(card);}
 if(!findings.length)content.append(el('p','muted','当前检查没有发现对象与几何问题。科学含义仍由作者核对。'));
 content.append(el('h3','',`视觉建议 · ${v.status==='completed'?'已返回':v.status==='running'?'正在审阅':v.status==='unavailable'?'服务不可用':'尚未请求'}`));
 if(v.error)content.append(el('p','muted small',v.error));
 for(const [index,f]of (v.findings||[]).entries()){if(f.status==='dismissed')continue;const n=el('div','finding');n.append(el('strong','','模型意见 · 待核验'),el('div','',f.message));if(f.evidence)n.append(el('p','muted small',f.evidence));const dismiss=el('button','','核验后排除此建议');dismiss.onclick=async()=>{try{const data=await api(`/api/jobs/${S.id}/review-finding`,{base_revision:S.revision,index,reason:'作者核验后排除'});S.audit=data.audit;renderAudit();}catch(e){toast(e.message,true);}};n.append(dismiss);content.append(n);}
 if(v.raw){const details=el('details'),summary=el('summary','','审阅原文与诊断');details.append(summary,el('p','muted small',`模型：${v.model||'—'} · 修订 r${v.revision||S.revision}`),el('pre','review-raw',v.raw));for(const f of (v.findings||[]).filter(f=>f.status==='dismissed'))details.append(el('p','muted small',`已排除：${f.message}；${f.resolution||''}`));content.append(details);}
 content.append(el('p','muted small',a.author_confirmed?'作者已核对当前修订。':'当前修订尚未标记为作者核对。'));workspaceUI?.refresh();
}
async function openAI(){if(!S.revision||!editor.selectedIds.length)return toast('请先选择要修改的对象');if(!await flush())return;await annotationUI.forSelection([...editor.selectedIds]);}


async function exportFile(format){
 if(!S.id||S.exporting)return;
 const jobId=S.id,status=$('export-status');S.exporting=true;
 document.querySelectorAll('[data-export]').forEach(b=>b.disabled=true);
 status.replaceChildren(el('p','','正在准备文件，请稍候…'));status.classList.remove('export-success');
 try{
  if(S.revision&&!await flush())return;
  if(S.id!==jobId)return;
  const result=await api(`/api/jobs/${jobId}/save-as`,{format,dpi:Number($('export-dpi').value),...(S.revision?{revision:S.revision}:{})});
  if(S.id!==jobId){toast(result.path?'上一个图版的文件已保存。':'上一个图版的保存已结束。');return;}
  if(result.cancelled){status.textContent='已取消保存。图版仍保留在软件里。';return;}
  if(!result.path)throw Error('没有返回保存位置，请重试。');
  status.classList.add('export-success');status.replaceChildren(el('strong','','文件已保存'),el('p','export-saved-path',result.path));
  if(result.warnings?.length)status.append(el('p','',result.warnings.join('；')));
  if(result.raster_objects?.length)status.append(el('p','',`这些对象以图片保存：${result.raster_objects.join('、')}`));
  const reveal=el('button','button','打开保存位置');reveal.onclick=()=>api('/api/reveal',{path:result.path,action:'select'}).catch(e=>toast(e.message,true));status.append(reveal);
  onboardingUI?.exported(jobId);toast('文件已保存到电脑。软件里的图版也已保留。');
 }catch(e){if(S.id===jobId)status.replaceChildren(el('p','','保存没有完成：'+e.message),el('p','muted','图版仍在软件里，可以换一个格式或保存位置重试。'));toast(e.message,true);}
 finally{S.exporting=false;if(S.id!==jobId)status.replaceChildren();document.querySelectorAll('[data-export]').forEach(b=>b.disabled=false);}
}
function updateCount(){$('brief-count').textContent=`${$('brief-input').value.length} / ${$('brief-input').maxLength}`;}
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=()=>tab(b.dataset.tab,true));document.querySelectorAll('[data-tool]').forEach(b=>b.onclick=()=>{document.querySelectorAll('[data-tool]').forEach(n=>n.classList.toggle('active',n===b));if(b.dataset.tool==='connect'&&editor.scene?.objects.filter(o=>editor.selectedIds.includes(o.id)).length===2){editor.connectSelection(editor.relationType);editor.setTool('select');}else editor.setTool(b.dataset.tool);});document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>$(b.dataset.close).close());
for(const[id,fn]of [['toggle-left',()=>{preserveCanvasView(editor,()=>ws.classList.toggle('left-collapsed'));syncPanelButtons(ws); }],['toggle-properties',()=>ws.classList.toggle('properties-hidden')],['close-properties',()=>{preserveCanvasView(editor,()=>ws.classList.add('properties-hidden'));syncPanelButtons(ws); }],['undo',()=>editor.undo()],['redo',()=>editor.redo()],['group',()=>editor.groupSelection()],['ungroup',()=>editor.ungroupSelection()],['add-text',()=>editor.insertTextAtCenter()],['zoom-fit',()=>S.revision?editor.fit():workspaceUI?.legacyZoom(1)],['zoom-100',()=>S.revision?editor.setZoom(1):workspaceUI?.legacyZoom(1)],['zoom-in',()=>S.revision?editor.zoomBy(1.15):workspaceUI?.legacyZoom(null,1.15)],['zoom-out',()=>S.revision?editor.zoomBy(1/1.15):workspaceUI?.legacyZoom(null,1/1.15)],['welcome-example',()=>libraryUI.showTemplate(S.templates.find(t=>t.id==='sb_socs_feedback'))],['welcome-blank',blank],['new-blank',blank]])$(id).onclick=fn;
$('align').onchange=e=>{if(e.target.value.startsWith('distribute-'))editor.distributeSelection(e.target.value.at(-1));else if(e.target.value)editor.alignSelection(e.target.value);e.target.value='';};$('brief-input').oninput=()=>{authorBrief(S,$('brief-input').value);generationUI?.refresh();try{localStorage.setItem('rylume-research-brief',$('brief-input').value);}catch{}updateCount();};$('history-search').oninput=renderHistory;
// generate handled by generationUI
$('cancel-job').onclick=()=>{if(S.active)api(`/api/jobs/${S.active}/cancel`,{}).then(()=>$('generation-text').textContent='正在取消…').catch(e=>toast(e.message,true));};$('open-history').onclick=async()=>{await refreshJobs();$('history-dialog').showModal();};$('toggle-export').onclick=()=>{const dialog=$('export-menu');if(dialog.open){dialog.close();return;}dialog.hidden=false;dialog.showModal();$('export-status').replaceChildren();if(S.exporting)$('export-status').textContent='上一份文件还在保存，请稍候。';$('export-revision').textContent='导出当前图版，原图仍可继续编辑。';};
$('close-export').onclick=$('continue-editing').onclick=()=>$('export-menu').close();$('export-menu').addEventListener('close',()=>$('export-menu').hidden=true);document.querySelectorAll('[data-export]').forEach(b=>b.onclick=()=>exportFile(b.dataset.export));$('open-audit').onclick=()=>workspaceUI?.showRight('review');
$('repair-geometry').onclick=async()=>{if(!S.revision||!await flush())return;try{const data=await api(`/api/jobs/${S.id}/auto-fix`,{});S.revision=data.revision;S.svg=data.svg;S.audit=data.audit;editor.updateDocument(data.scene,data.svg);saveStatus(`已保存 · r${S.revision}`);renderAudit();toast(data.changed?'已修复可确认的几何问题':data.message||'没有可自动修复的问题');}catch(e){toast(e.message,true);}};
$('vision-review').onclick=async()=>{if(!S.revision||!await flush())return;try{await api(`/api/jobs/${S.id}/recheck`,{vision:true});S.audit.vision={status:'running',findings:[]};renderAudit();const id=S.id;for(let i=0;i<90;i++){await new Promise(r=>setTimeout(r,1500));if(S.id!==id)return;S.audit=(await api(`/api/jobs/${id}/scene`)).audit;renderAudit();if(S.audit.vision?.status!=='running')break;}}catch(e){toast(e.message,true);}};
$('confirm-author').onclick=async()=>{if(!S.revision||!await flush())return;await api(`/api/jobs/${S.id}/confirm`,{revision:S.revision});S.audit.author_confirmed=true;renderAudit();toast('已记录当前修订的作者核对');};
$('download-draft').onclick=()=>{if(!editor.scene)return;const url=URL.createObjectURL(new Blob([JSON.stringify(editor.scene,null,2)],{type:'application/json'})),a=el('a');a.href=url;a.download=(S.id||'figure')+'-draft.scene.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};$('reload-scene').onclick=()=>{if(!confirm('请先保存本地草稿。重新载入将显示服务器上已保存的修订。'))return;S.pending=[];S.conflict=false;openJob(S.id);};
// reference handled by generationUI
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveControls.run();}if(e.key==='Escape'&&$('export-menu').open)$('export-menu').close();});window.addEventListener('beforeunload',e=>{if(S.pending.length||S.saving||S.inlineEditing){e.preventDefault();e.returnValue='';}});
async function boot(){ws.classList.add('left-collapsed','properties-hidden');syncPanelButtons(ws);renderProperties();try{try{if(!location.hash)$('brief-input').value=localStorage.getItem('rylume-research-brief')||'';}catch{}updateCount();const data=await api('/api/scene/catalog');S.assets=data.assets||[];S.examples=data.examples||[];libraryUI.init(data);renderExamples();renderTools();await refreshJobs();const id=location.hash.slice(1);if(!startupNavigationCancelled&&/^[A-Za-z0-9_-]+$/.test(id))await openJob(id);return true;}catch(e){toast('连接本地服务失败：'+e.message,true);return false;}}
const libraryUI=setupLibrary({editor,api,state:S,toast,blank,flush,follow,tab,requestResource:pid=>deliveryUI.openResources(pid)});
$('toggle-snap').onchange=e=>editor.snap=e.target.checked;
$('duplicate').onclick=()=>editor.duplicateSelection();$('delete').onclick=()=>editor.deleteSelection();$('quick-connect').onclick=()=>{const objects=editor.scene?.objects.filter(o=>editor.selectedIds.includes(o.id))||[];if(objects.length===2){editor.connectSelection(editor.relationType);editor.setTool('select');}else editor.setTool('connect');};
for(const b of document.querySelectorAll('.tool[aria-label]'))b.title=b.title||b.getAttribute('aria-label');
for(const [tool,label] of [['select','选择'],['pan','拖动画布'],['connect','添加连线']]){const b=document.querySelector(`[data-tool=${tool}]`);b.append(el('span','tool-caption',label));}
const editLabel=el('span','tool-caption','添加文字');$('add-text').append(editLabel);
window.addEventListener('hashchange',()=>{const id=location.hash.slice(1);if(/^[A-Za-z0-9_-]+$/.test(id)&&id!==S.id)openJob(id);});
workspaceUI=setupWorkspace({state:S,editor,api,toast,flush,follow,tab,openJob,renderAudit,renderHistory,renderReview:()=>reviewUI?.render()});
workbenchUI=setupWorkbench({editor,workspace:ws});
relationsUI=setupRelations(editor,{flush,getDocumentId:()=>S.id});
annotationUI=setupAnnotations({state:S,editor,api,flush,toast,workspace:ws,canSubmit:()=>documentUI.checkModels('vector'),onApplied:async data=>{
  if(data.scene?.id!==S.id)return;
  const before=clone(editor.scene);
  editor.undoStack.push(before);if(editor.undoStack.length>100)editor.undoStack.shift();editor.redoStack=[];
  S.revision=data.revision;S.audit=data.audit;S.svg=data.svg;S.pending=[];S.dirty++;S.conflict=false;
  editor.updateDocument(data.scene,data.svg);saveStatus(`已保存 · r${S.revision}`);
  renderAudit();renderProperties();renderLayers();renderTools();workspaceUI?.refresh();await refreshJobs();
}});
reviewUI=setupReview({state:S,editor,api,flush,toast,showRight:workspaceUI.showRight,showLayers:()=>tab('layers')});
$('open-check-toolbar').onclick=()=>workspaceUI.showRight('review',false);
documentUI=setupDocumentWorkflows({state:S,editor,api,flush,toast,openJob,refreshJobs,follow});
$('welcome-ai').onclick=()=>{tab('generate');$('brief-input').focus();};
deliveryUI=setupDelivery({api,toast,flush,state:S,saveCopy:()=>documentUI.saveCopy(),documentTitle:()=>editor.scene?.title,reloadCatalog:async data=>{S.assets=data.assets;libraryUI.init(data);renderExamples();},openAssets:pid=>{tab('assets');libraryUI.selectDomain(pid);},openTemplates:pid=>libraryUI.openPackTemplates(pid)});
document.querySelectorAll('.close-library-panel').forEach(b=>b.onclick=()=>{preserveCanvasView(editor,()=>ws.classList.add('left-collapsed'));syncPanelButtons(ws);});
noviceUI=setupNovice({state:S,editor,api,toast,flush,canLeave,openJob,refreshJobs,follow,tab,renderRecent:()=>navigationUI?.render()});
modesUI=setupWorkspaceModes({editor,state:S,tab,showRight:name=>workspaceUI.showRight(name),refresh:renderTools});
generationUI=setupGenerationWorkflow({state:S,editor,api,flush,follow,canLeave,workspace:workspaceUI,checkModels:mode=>documentUI.checkModels(mode),toast,tab});
composerUI=setupCreationComposer({state:S,toast,workflow:generationUI,workspace:workspaceUI});
navigationUI=setupWorkspaceNavigation({state:S,editor,api,openJob,follow,tab,toast});
// A slow startup must not reopen the last document over an explicit new start.
$('open-start').addEventListener('click',()=>{startupNavigationCancelled=true;loadDocument.cancel();},{capture:true});
documentsUI=setupDocumentAssistant({state:S,editor,api,toast,composer:composerUI});
onboardingUI=setupOnboarding({state:S,editor,api,flush,canLeave,openJob,refreshJobs,tab,toast});
const personalUI=setupPersonalAssets({api,toast,library:libraryUI,state:S});
const releaseUI=setupReleaseNotes({api,toast});
// Keep command names and visible targets in sync as modules are added. A
// broken target is reported for diagnostics but never blocks the editor.
const uiContract=installUiContract({onIssue:issue=>console.warn('[Rylume UI contract]',issue.message)});
window.__RYLUME_UI_CONTRACT__=uiContract;
document.addEventListener('ui-action-error',event=>toast(event.detail?.message||'当前操作暂不可用',true));
boot().then(async ok=>{if(ok){await onboardingUI.ready();deliveryUI.ready();releaseUI.ready();}});
