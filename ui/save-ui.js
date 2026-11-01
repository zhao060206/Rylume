import {documentSaveState,saveBeforeDestructiveAction} from './save-state.js';

const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};

export function setupSaveControls({state,flush,toast}){
  const save=document.getElementById('save-document'),label=document.getElementById('save-status');
  async function run(){
    if(!state.id&&!state.pending.length)return toast('当前没有打开的图版，无需保存');
    const ok=await flush();refresh();
    if(ok)toast('图版已保存到本机');
    else toast(state.conflict?'图版版本有冲突，请在提示中另存副本。':state.saveError||'保存暂未完成，可点击“保存”重试。',true);
    return ok;
  }
  function refresh(){
    const info=documentSaveState(state);
    save.disabled=info.kind==='empty'||info.kind==='readonly'||info.kind==='saving';
    save.textContent=info.kind==='saving'?'保存中…':info.kind==='error'?'重试保存':'保存';
    save.dataset.saveState=info.kind;
    label.textContent=info.label;label.dataset.saveState=info.kind;
    label.title=state.revision?`图版自动保存在本机，当前修订 r${state.revision}。也可点击“保存”或按 Ctrl+S。`:info.label;
  }
  save.onclick=run;document.addEventListener('document-save-state',refresh);
  document.addEventListener('editor-inline-edit',event=>{state.inlineEditing=!!event.detail?.dirty;refresh();});
  document.getElementById('file-save-document')?.addEventListener('click',run);
  refresh();return {run,refresh};
}

/** This dialog stays open on failure: the error, retry and copy recovery are
 * never reduced to a short-lived toast behind another window. */
export function setupRestartDialog({state,flush,saveCopy,apply,documentTitle=()=>''}){
  const dialog=make('dialog','restart-dialog');dialog.id='restart-update-dialog';
  dialog.setAttribute('aria-labelledby','restart-update-title');dialog.setAttribute('aria-describedby','restart-update-description');
  const heading=make('h2','','保存并重启更新');heading.id='restart-update-title';
  const target=make('p','restart-target'),description=make('p','restart-description');description.id='restart-update-description';
  const steps=make('ol','restart-steps');
  const saveStep=make('li','','保存当前图版'),installStep=make('li','','安装已下载并校验的新版'),openStep=make('li','','重新打开软件，保留图版与设置');steps.append(saveStep,installStep,openStep);
  const error=make('p','restart-error');error.id='restart-update-error';error.setAttribute('role','alert');error.hidden=true;
  const progress=make('p','restart-progress');progress.setAttribute('role','status');progress.setAttribute('aria-live','polite');
  const actions=make('div','dialog-actions'),later=make('button','button','继续编辑'),copy=make('button','button','另存副本并重启'),confirm=make('button','button primary','保存并重启');
  for(const b of [later,copy,confirm])b.type='button';copy.hidden=true;copy.id='restart-save-copy';confirm.id='confirm-save-restart';
  actions.append(later,copy,confirm);dialog.append(heading,target,description,steps,error,progress,actions);document.body.append(dialog);
  let busy=false,attempt=0,restarting=false,applying=false;
  function close(){if(restarting||applying)return;attempt++;busy=false;dialog.close();}
  later.onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
  function fail(message){error.textContent=message;error.hidden=false;progress.textContent='当前软件继续可用，修改仍保留。';copy.hidden=!saveCopy||!state.pending.length;confirm.textContent='重试保存并重启';}
  async function run(asCopy=false){
    if(busy||restarting)return;
    const token=++attempt;busy=true;confirm.disabled=copy.disabled=true;error.hidden=true;
    try{
      if(state.active)throw Error('还有绘图任务正在运行。请等待完成或取消任务后，再点击重试。');
      progress.textContent=asCopy?'正在另存为独立图版…':'正在保存图版，请稍候…';
      const ok=asCopy?await saveCopy():await saveBeforeDestructiveAction(state,flush);
      if(token!==attempt)return;
      if(!ok)throw Error(state.conflict?'图版已有其他修订。点击“另存副本并重启”保留你的修改，原图不会被覆盖。':state.saveError||'图版尚未成功写入本机。请重试保存；也可以另存独立副本。');
      if(state.active)throw Error('有新的绘图任务开始了，请等待完成后重试。');
      saveStep.textContent='图版已安全保存';saveStep.classList.add('complete');
      progress.textContent='图版已保存，正在准备重启…';
      applying=true;later.disabled=true;
      const result=await apply();
      if(token!==attempt)return;
      if(result?.state!=='installing')throw Error('更新尚未开始，请重试。');
      restarting=true;later.disabled=true;progress.textContent='正在重启更新，请稍候。软件会自动重新打开。';confirm.textContent='正在重启…';
    }catch(e){if(token===attempt)fail(e.message);}
    finally{if(token===attempt&&!restarting){busy=false;applying=false;later.disabled=false;confirm.disabled=copy.disabled=false;}}
  }
  confirm.onclick=()=>run(false);copy.onclick=()=>run(true);
  return {open(version){
    if(dialog.open){confirm.focus();return;}
    busy=false;restarting=false;applying=false;attempt++;error.hidden=true;copy.hidden=true;progress.textContent='';saveStep.classList.remove('complete');
    target.textContent=version?`即将更新至 Rylume ${version}`:'新版已下载并通过校验';
    const info=documentSaveState(state),empty=['empty','readonly'].includes(info.kind);
    description.textContent=empty?'当前没有需要保存的图版，可以直接重启更新。':`图版「${documentTitle()||'未命名图版'}」将先保存到本机，然后重启安装新版。`;
    saveStep.textContent=empty?'无需保存，原有任务已保留':info.kind==='saved'?'当前图版已保存到本机':'自动保存当前图版的修改';
    confirm.textContent=empty?'重启更新':'保存并重启';confirm.disabled=copy.disabled=later.disabled=false;
    dialog.showModal();later.focus();
  }};
}
