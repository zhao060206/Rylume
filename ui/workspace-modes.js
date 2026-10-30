import {preserveCanvasView, syncPanelButtons} from './panel-layout.js';

export const MODE_KEY = 'rylume-workspace-mode';
export const normalizeWorkspaceMode = value => value === 'professional' ? value : 'simple';

export function defaultModeLayout(mode, width = 1280) {
  return normalizeWorkspaceMode(mode) === 'professional'
    ? {tab:'layers', inspector:'properties', leftCollapsed:width < 1100, propertiesHidden:false}
    : {tab:'assets', inspector:'properties', leftCollapsed:true, propertiesHidden:true};
}

export function responsiveModeLayout(layout, width) {
  return {...layout, leftCollapsed:width < 1100 && !layout.propertiesHidden ? true : layout.leftCollapsed};
}

/** Serialize mode requests so quick repeated clicks always settle on the last choice. */
export function modeRequestQueue(initial, apply) {
  let current=normalizeWorkspaceMode(initial), desired=current, running=null;
  function request(value) {
    desired=normalizeWorkspaceMode(value);
    if(running)return running;
    if(desired===current)return Promise.resolve(current);
    running=(async()=>{
      try { while(current!==desired){const next=desired;await apply(next,current);current=next;} }
      finally {running=null;}
      return current;
    })();
    return running;
  }
  return {request, get current(){return current;}};
}

export function setupWorkspaceModes({editor, state, tab, showRight, refresh}) {
  const $=id=>document.getElementById(id), root=document.documentElement, ws=$('workspace');
  let initial='simple';try{initial=normalizeWorkspaceMode(localStorage.getItem(MODE_KEY));}catch{}
  const layouts={simple:defaultModeLayout('simple'),professional:defaultModeLayout('professional',innerWidth)};
  let mode=initial, applying=false, transition=null, animation=null, readyDocument=null, deferredLayout=false;
  const buttons=[...document.querySelectorAll('.workspace-mode-switch [data-workspace-mode]')];
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const actionNodes=[$('duplicate'),$('delete'),document.querySelector('.selection-more')];
  const inlineActions=document.createElement('div'),inspectorActions=document.createElement('div');
  inlineActions.className='selection-actions-inline';inspectorActions.className='inspector-selection-actions';
  inspectorActions.setAttribute('role','toolbar');inspectorActions.setAttribute('aria-label','所选对象操作');
  $('quick-fields').append(inlineActions);$('properties').append(inspectorActions);
  function placeActions(){
    const target=!ws.classList.contains('properties-hidden')?inspectorActions:inlineActions;
    if(actionNodes[0].parentElement!==target)target.append(...actionNodes);
  }
  const selectedTab=()=>document.querySelector('.rail [data-tab].active')?.dataset.tab||'assets';
  function remember(){
    placeActions();
    if(deferredLayout&&!applying&&!ws.classList.contains('annotations-open')){
      deferredLayout=false;applying=true;
      try{preserveCanvasView(editor,()=>{layout();refresh();});}finally{applying=false;}
      return;
    }
    if(applying||!state.id||state.id!==readyDocument||!$('welcome').hidden||ws.classList.contains('annotations-open'))return;
    layouts[mode]={tab:selectedTab(),inspector:document.querySelector('[data-inspector][aria-selected=true]')?.dataset.inspector||'properties',leftCollapsed:ws.classList.contains('left-collapsed'),propertiesHidden:ws.classList.contains('properties-hidden')};
  }
  function controls(){
    root.dataset.workspaceMode=mode;
    for(const b of buttons)b.setAttribute('aria-pressed',String(b.dataset.workspaceMode===mode));
    const summary=document.querySelector('.workbench-more>summary');summary.textContent=mode==='simple'?'更多':'帮助';
    summary.setAttribute('aria-label',mode==='simple'?'更多绘图工具':'帮助与操作说明');
    placeActions();
    document.querySelector('.toolbar').setAttribute('aria-label',mode==='simple'?'常用绘图工具':'专业绘图工具');
  }
  function layout(){
    if(!state.id||!$('welcome').hidden||ws.classList.contains('annotations-open'))return;
    const target=responsiveModeLayout(layouts[mode],innerWidth);
    tab(target.tab);
    if(!target.propertiesHidden)showRight(target.inspector);
    ws.classList.toggle('left-collapsed',target.leftCollapsed);
    ws.classList.toggle('properties-hidden',target.propertiesHidden);
    syncPanelButtons(ws);
  }
  function commit(next){
    applying=true;
    if(ws.classList.contains('annotations-open'))deferredLayout=true;
    try {preserveCanvasView(editor,()=>{mode=next;controls();layout();refresh();});}
    finally {applying=false;}
    try{localStorage.setItem(MODE_KEY,mode);}catch{}
    $('workspace-mode-status').textContent=mode==='professional'?'已切换到专业模式：图层和属性按需展开。':'已切换到极简模式：精细设置可在更多中打开。';
    ws.dispatchEvent(new CustomEvent('workspace-mode-change',{detail:{mode}}));
  }
  async function change(next){
    remember();
    // Commit an active text field just as a normal click outside the field would.
    if(document.activeElement?.matches('.editor-inline-input,#quick-label,.property-grid input'))document.activeElement.blur();
    if(reduced.matches){commit(next);return;}
    if(typeof document.startViewTransition==='function'){
      try{
        root.dataset.modeMotion='snapshot';
        transition=document.startViewTransition(()=>commit(next));
        await transition.finished;
      }catch{if(mode!==next)commit(next);}
      finally{transition=null;delete root.dataset.modeMotion;}
    }else{
      commit(next);
      const surface=!ws.classList.contains('properties-hidden')?$('properties'):document.querySelector('.toolbar');
      animation=surface.animate?.([{opacity:.35,transform:'translateY(5px)'},{opacity:1,transform:'translateY(0)'}],{duration:320,easing:'cubic-bezier(.22,1,.36,1)'});
      try{await animation?.finished;}catch{}finally{animation=null;}
    }
  }
  const queue=modeRequestQueue(initial,change);
  for(const b of buttons)b.onclick=()=>{transition?.skipTransition();animation?.finish();queue.request(b.dataset.workspaceMode);};
  document.querySelector('.workspace-mode-switch').addEventListener('keydown',e=>{
    e.stopPropagation();
    if(e.key==='ArrowLeft'||e.key==='ArrowRight'){
      e.preventDefault();const b=buttons[e.key==='ArrowRight'?1:0];b.focus();b.click();
    }
  });
  reduced.addEventListener('change',()=>{if(reduced.matches){transition?.skipTransition();animation?.finish();}});
  document.querySelectorAll('[data-panel-command]').forEach(b=>b.onclick=()=>tab(b.dataset.panelCommand));
  // One template gallery, instead of a second sidebar containing gallery launchers.
  document.querySelector('.rail [data-tab=templates]').onclick=()=> $('open-gallery').click();
  const palette=document.createElement('div');palette.className='canvas-style-settings';
  const paletteLabel=document.querySelector('label[for=colorway]');paletteLabel.textContent='图版配色';
  palette.append(paletteLabel,$('colorway'));$('property-content').before(palette);
  // Duplicate menus remain wired for compatibility but no longer add visible choices.
  for(const id of ['open-audit','process-edit','process-check'])$(id).classList.add('consolidated-command');
  document.querySelector('[data-command=show-shortcuts]').classList.add('consolidated-command');
  document.querySelectorAll('.tool-cluster').forEach((n,i)=>n.setAttribute('aria-label',i?'绘制':'撤销与恢复'));
  $('open-start').addEventListener('click',remember);
  $('return-to-document').addEventListener('click',()=>{applying=true;try{preserveCanvasView(editor,()=>{layout();refresh();});}finally{applying=false;}});
  new MutationObserver(remember).observe(ws,{attributes:true,attributeFilter:['class']});
  ws.addEventListener('workspace-panel-request',()=>queueMicrotask(remember));
  controls();
  return {get mode(){return mode;}, opened(){readyDocument=state.id;applying=true;try{preserveCanvasView(editor,layout);refresh();}finally{applying=false;}if(editor.scene)editor.fit();}};
}
