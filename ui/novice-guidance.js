import {preserveCanvasView} from './panel-layout.js';
import {RELATION_DEFINITIONS} from './canvas-editor.js';

/** The next useful action follows the actual document, rather than a fixed tour. */
export function workflowHint({scene,selectedIds=[],tool='select',connectStart=null,legacy=false,activeLabel=null}) {
  if(legacy)return {title:'这是一张原图',detail:'可以直接导出；需要移动图中对象时，先创建可编辑副本。',action:'export',label:'导出图片'};
  const objects=scene?.objects.filter(o=>o.visible!==false&&o.role!=='context')||[];
  const selected=objects.filter(o=>selectedIds.includes(o.id));
  const relation=scene?.relations.find(r=>selectedIds.includes(r.id));
  if(tool==='connect') {
    const source=objects.find(o=>o.id===connectStart);
    return {title:source?`再点一下终点：从「${source.label||'所选对象'}」连出去`:'先点一下起点，再点一下终点',detail:'上方可选择这条线的含义。完成后自动回到选择工具。',action:'cancel',label:'取消连线'};
  }
  if(tool==='text')return {title:'在纸张上点一下，放置文字',detail:'输入后点「完成」，或点击空白处保存。',action:'cancel',label:'取消放置'};
  if(tool==='pan')return {title:'按住鼠标拖动，移动整张画布',detail:'需要移动单个图形时，回到「选择」工具。',action:'select',label:'回到选择'};
  if(!objects.length)return {title:'先放入第一个素材',detail:'点击左侧素材即可添加，也可以直接输入一段文字。',action:'assets',label:'添加素材'};
  if(activeLabel&&selectedIds.length===1&&selectedIds[0]===activeLabel.id)return {title:'正在调整文字',detail:'直接拖动文字；方向键微调，Shift 加大步长。双击或点右侧按钮改字。',action:'edit',label:'修改文字'};
  if(relation){const def=RELATION_DEFINITIONS.find(d=>d.id===relation.type);return {title:relation.type==='associates'?'这条连线表达什么？':'连线含义：'+(def?.title||'待确认'),detail:(def?.description||'在上方选择含义。')+' 移动图形时，连线会跟随。',action:'meaning',label:'查看连线含义'};}
  if(selected.length===1&&selected[0].locked)return {title:'这个对象已锁定',detail:'需要修改时，在图层中解除锁定。',action:'layers',label:'打开图层'};
  if(selected.length>1)return {title:`已选中 ${selected.length} 个对象`,detail:'一起拖动；在「排列」中对齐、等距分布或组合。',action:'arrange',label:'排列所选对象'};
  if(selected.length===1)return {title:`已选中「${selected[0].label||'未命名对象'}」`,detail:'拖动图形移动整体；拖动文字可单独挪动，双击改字。误操作可点「撤销」。',action:'edit',label:'修改文字'};
  if(objects.length<2)return {title:'第一个素材已经放好了',detail:'再加一个素材，就可以用连线表达它们的关系。',action:'assets',label:'再加一个素材'};
  if(!scene.relations.length)return {title:'对象已经准备好了，可以添加连线',detail:'点击「添加连线」，然后依次点击两个对象。',action:'connect',label:'添加连线'};
  return {title:'可以继续编辑，也可以导出了',detail:'点选图形后拖动；双击改字。修改会自动保存在本机。',action:'export',label:'导出图片'};
}

export function setupNovice({state,editor,api,toast,flush,canLeave,openJob,refreshJobs,follow,tab}) {
  const $=id=>document.getElementById(id),ws=$('workspace');
  let savedPanels=null,starting=false,lastRecent='';
  const closeLibrary=()=>preserveCanvasView(editor,()=>ws.classList.add('left-collapsed'));
  const actions={
    assets:()=>{tab('assets');$('asset-search').focus();},
    layers:()=>tab('layers'),
    connect:()=>{editor.setTool('connect');editor.host.focus({preventScroll:true});},
    cancel:()=>{editor.cancelGesture();editor.setTool('select');},
    select:()=>editor.setTool('select'),
    edit:()=>{editor.ensureSelectionVisible();editor.editSelectedLabel();},
    meaning:()=>$('relation-picker').click(),
    arrange:()=>{document.querySelector('.selection-more').open=true;},
    export:()=>$('toggle-export').click()
  };
  $('workflow-next').onclick=()=>actions[$('workflow-next').dataset.action]?.();
  $('empty-add-asset').onclick=actions.assets;
  $('empty-add-text').onclick=()=>$('add-text').click();
  $('return-to-document').onclick=()=>{
    $('welcome').hidden=true;
    if(savedPanels)preserveCanvasView(editor,()=>{ws.classList.toggle('left-collapsed',savedPanels.left);ws.classList.toggle('properties-hidden',savedPanels.right);});
    savedPanels=null;refresh();
  };
  $('open-start').onclick=async()=>{
    if(state.id&&!await canLeave())return;
    savedPanels={left:ws.classList.contains('left-collapsed'),right:ws.classList.contains('properties-hidden')};
    preserveCanvasView(editor,()=>ws.classList.add('left-collapsed','properties-hidden'));
    $('welcome').hidden=false;refresh();
  };
  $('welcome-example').onclick=async()=>{
    if(starting||state.active)return;
    starting=true;$('welcome-example').disabled=true;
    try{
      if(state.id&&!await canLeave())return;
      const result=await api('/api/scene/example',{template:'sb_socs_feedback',canvas_mm:[180,120]});
      await follow(result.job_id);editor.fit();
      toast('示例已打开。先点一个图形，上方就能直接改字；修改只保存在这份副本中。');
    }catch(e){toast(e.message,true);}finally{starting=false;$('welcome-example').disabled=false;}
  };
  $('workflow-help').onclick=()=>$('beginner-help').click();

  function renderRecent(){
    const jobs=state.jobs.filter(j=>!j.archived&&!['failed','error','cancelled','queued','processing','running'].includes(j.status)).slice(0,3);
    const signature=jobs.map(j=>j.id+':'+j.title).join('|');if(signature===lastRecent)return;lastRecent=signature;
    const list=$('home-recent-list');list.replaceChildren();$('home-recent').hidden=!jobs.length;
    for(const j of jobs){
      const b=document.createElement('button');b.className='home-recent-item';b.type='button';
      const img=document.createElement('img');img.src=j.svg_url||j.png_url||'/ui/rylume-mark.svg';img.alt='';img.loading='lazy';
      const text=document.createElement('span');text.textContent=j.title||'未命名图版';
      const action=document.createElement('small');action.textContent='继续编辑';b.append(img,text,action);
      b.onclick=()=>openJob(j.id);list.append(b);
    }
  }
  function refresh(){
    const home=!$('welcome').hidden,scene=editor.scene,count=editor.selectedIds.length;
    ws.classList.toggle('showing-start',home);ws.classList.toggle('empty-document',!!state.revision&&!scene?.objects.some(o=>o.visible!==false&&o.role!=='context'));
    $('return-to-document').hidden=!state.id;$('toggle-export').disabled=!state.id||home;
    const guideHidden=home||!scene?.objects.some(o=>o.visible!==false&&o.role!=='context');
    if($('workflow-guide').hidden!==guideHidden)preserveCanvasView(editor,()=>$('workflow-guide').hidden=guideHidden);
    $('empty-canvas-actions').hidden=home||!state.revision||!!scene?.objects.some(o=>o.visible!==false&&o.role!=='context');
    const hint=workflowHint({scene,selectedIds:editor.selectedIds,tool:editor.tool,connectStart:editor.connectStart,legacy:!!state.id&&!state.revision,activeLabel:editor.activeLabel});
    $('workflow-title').textContent=hint.title;$('workflow-detail').textContent=hint.detail;
    $('workflow-next').textContent=hint.label;$('workflow-next').dataset.action=hint.action;
    const canConnect=(scene?.objects.filter(o=>o.visible!==false&&!o.locked&&o.role!=='context').length||0)>=2;
    const connect=document.querySelector('[data-tool=connect]');connect.disabled=!state.revision||!canConnect;
    connect.title=canConnect?'依次点击起点与终点，或从所选对象连到另一对象':'先添加两个对象，才能连接它们';
    $('colorway').disabled=!state.revision;$('colorway').title=state.revision?'更改当前图版的配色':'先使用一个模板，或新建图版';
    renderRecent();
  }
  return {refresh,opened(){savedPanels=null;refresh();},selection(){
    if(editor.selectedIds.length&&innerWidth<1100&&!ws.classList.contains('left-collapsed'))closeLibrary();
    refresh();
  }};
}
