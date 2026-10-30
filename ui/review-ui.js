/** Plain-language layout advice with local, undoable preview candidates. */
export function findingPresentation(f,scene){
  const objects=scene?.objects||[],relations=scene?.relations||[];
  const names=(f.object_ids||[]).map(id=>objects.find(o=>o.id===id)?.label||relations.find(r=>r.id===id)?.label||'相关对象');
  const pair=names.slice(0,2).map(n=>'“'+n+'”').join('与');
  const table={
    'label-overlap':['两处文字靠得太近',`${pair}的文字范围有重叠。可以只移动文字，保留图形和连线。`,'layout',true],
    'label-object-overlap':['文字挡住了图形',`${pair}之间可能有遮挡。预览会尝试只挪开相关文字。`,'layout',true],
    'label-outside':['文字超出了纸张',`${pair}的部分文字可能在导出时被裁掉。`,'layout',true],
    'outside-canvas':['图形超出了纸张',`${pair}有一部分位于纸张外。可以预览移回纸张后的效果。`,'layout',true],
    'empty-label':['这个对象还没有名称',`${pair}尚未填写文字。如果这是装饰元素，可以保留为空。`,'layout',false],
    'overlap':['两个图形有较多重叠',`${pair}的重叠可能是有意的结合状态。请先看一下，需要时再拖开。`,'layout',false],
    'uncertain-relation':['这条连线的含义还没确定',`${pair}目前使用普通关联。可以在属性中选激活、抑制等类型，也可以暂时保留。`,'content',false],
    'compartment':['对象跨到了另一个区域',`${pair}的位置和记录的所属区域不同。请结合机制核对。`,'content',false],
    'required-object':['原始描述中的对象没有显示','请核对图层中是否隐藏了相关对象，或是否需要补回。','content',false],
    'required-relation':['原始描述中的连线没有显示','请对照研究描述确认是否有意删去，再决定是否补回。','content',false],
    'hidden-endpoint':['连线的一端被隐藏了',`${pair}中有被隐藏的对象。可以到图层中查看。`,'content',false],
    'author-review':['有一项科学内容待核对',f.message,'content',false]
  };
  const [title,detail,section,canPreview]=table[f.code]||['请留意这一处',f.message,'layout',false];
  return {title,detail,section,canPreview};
}

export function setupReview({state,editor,api,flush,toast,showRight,showLayers}){
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
      $('fix-before').replaceChildren(sanitizedSvg(state.svg));$('fix-after').replaceChildren(sanitizedSvg(result.svg));
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
    try{if(!await flush())return;const result=await api(`/api/jobs/${state.id}/layout-decision`,{base_revision:state.revision,code:f.code,object_ids:f.object_ids,restore});state.audit=result.audit;render();const n=result.audit.findings.filter(f=>f.status!=='acknowledged').length;$('open-audit').textContent=n?`排版与内容建议 · ${n}`:'查看排版建议';toast(restore?'已恢复这条提示':'已记住这个排版选择。相关对象发生变化时会重新检查。');}catch(e){toast(e.message,true);}
  }
  function render(){
    const parent=$('inspector-review');parent.replaceChildren();const a=state.audit;
    if(!a){parent.append(el('p','muted','打开可编辑图版后，这里会给出可处理的排版建议。'));return;}
    const findings=(a.findings||[]).filter(f=>f.status!=='acknowledged'),parts=findings.map(f=>({f,...findingPresentation(f,editor.scene),...(f.severity==='error'?{section:'output'}:{})}));
    parent.append(el('div','review-status',`当前修订 r${state.revision} · ${a.author_confirmed?'作者已核对':'作者待核对'} · ${a.vision?.status==='completed'?'视觉建议已获取':'视觉建议可选'}`));
    parent.append(el('p','review-intro','建议帮助你检查文字与排版，可以逐项处理，也可以继续编辑和导出。'));
    if(state.pending.length||state.saving)parent.append(el('p','review-updating','正在保存；下列建议对应上一次保存的图版。'));
    if(!parts.length)parent.append(el('div','review-clear','当前没有待处理的建议。科学机制仍请对照研究资料核对。'));
    for(const [section,title] of [['output','可能影响输出'],['layout','排版建议'],['content','科学内容待核对']]){
      const list=parts.filter(p=>p.section===section);if(!list.length)continue;
      const group=el('section','review-group');group.append(el('h3','',`${title} · ${list.length}`));
      for(const p of list){
        const card=el('article','advice-card');card.append(el('h4','',p.title),el('p','',p.detail),el('span','review-source','本机结构与排版检查 · r'+state.revision));const actions=el('div','advice-actions');
        if(p.f.object_ids?.some(id=>editor.scene?.objects.some(o=>o.id===id)||editor.scene?.relations.some(r=>r.id===id))){const locateButton=el('button','button','在图上查看');locateButton.onclick=()=>locate(p.f);actions.append(locateButton);}
        if(p.canPreview){const b=el('button','button primary','预览调整');b.onclick=()=>preview(p.f,b);actions.append(b);}
        else if(p.f.code==='empty-label'){const b=el('button','button','填写名称');b.onclick=()=>{locate(p.f);$('quick-label').focus();$('quick-label').select();};actions.append(b);}
        else if(p.f.code==='uncertain-relation'){const b=el('button','button','设置连线含义');b.onclick=()=>{locate(p.f);showRight('properties',false);};actions.append(b);}
        else if(['hidden-endpoint','required-object'].includes(p.f.code)){const b=el('button','button','查看图层');b.onclick=showLayers;actions.append(b);}
        if(p.f.severity!=='error'&&['overlap','label-overlap','label-object-overlap','empty-label'].includes(p.f.code)){const keep=el('button','text-button','保留当前排版');keep.onclick=()=>decision(p.f);actions.append(keep);}
        card.append(actions);group.append(card);
      }parent.append(group);
    }
    const vision=a.vision||{},details=el('details','review-advanced');details.append(el('summary','','更多：视觉建议与检查记录'));
    details.append(el('p','muted small','视觉模型可补充美观和语义建议，需要联网调用已配置的服务。它的意见不会自动修改图版。'));
    const visionButton=el('button','button',vision.status==='running'?'视觉建议获取中…':'获取视觉建议');visionButton.disabled=vision.status==='running';visionButton.onclick=()=>$('vision-review').click();details.append(visionButton);
    for(const f of (vision.findings||[]).filter(f=>f.status!=='dismissed'))details.append(el('p','finding',f.message));
    for(const f of (a.findings||[]).filter(f=>f.status==='acknowledged')){const row=el('div','finding');row.append(el('p','',findingPresentation(f,editor.scene).title+' · 已确认保留'));const restore=el('button','text-button','重新显示这条建议');restore.onclick=()=>decision(f,true);row.append(restore);details.append(row);}
    const raw=el('button','text-button','查看完整记录与作者确认');raw.onclick=()=>$('audit-dialog').showModal();details.append(raw);parent.append(details);
  }
  return {render};
}
