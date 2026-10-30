import {sanitizedSvg} from './canvas-editor.js';
const NS='http://www.w3.org/2000/svg';
const clone=x=>JSON.parse(JSON.stringify(x));
const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
export function regionFromPoints(a,b,canvas){
  const x=Math.max(0,Math.min(canvas.width_mm,Math.min(a.x,b.x))),y=Math.max(0,Math.min(canvas.height_mm,Math.min(a.y,b.y)));
  return {x,y,w:Math.max(0,Math.min(canvas.width_mm,Math.max(a.x,b.x))-x),h:Math.max(0,Math.min(canvas.height_mm,Math.max(a.y,b.y))-y)};
}
export function setupAnnotations({state,editor,api,flush,toast,workspace,onApplied,canSubmit=async()=>true}){
  let job=null,notes=[],revision=0,epoch=0,savedEpoch=0,timer=null,saving=null,conflict=false,mode=null,drag=null,replaceId=null,selected=null,visible=true,currentRun=null,runs=[],recovery=null,polling=false,pollJob=null,panels=null,requestId=null;
  const host=editor.host,button=el('button','tool text-tool','批注修改');button.id='open-annotations';
  document.getElementById('open-check-toolbar').before(button);
  const panel=el('aside','annotation-panel');panel.hidden=true;panel.setAttribute('aria-label','图版批注');
  const head=el('div','annotation-head'),title=el('h2','','图版批注'),close=el('button','icon-button','×');close.setAttribute('aria-label','关闭批注面板');head.append(title,close);
  const help=el('p','annotation-help','圈出位置，分别写清要求；提交后逐条修改与核验。批注不会进入导出文件。');
  const tools=el('div','annotation-tools'),rect=el('button','button','方框批注'),ellipse=el('button','button','圆框批注'),whole=el('button','button','整图要求'),hide=el('button','text-button','隐藏批注');tools.append(rect,ellipse,whole,hide);
  const hint=el('p','annotation-hint','先画一个框，或添加整图要求。'),saveState=el('p','annotation-save',''),list=el('div','annotation-list'),status=el('p','annotation-status','');status.setAttribute('role','status');
  const cancelFrame=el('button','text-button','取消圈框');cancelFrame.hidden=true;cancelFrame.onclick=()=>setMode(null);tools.append(cancelFrame);
  const runControls=el('div','annotation-run-controls'),submit=el('button','button primary','按全部批注修改'),cancel=el('button','button','取消任务'),retrySave=el('button','text-button','重试保存'),reload=el('button','text-button','重新载入批注');cancel.hidden=true;retrySave.hidden=true;reload.hidden=true;runControls.append(submit,cancel);
  const result=el('div','annotation-result'),history=el('div','annotation-history'),rollback=el('button','button','恢复修改前的版本');rollback.hidden=true;
  const steps=el('ol','annotation-steps');for(const text of ['1 标记要求','2 AI 修改与核验','3 对比后应用'])steps.append(el('li','',text));panel.append(steps);
  const footer=el('div','annotation-footer');footer.append(status,runControls);
  panel.append(head,help,tools,hint,saveState,retrySave,reload,list,result,rollback,history,footer);workspace.append(panel);
  const compare=document.createElement('dialog');compare.className='annotation-comparison';compare.innerHTML='<div class="annotation-head"><h2>批注修改对比</h2><button class="icon-button" aria-label="关闭批注对比">×</button></div><div class="annotation-compare-grid"><section><h3>修改前</h3><div id="annotation-before"></div></section><section><h3>修改后候选</h3><div id="annotation-after"></div></section></div><div class="annotation-verification"></div><div class="annotation-dialog-actions"></div>';document.body.append(compare);compare.querySelector('button').onclick=()=>compare.close();
  const restore=document.createElement('dialog');restore.className='annotation-restore';const restoreText=el('p'),keep=el('button','button','保留当前图版'),restoreGo=el('button','button primary','恢复并保存为新版本');restore.append(el('h2','','恢复修改前'),restoreText,keep,restoreGo);document.body.append(restore);keep.onclick=()=>restore.close();
  const drafts=new Map();
  function cacheDraft(){if(job){const record={notes:clone(notes),revision,epoch};drafts.set(job,record);try{localStorage.setItem('cfs-annotation-draft-'+job,JSON.stringify(record));}catch{}}}
  function clearDraft(id){drafts.delete(id);try{localStorage.removeItem('cfs-annotation-draft-'+id);}catch{}}
  function dirty(){epoch++;requestId=null;cacheDraft();clearTimeout(timer);timer=setTimeout(()=>save().catch(()=>{}),500);saveState.textContent=conflict?'批注版本冲突，本地草稿保留':'批注待保存';renderOverlay();}
  function setMode(next,id=null){mode=next;replaceId=id;drag=null;editor.cancelGesture();editor.setTool('select');host.style.cursor=next?'crosshair':'default';cancelFrame.hidden=!next;rect.setAttribute('aria-pressed',String(next==='rect'));ellipse.setAttribute('aria-pressed',String(next==='ellipse'));hint.textContent=next?'在图纸上按住并拖动，松开后填写要求；可点“取消圈框”。':'可以继续添加批注，也可以提交全部要求。';renderOverlay();}
  function open(){
    if(!state.revision||!editor.scene)return toast('请先打开可编辑图版；旧插画可先创建可编辑副本');
    const width=host.clientWidth;editor.fitMode=false;if(panel.hidden){panels={left:workspace.classList.contains('left-collapsed'),right:workspace.classList.contains('properties-hidden')};workspace.classList.add('left-collapsed','properties-hidden','annotations-open');panel.hidden=false;button.setAttribute('aria-pressed','true');editor.offset.x+=(host.clientWidth-width)/2;editor.position();}
    if(job!==state.id)load(state.id);else render();
  }
  function dismiss(){const width=host.clientWidth;editor.fitMode=false;panel.hidden=true;button.setAttribute('aria-pressed','false');workspace.classList.remove('annotations-open');if(panels){workspace.classList.toggle('left-collapsed',panels.left);workspace.classList.toggle('properties-hidden',panels.right);}panels=null;setMode(null);editor.offset.x+=(host.clientWidth-width)/2;editor.position();}
  workspace.addEventListener('workspace-panel-request',()=>{if(!panel.hidden)dismiss();});
  button.onclick=()=>panel.hidden?open():dismiss();close.onclick=dismiss;rect.onclick=()=>setMode('rect');ellipse.onclick=()=>setMode('ellipse');whole.onclick=()=>add({shape:'whole',x:0,y:0,w:editor.scene.canvas.width_mm,h:editor.scene.canvas.height_mm});hide.onclick=()=>{visible=!visible;hide.textContent=visible?'隐藏批注':'显示批注';renderOverlay();};retrySave.onclick=()=>save().catch(()=>{});reload.onclick=()=>{if(epoch!==savedEpoch){saveState.textContent='本地文字尚未保存。请先复制要求；重新打开图版可载入服务器版本。';return;}load(job);};
  function add(region){
    if(notes.length>=30)return toast('每批最多 30 条批注');
    if(replaceId){const note=notes.find(n=>n.id===replaceId);if(note)Object.assign(note,region);selected=replaceId;}
    else{selected='n_'+crypto.randomUUID().replaceAll('-','').slice(0,12);notes.push({id:selected,...region,instruction:'',original_instruction:''});}
    setMode(null);dirty();render();list.querySelector(`[data-note-id="${selected}"] textarea`)?.focus();
  }
  function renderOverlay(){
    const svg=host.querySelector('svg');if(!svg)return;svg.querySelector('#annotation-overlay')?.remove();if(!visible&&!drag)return;
    const layer=document.createElementNS(NS,'g');layer.id='annotation-overlay';layer.setAttribute('data-editor-overlay','true');layer.style.pointerEvents='none';
    function draw(n,index){if(n.shape==='whole')return;const mark=document.createElementNS(NS,n.shape==='ellipse'?'ellipse':'rect'),attrs=n.shape==='ellipse'?{cx:n.x+n.w/2,cy:n.y+n.h/2,rx:n.w/2,ry:n.h/2}:{x:n.x,y:n.y,width:n.w,height:n.h};for(const[k,v]of Object.entries({...attrs,fill:'none',stroke:n.id===selected?'#AF482F':'#BD7557','stroke-width':n.id===selected?2:1.3,'vector-effect':'non-scaling-stroke','stroke-dasharray':'5 3'}))mark.setAttribute(k,v);layer.append(mark);const badge=document.createElementNS(NS,'text');badge.setAttribute('x',n.x+.7);badge.setAttribute('y',n.y+3.3);badge.setAttribute('font-size',3.1);badge.setAttribute('font-family','Arial');badge.setAttribute('fill','#A33F2C');badge.textContent=String(index);layer.append(badge);}
    if(visible)notes.forEach((n,i)=>draw(n,i+1));if(drag?.end)draw({...regionFromPoints(drag.start,drag.end,editor.scene.canvas),shape:mode},'+');svg.append(layer);
  }
  editor.onAnnotationRender=renderOverlay;
  host.addEventListener('pointerdown',e=>{if(!mode||!editor.scene||e.button!==0)return;const p=editor.world(e),c=editor.scene.canvas;if(p.x<0||p.y<0||p.x>c.width_mm||p.y>c.height_mm)return;e.preventDefault();e.stopImmediatePropagation();host.setPointerCapture(e.pointerId);drag={start:p,id:e.pointerId};},true);
  host.addEventListener('pointermove',e=>{if(!drag)return;e.preventDefault();e.stopImmediatePropagation();drag.end=editor.world(e);renderOverlay();},true);
  host.addEventListener('pointerup',e=>{if(!drag)return;e.preventDefault();e.stopImmediatePropagation();const region=regionFromPoints(drag.start,editor.world(e),editor.scene.canvas);drag=null;if(region.w<1||region.h<1){renderOverlay();return;}add({...region,shape:mode});},true);
  host.addEventListener('pointercancel',()=>{drag=null;renderOverlay();},true);
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&(mode||drag)){e.preventDefault();e.stopImmediatePropagation();setMode(null);}},true);
  async function save(){
    clearTimeout(timer);if(!job||epoch===savedEpoch)return true;if(saving){await saving;return save();}if(conflict)throw Error('批注存在版本冲突，本地文字仍保留');
    const id=job,at=epoch,snapshot=clone(notes);saveState.textContent='正在保存批注…';
    saving=(async()=>{try{const doc=await api(`/api/jobs/${id}/annotations`,{base_annotation_revision:revision,notes:snapshot},'PUT');if(job!==id)return false;revision=doc.annotation_revision;savedEpoch=at;if(epoch===at)clearDraft(id);else cacheDraft();saveState.textContent=epoch===at?'批注已保存':'批注待保存';retrySave.hidden=true;reload.hidden=true;return true;}catch(e){if(job===id){conflict=e.status===409;cacheDraft();saveState.textContent=e.message+'；本地批注保留';retrySave.hidden=false;reload.hidden=!conflict;}throw e;}})();
    try{return await saving;}finally{saving=null;if(job===id&&epoch!==savedEpoch&&!conflict)timer=setTimeout(()=>save().catch(()=>{}),1500);}
  }
  async function load(id){
    clearTimeout(timer);const previous=job;if(previous&&epoch!==savedEpoch){try{await save();}catch{if(state.id===previous)return;toast('前一图版的批注未保存，请返回该图查看',true);}}
    job=id;notes=[];epoch=0;savedEpoch=0;revision=0;selected=null;currentRun=null;runs=[];recovery=null;conflict=false;requestId=null;setMode(null);render();if(!id)return;
    try{const doc=await api(`/api/jobs/${id}/annotations`);if(job!==id)return;notes=doc.notes||[];revision=doc.annotation_revision;runs=doc.runs||[];recovery=doc.recovery;saveState.textContent=notes.length?'批注已保存':'';let cached=drafts.get(id);try{cached ||= JSON.parse(localStorage.getItem('cfs-annotation-draft-'+id)||'null');}catch{}if(cached?.notes){notes=cached.notes;epoch=1;savedEpoch=0;conflict=cached.revision!==revision;revision=cached.revision;saveState.textContent=conflict?'检测到本地批注与服务器版本不同，本地草稿保留；请先复制内容后合并。':'已恢复尚未保存的本地批注';if(!conflict)timer=setTimeout(()=>save().catch(()=>{}),500);}render();const active=runs.find(r=>['queued','running'].includes(r.status))||runs[0];if(active){await fetchRun(active.id);if(['queued','running'].includes(active.status))poll();}}
    catch(e){if(job===id){saveState.textContent='批注载入失败：'+e.message;toast(saveState.textContent,true);}}
  }
  function render(){
    list.replaceChildren();for(const[note,index]of notes.map((n,i)=>[n,i])){
      const card=el('section','annotation-card'+(selected===note.id?' active':''));card.dataset.noteId=note.id;
      const row=el('div','annotation-card-head'),name=el('button','text-button',`${index+1} · ${note.target_ids?'所选对象（'+note.target_ids.length+' 项）':note.shape==='whole'?'整图要求':note.shape==='ellipse'?'圆框区域':'方框区域'}`),remove=el('button','text-button','删除');
      name.onclick=()=>{selected=note.id;renderOverlay();for(const c of list.children)c.classList.toggle('active',c===card);};remove.onclick=()=>{notes=notes.filter(n=>n.id!==note.id);dirty();render();};row.append(name,remove);
      const input=el('textarea');input.value=note.instruction;input.maxLength=2000;input.placeholder='例如：将这里的标签改为 STAT3，其他内容保持不变';input.setAttribute('aria-label',`批注 ${index+1} 的修改要求`);input.oninput=()=>{note.instruction=input.value;note.original_instruction=input.value;dirty();renderResult();};input.onfocus=()=>{selected=note.id;renderOverlay();};
      const actions=el('div','annotation-card-actions'),enhance=el('button','text-button','保持原意优化表达'),redraw=el('button','text-button','重新圈定');redraw.hidden=note.shape==='whole'||!!note.target_ids;redraw.onclick=()=>setMode(note.shape,note.id);
      const suggestion=el('div','annotation-enhancement');suggestion.hidden=true;
      enhance.onclick=async()=>{if(!note.instruction.trim())return toast('先填写这处修改要求');enhance.disabled=true;const original=note.instruction,id=job;try{const res=await api(`/api/jobs/${id}/annotation-enhance`,{instruction:original});if(job!==id||!notes.includes(note)||note.instruction!==original)return;const before=el('p','','原文：'+original),after=el('p','','建议：'+res.enhanced),adopt=el('button','button','采用建议'),keep=el('button','text-button','保留原文');suggestion.replaceChildren(before,after,el('p','muted small',(res.notes||[]).join(' ')),adopt,keep);suggestion.hidden=false;adopt.disabled=res.enhanced===original;adopt.onclick=()=>{note.original_instruction=original;note.instruction=res.enhanced;input.value=res.enhanced;suggestion.hidden=true;dirty();};keep.onclick=()=>suggestion.hidden=true;}catch(e){toast(e.message,true);}finally{enhance.disabled=false;}};
      actions.append(enhance,redraw);card.append(row,input,actions,suggestion);list.append(card);
    }
    if(!notes.length)list.append(el('p','muted','可批注多处。先圈位置，再填写这一处要改什么。'));
    renderOverlay();renderResult();
  }
  async function fetchRun(runId){const id=job;const res=await api(`/api/jobs/${id}/annotation-runs?run_id=${runId}`);if(job===id){currentRun=res.run;renderResult();}return res.run;}
  async function poll(){if(polling&&pollJob===job)return;polling=true;const id=job;pollJob=id;try{while(job===id&&currentRun&&['queued','running'].includes(currentRun.status)){await new Promise(r=>setTimeout(r,900));if(job!==id)break;await fetchRun(currentRun.id);}}catch(e){if(job===id)status.textContent='进度读取暂时失败，任务与原图保留。重新打开面板可恢复查看。';}finally{if(pollJob===id)polling=false;}}
  submit.onclick=async()=>{if(!notes.length)return toast('先添加批注');if(notes.some(n=>!n.instruction.trim()))return toast('请为每处批注填写要求');if(state.active)return toast('已有生成任务，请先完成或取消');submit.disabled=true;try{if(!await canSubmit()||!await flush()||!await save())return;const id=job;requestId ||= crypto.randomUUID();const res=await api(`/api/jobs/${id}/annotation-runs`,{base_revision:state.revision,annotation_revision:revision,request_id:requestId});if(job!==id)return;currentRun=res.run;runs=[currentRun,...runs.filter(r=>r.id!==currentRun.id)];setMode(null);renderResult();poll();}catch(e){toast(e.message,true);}finally{renderResult();}};
  cancel.onclick=async()=>{if(!currentRun)return;try{const res=await api(`/api/jobs/${job}/annotation-cancel`,{run_id:currentRun.id});currentRun=res.run;requestId=null;renderResult();}catch(e){toast(e.message,true);}};
  function checkList(parent,run){
    const candidate=run.candidate||{};for(const c of candidate.checks||run.checks||[]){const number=(run.notes||notes).findIndex(n=>n.id===c.note_id)+1;const card=el('div','annotation-check '+c.status);card.append(el('strong','',`批注 ${number||c.note_id} · ${{verified:'已核验',needs_review:'仍需核对',unfulfilled:'未满足'}[c.status]||'待核对'}`),el('p','',c.message));if(c.evidence)card.append(el('p','annotation-evidence',c.evidence));parent.append(card);}
  }
  function renderResult(){
    const busy=currentRun&&['queued','running'].includes(currentRun.status);submit.disabled=!!busy||!job||!notes.length||notes.some(n=>!n.instruction.trim());for(const [i,n]of [...steps.children].entries())n.classList.toggle('active',i===(busy?1:currentRun?.candidate?2:0));cancel.hidden=!busy;
    if(currentRun&&!busy&&['failed','cancelled','interrupted','completed'].includes(currentRun.status))requestId=null;
    status.textContent=currentRun?`${currentRun.round?`第 ${currentRun.round}/3 轮 · `:''}${currentRun.message||currentRun.status}${currentRun.error?'：'+currentRun.error:''}`:'';result.replaceChildren();
    if(currentRun?.candidate){const c=currentRun.candidate;result.append(el('h3','','候选与核验'));result.append(el('p','annotation-help',c.verification?.mode==='vision_and_structure'?'已进行图像与结构核验；仍请作者对比确认。':c.verification?.mode==='structure_and_text'?'已核对结构与文字；本轮没有图像核验。':'核验服务未完整返回，当前图版保持原样。'));checkList(result,currentRun);const preview=el('button','button','对比修改前后');preview.onclick=()=>showComparison(currentRun).catch(e=>toast(e.message,true));result.append(preview);}
    rollback.hidden=!recovery?.can_rollback;history.replaceChildren();const details=el('details'),summary=el('summary','','修改记录');details.append(summary);for(const r of runs.slice(0,12)){const b=el('button','text-button',`r${r.base_revision} · ${{completed:'候选已生成',running:'修改中',queued:'排队中',cancelled:'已取消',failed:'未完成',interrupted:'已中断'}[r.status]||r.status}${r.applied_revision?' · 已应用 r'+r.applied_revision:''}`);b.onclick=()=>fetchRun(r.id).catch(e=>toast(e.message,true));details.append(b);}history.append(details);
  }
  async function showComparison(run){
    const id=job,base=await api('/api/jobs/'+id+'/revisions?revision='+run.base_revision);if(job!==id)return;
    const {setupComparison}=await import('./candidate-comparison.js');
    compare.querySelector('#annotation-before').replaceChildren(sanitizedSvg(run.before_svg||state.svg));compare.querySelector('#annotation-after').replaceChildren(sanitizedSvg(run.candidate.preview_svg));const checks=compare.querySelector('.annotation-verification');checks.replaceChildren();checkList(checks,run);const actions=compare.querySelector('.annotation-dialog-actions'),keep=el('button','button','保留当前图版'),apply=el('button','button primary','应用修改版');keep.onclick=()=>compare.close();apply.disabled=!run.candidate.can_apply||!!run.applied_revision;apply.onclick=async()=>{apply.disabled=true;try{if(!await flush()||!await save())return;const id=job;const data=await api(`/api/jobs/${id}/annotation-apply`,{run_id:run.id,base_revision:state.revision});if(state.id!==id)return;await onApplied(data);recovery=data.recovery;compare.close();await load(id);toast('修改版已保存，可随时恢复修改前版本');}catch(e){toast(e.message,true);}finally{apply.disabled=!run.candidate.can_apply||!!run.applied_revision;}};actions.replaceChildren(keep,apply);setupComparison(compare,{beforeScene:base.scene,afterScene:run.candidate.preview_scene,operations:run.candidate.operations,notes:run.notes||notes});compare.showModal();
  }
  rollback.onclick=()=>{restoreText.textContent=`将整张图恢复到批注修改前的 r${recovery.before_revision}。后续手动修改也会一并回退；当前版本仍保留在历史修订中。`;restore.showModal();};restoreGo.onclick=async()=>{restoreGo.disabled=true;try{if(!await flush())return;const id=job,data=await api(`/api/jobs/${id}/annotation-rollback`,{base_revision:state.revision,run_id:recovery.run_id});if(state.id!==id)return;await onApplied(data);restore.close();await load(id);toast('已恢复修改前图版，并保存为新版本');}catch(e){toast(e.message,true);}finally{restoreGo.disabled=false;}};
  window.addEventListener('beforeunload',()=>{if(job&&epoch!==savedEpoch)fetch(`/api/jobs/${job}/annotations`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({base_annotation_revision:revision,notes}),keepalive:true}).catch(()=>{});});
  async function forSelection(ids){
    const id=state.id;if(job!==id)await load(id);if(job!==id)return;open();
    const scene=editor.scene,selected=new Set(ids),objects=scene.objects.filter(o=>selected.has(o.id)||scene.relations.some(r=>selected.has(r.id)&&(r.source===o.id||r.target===o.id)));
    if(!objects.length||objects.every(o=>o.locked))return toast('请选择未锁定的可编辑对象');
    const x=Math.max(0,Math.min(...objects.map(o=>o.x))-3),y=Math.max(0,Math.min(...objects.map(o=>o.y))-3),right=Math.min(scene.canvas.width_mm,Math.max(...objects.map(o=>o.x+o.w))+3),bottom=Math.min(scene.canvas.height_mm,Math.max(...objects.map(o=>o.y+o.h))+7);
    add({shape:'rect',x,y,w:Math.max(1,right-x),h:Math.max(1,bottom-y),target_ids:ids});
    toast('已添加所选对象要求；提交时会处理面板中的全部批注');
  }
  return {open,load,forSelection,refresh:()=>{button.disabled=!state.revision;renderOverlay();}};
}
