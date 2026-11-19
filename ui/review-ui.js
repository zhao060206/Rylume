/** Plain-language layout advice with local, undoable preview candidates. */
export function reviewCounts(a){
  const local=(a?.findings||[]).filter(f=>f.status!=='acknowledged').length;
  const visual=(a?.vision?.findings||[]).filter(f=>f.status!=='dismissed').length;
  return {local,visual,total:local+visual};
}
export function groupFindings(findings){
 const groups=new Map();
 for(const f of findings){const key=['overlap','label-object-overlap','label-overlap','line-label-overlap'].includes(f.code)?[f.severity,f.code,f.object_ids?.[0]].join(':'):JSON.stringify(f);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(f);}
 return [...groups.values()].sort((a,b)=>(a[0].severity==='error'?0:1)-(b[0].severity==='error'?0:1));
}
export function findingPresentation(f,scene){
  const objects=scene?.objects||[],relations=scene?.relations||[];
  const objectName=id=>{const o=objects.find(o=>o.id===id);return o?.label||o?.display_name||null;};
  const names=(f.object_ids||[]).map(id=>{
    const link=relations.find(r=>r.id===id);
    if(!link)return objectName(id)||id;
    const endpoints=`${objectName(link.source)||'未命名起点'} → ${objectName(link.target)||'未命名终点'}`;
    return link.label?`${endpoints}（${link.label}）`:endpoints;
  });
  const pair=names.slice(0,2).map(n=>'“'+n+'”').join('与');
  const table={
    'label-overlap':['两处文字靠得太近',`${pair}的文字范围有重叠。可以只移动文字，保留图形和连线。`,'layout',true],
    'text-wrap':['文字框太窄',`${pair}被挤成多行或超出边界。请在属性中加宽文字框。`,'layout',false],
    'label-object-overlap':['文字挡住了图形',`${pair}之间可能有遮挡。预览会尝试只挪开相关文字。`,'layout',true],
    'label-outside':['文字超出了纸张',`${pair}的部分文字可能在导出时被裁掉。`,'layout',true],
    'line-label-overlap':['连线穿过了文字',`${pair}发生交叉。可预览绕开文字的路径，或手动拖动连线中点。`,'layout',true],
    'label-detached':['文字离所属图形太远',`${pair}的文字位置可能让读者误认归属。预览可将文字放回附近。`,'layout',true],
    'containment':['对象离开了所属结构',`${pair}的包含位置不一致。请核对后拖回内部或边界。`,'content',false],
    'outside-canvas':['图形超出了纸张',`${pair}有一部分位于纸张外。可以预览移回纸张后的效果。`,'layout',true],
    'empty-label':['这个对象还没有名称',`${pair}尚未填写文字。如果这是装饰元素，可以保留为空。`,'layout',false],
    'overlap':['两个图形有较多重叠',`${pair}的重叠可能是有意的结合状态。请先看一下，需要时再拖开。`,'layout',false],
    'uncertain-relation':['这条连线需要作者核对',`${pair}的含义或证据待确认。选择“设置连线含义”核对类型和说明。`,'content',false],
    'compartment':['对象跨到了另一个区域',`${pair}的位置和记录的所属区域不同。请结合机制核对。`,'content',false],
    'required-object':['原始描述中的对象没有显示','请核对图层中是否隐藏了相关对象，或是否需要补回。','content',false],
    'required-relation':['原始描述中的连线没有显示','请对照研究描述确认是否有意删去，再决定是否补回。','content',false],
    'hidden-endpoint':['连线的一端被隐藏了',`${pair}中有被隐藏的对象。可以到图层中查看。`,'content',false],
    'author-review':['有一项科学内容待核对',f.message,'content',false]
  };
  const [title,detail,section,canPreview]=table[f.code]||['请留意这一处',f.message,'layout',false];
  return {title,detail,section,canPreview};
}

export function setupReview({state,editor,api,flush,toast,openRelationDefinitions,showLayers}){
  const $=id=>document.getElementById(id),el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  let pending=null;
  function locate(f){
    const existing=new Set([...(editor.scene?.objects||[]),...(editor.scene?.relations||[])].map(o=>o.id));
    const ids=(f.object_ids||[]).filter(id=>existing.has(id));editor.setSelection(ids);
    if(ids.length)editor.revealSelection();else toast('这个提示涉及原始描述，请展开任务页查看研究内容。');
  }
  async function preview(f,button){
    button.disabled=true;
    try{
      if(!await flush())return;
      const result=await api(`/api/jobs/${state.id}/preview-fix`,{base_revision:state.revision,code:f.code,object_ids:f.object_ids});
      if(!result.changed){toast(result.message);locate(f);return;}
      const {sanitizedSvg}=await import('./canvas-editor.js');pending={...result,jobId:state.id,dirty:state.dirty};
      const before=state.svg||(await api(`/api/jobs/${state.id}/revisions?revision=${state.revision}`)).svg;
      $('fix-before').replaceChildren(sanitizedSvg(before));$('fix-after').replaceChildren(sanitizedSvg(result.svg));
      $('fix-description').textContent=findingPresentation(f,editor.scene).detail;
      $('fix-summary').textContent=`仅调整 ${result.operations.length} 个相关对象的排版；应用后可以撤销。`;
      $('apply-fix-preview').disabled=false;$('fix-preview-dialog').showModal();
    }catch(e){toast(e.message,true);}finally{button.disabled=false;}
  }
  $('apply-fix-preview').onclick=()=>{
    if(!pending||pending.jobId!==state.id||pending.base_revision!==state.revision||pending.dirty!==state.dirty||state.pending.length)return toast('图版已变化，请关闭预览后重新查看。',true);
    const candidate=pending;pending=null;$('fix-preview-dialog').close();editor.applyOperations(candidate.operations,'应用局部排版建议');toast('已应用局部调整。点“撤销”可以恢复。');
  };
  async function decision(f,restore=false){
    try{if(!await flush())return;const list=Array.isArray(f)?f:[f];const result=await api(`/api/jobs/${state.id}/layout-decision`,{base_revision:state.revision,findings:list.map(f=>({code:f.code,object_ids:f.object_ids})),restore});state.audit=result.audit;render();const n=reviewCounts(result.audit).total;$('open-audit').textContent=n?`排版与内容建议 · ${n}`:'查看排版建议';toast(restore?'已恢复这条提示':'已记住这个排版选择。相关对象发生变化时会重新检查。');}catch(e){toast(e.message,true);}
  }
  function render(){
    const parent=$('inspector-review');parent.replaceChildren();const a=state.audit;
    if(!a){parent.append(el('p','muted','打开可编辑图版后，这里会给出可处理的排版建议。'));return;}
    const findings=(a.findings||[]).filter(f=>f.status!=='acknowledged'),parts=groupFindings(findings).map(members=>{const f=members[0];return {f,members,...findingPresentation(f,editor.scene),...(f.severity==='error'?{section:'output'}:{})};});
    const vision=a.vision||{},visualFindings=(vision.findings||[]).filter(f=>f.status!=='dismissed');
    parent.append(el('div','review-status',parts.length||visualFindings.length
      ?`本机检查 ${parts.length} 组建议 · ${vision.status==='completed'?'图像核对 '+visualFindings.length+' 条意见待确认':vision.status==='running'?'正在视觉核验':'当前修订尚未视觉核验'}`
      :vision.status==='unavailable'?'本机检查暂无建议，图像核对未完成':'本机检查暂无建议'));
    parent.append(el('p','review-intro','点「在图上查看」就能找到位置。调整前可以预览，改错后可以撤销。科学内容仍需由你核对。'));
    if(state.pending.length||state.saving)parent.append(el('p','review-updating','正在保存；下列建议对应上一次保存的图版。'));
    if(!parts.length&&!visualFindings.length)parent.append(el('div','review-clear','本机结构与排版检查没有待处理的建议。科学机制仍请对照研究资料核对。'));
    for(const [section,title] of [['output','可能影响输出'],['layout','排版建议'],['content','科学内容待核对']]){
      const list=parts.filter(p=>p.section===section);if(!list.length)continue;
      const group=el('section','review-group');group.append(el('h3','',`${title} · ${list.length}`));
      for(const p of list){
        const card=el('article','advice-card');card.append(el('h4','',p.title),el('p','',p.detail),el('span','review-source','本机结构与排版检查 · r'+state.revision));const actions=el('div','advice-actions');
        if(p.members.length>1){const list=el('details');list.append(el('summary','',`同一对象涉及 ${p.members.length} 处 · 展开逐一查看`));for(const f of p.members){const row=el('div','finding');row.append(el('p','',findingPresentation(f,editor.scene).detail));const b=el('button','text-button','在图上查看');b.onclick=()=>locate(f);row.append(b);list.append(row);}card.append(list);}
        if(p.f.object_ids?.some(id=>editor.scene?.objects.some(o=>o.id===id)||editor.scene?.relations.some(r=>r.id===id))){const locateButton=el('button','button','在图上查看');locateButton.onclick=()=>locate(p.f);actions.append(locateButton);}
        if(p.canPreview){const b=el('button','button primary','预览调整');b.onclick=()=>preview(p.f,b);actions.append(b);}
        else if(p.f.code==='empty-label'){const b=el('button','button','填写名称');b.onclick=()=>{locate(p.f);editor.ensureSelectionVisible();editor.editSelectedLabel();};actions.append(b);}
        else if(p.f.code==='uncertain-relation'){const b=el('button','button','设置连线含义');b.onclick=()=>{if(!openRelationDefinitions(p.f.object_ids[0]))toast('连线已变更，请查看保存后的检查结果。');};actions.append(b);}
        else if(['hidden-endpoint','required-object'].includes(p.f.code)){const b=el('button','button','查看图层');b.onclick=showLayers;actions.append(b);}
        if(p.f.severity!=='error'&&['overlap','label-overlap','label-object-overlap','label-detached','line-label-overlap','empty-label'].includes(p.f.code)){const keep=el('button','text-button',p.members.length>1?`确认保留这 ${p.members.length} 处排版`:'保留当前排版');keep.onclick=()=>decision(p.members);actions.append(keep);}
        card.append(actions);group.append(card);
      }parent.append(group);
    }
    const details=el('details','review-advanced');details.append(el('summary','','更多：视觉建议与检查记录'));
    if(a.source_overlaps?.length){const baseline=el('details');baseline.append(el('summary','',`原图固有交叠 · ${a.source_overlaps.length} 处包围框`));baseline.append(el('p','muted small','这些对应区域保持原图的尺寸和相对位置，透明轮廓的包围框相交不代表新增遮挡。移动、缩放或改字后会重新检查。'));details.append(baseline);}
    if(!['completed','running','unavailable'].includes(vision.status))parent.append(el('p','review-updating','当前修订尚未进行视觉核验。本机检查不代表图像内容已核验。'));
    for(const old of (a.vision_history||[])){
      const pending=(old.findings||[]).filter(f=>f.status!=='dismissed');
      const record=el('details','review-advanced');record.append(el('summary','',`r${old.revision} 的视觉记录 · 已过期 · ${pending.length} 项待复验`));
      record.append(el('p','muted small','这些意见对应旧修订，修改后的结果需要重新核验。'));
      for(const f of pending)record.append(el('p','finding',f.message));
      if(old.raw)record.append(el('pre','review-raw',old.raw));
      parent.append(record);
    }
    if(visualFindings.length){const group=el('section','review-group');group.append(el('h3','','模型发现的需求与画面问题'));for(const f of visualFindings){const card=el('article','advice-card');card.append(el('p','',f.message),el('span','review-source','图像核对 · 待作者确认'));group.append(card);}parent.append(group);}
    else if(vision.status==='unavailable')parent.append(el('p','review-updating','图像核对未完成：'+(vision.error||'模型暂不可用')+'。当前仅有本机几何检查结果。'));
    details.append(el('p','muted small','视觉模型可补充美观和语义建议，需要联网调用已配置的服务。它的意见不会自动修改图版。'));
    const visionButton=el('button','button',vision.status==='running'?'视觉建议获取中…':'获取视觉建议');visionButton.disabled=vision.status==='running';visionButton.onclick=()=>$('vision-review').click();details.append(visionButton);
    for(const f of (vision.findings||[]).filter(f=>f.status!=='dismissed'))details.append(el('p','finding',f.message));
    for(const f of (a.findings||[]).filter(f=>f.status==='acknowledged')){const row=el('div','finding');row.append(el('p','',findingPresentation(f,editor.scene).title+' · 已确认保留'));const restore=el('button','text-button','重新显示这条建议');restore.onclick=()=>decision(f,true);row.append(restore);details.append(row);}
    const exportButton=el('button','button full','继续导出图片');exportButton.onclick=()=>$('toggle-export').click();parent.append(exportButton);
    const raw=el('button','text-button','查看完整记录与作者确认');raw.onclick=()=>$('audit-dialog').showModal();details.append(raw);parent.append(details);
  }
  return {render};
}
