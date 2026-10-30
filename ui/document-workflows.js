import {DraftStore} from './draft-store.js';
import {sanitizedSvg,legendOperations} from './canvas-editor.js';

const clone=x=>structuredClone(x),$=id=>document.getElementById(id);
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
const button=(text,run,primary=false)=>{const b=el('button','button'+(primary?' primary':''),text);b.type='button';b.onclick=async()=>{b.disabled=true;try{await run();}catch(e){document.dispatchEvent(new CustomEvent('workflow-error',{detail:e.message}));}finally{b.disabled=false;}};return b;};
function dialog(title){const d=el('dialog','document-dialog'),head=el('div','dialog-heading');head.append(el('h2','',title),button('关闭',()=>d.close()));d.append(head);document.body.append(d);return d;}
export function sameDocument(a,b){return JSON.stringify({...a,revision:0})===JSON.stringify({...b,revision:0});}

export function setupDocumentWorkflows({state,editor,api,flush,toast,openJob,refreshJobs,follow}){
  const store=new DraftStore();let recovery=null,exportMeta=null,exportEpoch=0;
  document.addEventListener('workflow-error',e=>toast(e.detail,true));
  function changed(){if(!state.id||!editor.scene)return;store.write({id:state.id,base_revision:state.revision,scene:clone(editor.scene)}).catch(()=>{state.backupError=true;toast('本机恢复副本暂存失败，请用“文件 → 保存可编辑文件”保留图版',true);});}
  function saved(){if(!state.pending.length&&!state.saving){state.saveError=null;state.saveFailures=0;store.clear(state.id).catch(()=>{});}else if(state.pending.length)changed();}
  async function independentCopy(scene,clearCurrent=false){
    const source=state.id,result=await api('/api/scene/import',{scene});
    if(clearCurrent){state.pending=[];state.conflict=false;state.saveError=null;await store.clear(source).catch(()=>{});}
    await refreshJobs();await openJob(result.job_id);toast('已保存为独立图版，原图保留');
  }
  const recover=dialog('发现尚未保存的图版'),recoveryText=el('p','muted'),recoveryActions=el('div','dialog-actions');recover.append(recoveryText,recoveryActions);
  recover.querySelector('.dialog-heading button').remove();recover.addEventListener('cancel',e=>e.preventDefault());
  async function opened(data){
    $('workspace').classList.add('editing-document');if(innerWidth<1440)$('workspace').classList.add('left-collapsed');
    const id=state.id,cached=await store.read(id);if(state.id!==id||!cached?.scene)return;
    if(sameDocument(cached.scene,data.scene)){await store.clear(id);return;}
    recovery=cached;recoveryText.textContent='发现 '+new Date(cached.updated_at).toLocaleString()+' 的本机恢复副本。服务器当前为 r'+state.revision+'，副本基于 r'+cached.base_revision+'。选择恢复方式后才会更改图版。';
    const restore=button('恢复到当前图版',()=>{if(state.id!==id||state.revision!==cached.base_revision)throw Error('服务器图版已更新，请恢复为独立副本');recover.close();editor.applyOperations([{op:'replace',scene:clone(cached.scene)}],'恢复本机草稿');},true);
    restore.disabled=state.revision!==cached.base_revision;restore.title=restore.disabled?'服务器有更新，请恢复为独立副本':'';
    recoveryActions.replaceChildren(button('保留服务器版本',async()=>{await store.clear(id);recover.close();}),button('恢复为独立副本',async()=>{await independentCopy(cached.scene,true);recover.close();}),restore);recover.showModal();
  }
  const retry=button('重试保存',async()=>{state.conflict=false;state.saveError=null;await flush();});retry.id='retry-scene-save';
  const rescue=button('另存为独立图版',()=>independentCopy(clone(editor.scene),true));
  $('error-banner').append(retry,rescue);
  $('download-draft').textContent='保存可编辑文件';
  function download(){if(!editor.scene)return toast('请先打开可编辑图版');const a=el('a'),url=URL.createObjectURL(new Blob([JSON.stringify(editor.scene,null,2)],{type:'application/json'}));a.href=url;a.download=(editor.scene.title||'图版')+'.scene.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('download-draft').onclick=download;
  const file=el('input');file.type='file';file.accept='.json,.scene.json,application/json';file.hidden=true;file.id='import-scene-file';document.body.append(file);
  file.onchange=async()=>{try{const selected=file.files[0];if(!selected)return;if(selected.size>24*1024*1024)throw Error('可编辑文件请小于 24 MB');const value=JSON.parse(await selected.text());if(!await flush()&&state.revision)throw Error('请先保存当前图版，或另存未保存的修改');await independentCopy(value.scene||value);}catch(e){toast('导入未完成：'+e.message,true);}finally{file.value='';}};
  const menu=document.querySelector('.app-menu .menu-items');
  const info=dialog('图版名称与分类'),name=el('input'),collection=el('input');name.maxLength=120;collection.maxLength=60;name.setAttribute('aria-label','图版名称');collection.setAttribute('aria-label','图版分类');
  const labelName=el('label','settings-field','图版名称'),labelCollection=el('label','settings-field','分类（可选）');labelName.append(name);labelCollection.append(collection);info.append(labelName,labelCollection);
  info.append(button('保存图版信息',async()=>{if(!await flush())return;const id=state.id;await api('/api/jobs/'+id+'/document-info',{base_revision:state.revision,title:name.value,collection:collection.value});info.close();await refreshJobs();await openJob(id);},true));
  function editInfo(){if(!state.id)return toast('请先打开图版');name.value=editor.scene?.title||state.currentJob?.title||'';collection.value=state.currentJob?.collection||'';info.showModal();name.focus();name.select();}
  const revisions=dialog('版本历史'),revisionBody=el('div','revision-browser'),revisionList=el('div','revision-list'),revisionPreview=el('div','revision-preview'),revisionCaption=el('p','muted');revisions.classList.add('wide-dialog');revisionBody.append(revisionList,revisionPreview);revisions.append(revisionCaption,revisionBody);
  async function history(){
    if(!state.revision)return toast('请先打开可编辑图版');if(!await flush())return;
    const id=state.id,data=await api('/api/jobs/'+id+'/revisions');revisionList.replaceChildren();revisionPreview.replaceChildren();revisionCaption.textContent='每次恢复都会新增版本；原有版本和导出文件保留。';
    for(const row of data.revisions){const b=button('r'+row.revision+' · '+row.label+'\n'+new Date(row.created_at*1000).toLocaleString(),async()=>{
      const snapshot=await api('/api/jobs/'+id+'/revisions?revision='+row.revision);revisionPreview.replaceChildren(sanitizedSvg(snapshot.svg));
      const restore=button('将 r'+row.revision+' 恢复为新版本',async()=>{if(state.id!==id||!await flush())return;await api('/api/jobs/'+id+'/restore-revision',{base_revision:state.revision,revision:row.revision});revisions.close();await refreshJobs();await openJob(id);toast('已恢复并保存为新版本');},true);restore.disabled=row.revision===state.revision;revisionPreview.append(restore);
    });revisionList.append(b);}revisions.showModal();revisionList.querySelector('button')?.click();
  }
  async function duplicate(){if(!state.revision)return toast('历史插画请在任务页创建可编辑副本');if(!await flush())return;const scene=clone(editor.scene);scene.title+=' · 副本';await independentCopy(scene);}
  async function archive(job=state.currentJob){if(!job)return;if(job.id===state.id&&state.revision&&!await flush())return;await api('/api/jobs/'+job.id+'/document-info',{base_revision:job.id===state.id?state.revision:job.scene_revision,title:job.title,archived:!job.archived});await refreshJobs();if(job.id===state.id)state.currentJob=state.jobs.find(j=>j.id===state.id);toast(job.archived?'已移回最近图版':'已归档，可在最近图版的归档筛选中找回');}
  for(const[text,fn]of [['导入可编辑文件…',()=>file.click()],['保存可编辑文件',download],['图版名称与分类…',editInfo],['另存为副本',duplicate],['版本历史…',history],['归档／取消归档当前图版',()=>archive()]])menu.append(button(text,fn));
  $('project-title').title='双击修改图版名称和分类';$('project-title').ondblclick=editInfo;
  const filter=$('history-filter'),option=el('option','','已归档图版');option.value='archived';filter.append(option);
  const collections=el('select');collections.id='history-collection';collections.setAttribute('aria-label','按图版分类筛选');filter.after(collections);collections.onchange=()=>renderHistory();
  function renderHistory(){
    const list=$('history-list'),q=$('history-search').value.toLowerCase(),kind=filter.value,selected=collections.value;
    collections.replaceChildren();for(const value of ['',...new Set(state.jobs.map(j=>j.collection).filter(Boolean))]){const opt=el('option','',value||'所有分类');opt.value=value;collections.append(opt);}collections.value=selected;
    const jobs=state.jobs.filter(j=>(kind==='archived'?j.archived:!j.archived)&&(!selected||j.collection===selected)&&(!q||((j.title||'')+' '+(j.collection||'')).toLowerCase().includes(q))&&(kind==='editable'?j.scene_engine==='v2':kind==='illustration'?(j.illustration_mode==='image'||j.scene_engine!=='v2'):kind==='active'?['queued','processing','running'].includes(j.status):true));list.replaceChildren();
    for(const job of jobs){const row=el('article','document-row'),open=button(job.title||'未命名图版',async()=>{$('history-dialog').close();if(['queued','processing','running'].includes(job.status)&&follow)await follow(job.id);else await openJob(job.id);});const thumb=el('img');thumb.src=job.svg_url||job.png_url||'/ui/rylume-mark.svg';thumb.alt='';thumb.loading='lazy';open.prepend(thumb);const desc=el('small','',new Date(job.created*1000).toLocaleString()+' · '+(job.scene_engine==='v2'?'可编辑 r'+(job.scene_revision||'—'):'插画')+(job.collection?' · '+job.collection:''));row.append(open,desc,button(job.archived?'移回最近':'归档',()=>archive(job)));list.append(row);}if(!jobs.length)list.append(el('p','muted','没有匹配图版。可以更改分类或查看已归档图版。'));
  }
  filter.onchange=renderHistory;$('history-search').oninput=renderHistory;
  const legend=dialog('插入图例 · 预览'),legendPreview=el('div','legend-preview'),legendText=el('p','muted'),legendActions=el('div','dialog-actions');legend.classList.add('wide-dialog');legend.append(legendText,legendPreview,legendActions);
  async function prepareLegend(expand=false){
    if(!editor.scene)return toast('请先打开图版');const id=state.id,epoch=state.dirty,ops=legendOperations(editor.scene,undefined,{expand});if(!ops.length)return toast('图中还没有连线，或当前类型已经有图例');
    const candidate=clone(editor.scene);for(const op of ops){if(op.op==='canvas')candidate.canvas={width_mm:op.width_mm,height_mm:op.height_mm};else if(op.op==='add')candidate.objects.push(op.object);}
    const preview=await api('/api/scene/preview',{scene:candidate});legendPreview.replaceChildren(sanitizedSvg(preview.svg));legendText.textContent=expand?'纸张将由 '+editor.scene.canvas.width_mm+' × '+editor.scene.canvas.height_mm+' mm 调整为 '+candidate.canvas.width_mm+' × '+candidate.canvas.height_mm+' mm。确认后才会改变尺寸。':'保留 '+candidate.canvas.width_mm+' × '+candidate.canvas.height_mm+' mm 纸张。请查看图例位置；空间不足时可选择扩展纸张预览。';
    const apply=button(expand?'确认扩展尺寸并插入':'保持尺寸并插入',()=>{if(state.id!==id||state.dirty!==epoch)throw Error('图版已变化，请重新预览图例');editor.applyOperations(ops,'插入连线图例');legend.close();},true);
    legendActions.replaceChildren(button('取消',()=>legend.close()),button(expand?'返回原尺寸预览':'预览扩展纸张',()=>prepareLegend(!expand)),apply);if(!legend.open)legend.showModal();
  }
  editor.host.addEventListener('editor-request-legend',()=>prepareLegend().catch(e=>toast(e.message,true)));
  const exportSummary=el('div','export-summary');$('export-details').append(exportSummary);
  async function prepareExport(){
    const epoch=++exportEpoch;exportMeta=null;$('export-warning').hidden=true;
    if(!state.revision){exportSummary.textContent='这张原图会按原有内容保存。';$('export-menu').querySelector('[data-export=pptx] span').textContent='放入幻灯片；原图主体按图片保留';return;}
    if(!await flush())return;const id=state.id;exportSummary.textContent='正在核对当前修订…';const meta=await api('/api/jobs/'+id+'/export-info');if(state.id!==id||epoch!==exportEpoch)return;exportMeta=meta;renderExport();
  }
  function renderExport(){
    if(!exportMeta)return;const m=exportMeta,dpi=Number($('export-dpi').value);$('export-revision').textContent='当前修改已保存，选择一种格式即可导出。';$('export-revision').title='版本 r'+m.revision;exportSummary.replaceChildren(el('p','','纸张 '+m.width_mm+' × '+m.height_mm+' mm · 最小文字 '+m.min_font_pt+' pt'),el('p','','PNG '+Math.round(m.width_mm*dpi/25.4)+' × '+Math.round(m.height_mm*dpi/25.4)+' px · '+dpi+' DPI'),el('p','',m.vector?'主体为矢量；PPTX 保留图形与文字编辑。':'包含位图，请留意放大后的清晰度。'));
    $('export-menu').querySelector('[data-export=pptx] span').textContent=m.vector?'图形和文字可以分别修改 · PPTX':'放入幻灯片；位图对象不能拆分编辑 · PPTX';
    const warning=$('export-warning');warning.hidden=!m.audit.errors;warning.replaceChildren();if(m.audit.errors){warning.append(el('p','','有 '+m.audit.errors+' 处可能影响输出，建议先看一眼；也可以直接导出。'),button('在图上查看',()=>{$('export-menu').close();$('open-check-toolbar').click();}));}
    const help=el('p','muted','论文矢量：PDF / SVG；投稿图片：PNG；继续排版：PPTX。');exportSummary.append(help);
    if(m.attribution){const details=el('details');details.append(el('summary','','素材来源与图注'),el('p','credit-copy',m.attribution),button('复制素材来源',async()=>{await navigator.clipboard.writeText(m.attribution);toast('已复制，请按素材要求保留署名');}));exportSummary.append(details);}
  }
  $('toggle-export').addEventListener('click',()=>{if($('export-menu').open)prepareExport().catch(e=>toast(e.message,true));});$('export-dpi').onchange=renderExport;
  const ready=dialog('开始生成前'),readyText=el('p'),readyActions=el('div','dialog-actions');ready.append(readyText,readyActions);
  async function checkModels(mode){const config=(await api('/api/state')).config||{},missing=['text',...(mode==='image'?['image']:[])].filter(k=>!config[k]?.base_url||!config[k]?.model);if(!missing.length)return true;readyText.textContent='当前方式需要配置'+missing.map(k=>k==='text'?'文本模型':'生图模型').join('和')+'。内置模板、素材和直接编辑可以离线使用；视觉模型用于可选的审阅。';readyActions.replaceChildren(button('使用离线模板',()=>{ready.close();$('welcome-gallery').click();}),button('前往模型设置',()=>{ready.close();$('open-settings').click();},true));ready.showModal();return false;}
  return {changed,saved,opened,renderHistory,checkModels,prepareExport,history,editInfo};
}
