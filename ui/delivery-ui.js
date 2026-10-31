import {setupFloatingWindows} from './floating-windows.js';
/** Deliberate downloads; a restart is requested only after saving the current work. */
export function byteSize(n){if(!Number.isFinite(n)||n<0)return '—';return n<1024*1024?`${Math.max(1,Math.round(n/1024))} KB`:`${(n/1024/1024).toFixed(1)} MB`;}
export function packAction(p){const s=p.task?.state;if(['queued','downloading','validating','installing'].includes(s))return 'cancel';if(!p.compatible)return 'upgrade';if(p.update_available)return 'update';if(p.installed_version)return 'use';return 'install';}
export const busyUpdate=s=>['checking','downloading','validating','installing'].includes(s);
export const showUpdateNotice=(u,dismissed)=>!!u?.latest_version&&['available','downloading','validating','ready','failed','cancelled'].includes(u.state)&&dismissed!==u.latest_version;
export function setupDelivery({api,toast,flush,state,reloadCatalog,openAssets,openTemplates}){
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  const dialog=el('dialog','delivery-dialog');dialog.id='delivery-dialog';dialog.setAttribute('aria-labelledby','delivery-title');
  const head=el('div','dialog-heading'),title=el('h2','','资源与更新');title.id='delivery-title';const close=el('button','icon-button','×');close.type='button';close.setAttribute('aria-label','关闭资源与更新');close.onclick=()=>dialog.close();head.append(title,close);
  const tabs=el('div','delivery-tabs');tabs.setAttribute('role','tablist');
  const resourceTab=el('button','','学科资源'),updateTab=el('button','','软件更新');
  for(const b of [resourceTab,updateTab])b.setAttribute('role','tab');tabs.append(resourceTab,updateTab);
  const resourcePage=el('section','delivery-page'),updatePage=el('section','delivery-page');
  for(const p of [resourcePage,updatePage])p.setAttribute('role','tabpanel');
  const intro=el('p','muted','按需要下载。素材与模板安装后立即可用，已保存的图版保留素材快照。');
  const resourceToolbar=el('div','delivery-toolbar'),resourceStatus=el('p','muted small');resourceStatus.setAttribute('role','status');
  const refresh=el('button','button','刷新目录');resourceToolbar.append(resourceStatus,refresh);
  const rows=el('div','pack-list');resourcePage.append(intro,resourceToolbar,rows);
  const versionTitle=el('h3'),versionNote=el('p','muted'),updateProgress=el('progress'),updateStatus=el('p','muted small'),notes=el('details','update-notes'),notesText=el('pre'),updateActions=el('div','dialog-actions');
  updateStatus.setAttribute('role','status');updateProgress.max=100;updateProgress.setAttribute('aria-label','软件更新进度');notes.append(el('summary','','版本说明'),notesText);
  const check=el('button','button','检查更新'),download=el('button','button primary','下载新版'),apply=el('button','button primary','保存并重启更新'),cancel=el('button','button','取消下载'),releaseLink=el('a','button','打开发布页');
  releaseLink.target='_blank';releaseLink.rel='noreferrer';updateActions.append(check,download,cancel,apply,releaseLink);
  const reminder=el('p','muted small','自动检查只查询公开版本信息。下载由你发起；文件校验通过后才能替换程序。任务与模型配置保存在本机数据目录。');
  updatePage.append(versionTitle,versionNote,updateProgress,updateStatus,updateActions,notes,reminder);
  dialog.append(head,tabs,resourcePage,updatePage);document.body.append(dialog);setupFloatingWindows(dialog);
  const notice=el('aside','update-corner');notice.hidden=true;notice.setAttribute('aria-live','polite');
  const noticeHead=el('div','update-corner-head'),noticeTitle=el('strong'),noticeClose=el('button','icon-button','×');noticeClose.type='button';noticeClose.setAttribute('aria-label','稍后提醒');noticeClose.title='稍后提醒';noticeHead.append(noticeTitle,noticeClose);
  const noticeText=el('p'),noticeActions=el('div','update-corner-actions'),noticePrimary=el('button','button primary'),noticeDetails=el('button','text-button','查看详情');noticeActions.append(noticePrimary,noticeDetails);notice.append(noticeHead,noticeText,noticeActions);document.body.append(notice);
  let dismissedVersion='';try{dismissedVersion=localStorage.getItem('rylume-dismissed-update')||'';}catch{}
  noticeClose.onclick=()=>{dismissedVersion=update?.latest_version||'';try{localStorage.setItem('rylume-dismissed-update',dismissedVersion);}catch{}notice.hidden=true;};
  noticeDetails.onclick=()=>{showView('updates');if(!dialog.open)dialog.show();loadUpdate();schedule();};
  noticePrimary.onclick=()=>{if(update?.state==='ready')apply.click();else if(update?.state==='available'||update?.state==='failed'||update?.state==='cancelled')download.click();};
  const top=el('button','text-button delivery-entry','资源与更新');top.id='open-delivery';top.title='下载学科素材与模板，检查软件更新';
  const models=document.getElementById('open-settings')||document.querySelector('header button[title]');
  const settingsMenu=document.getElementById('settings-menu-items');
  if(settingsMenu)settingsMenu.prepend(top);else if(models)models.before(top);else document.querySelector('header')?.append(top);
  const assetOpen=el('button','button full secondary','下载其他学科素材与模板');document.getElementById('panel-assets')?.append(assetOpen);
  const templateOpen=el('button','text-button full','管理学科资源包');document.getElementById('panel-templates')?.append(templateOpen);
  let view='resources',focused='',timer=null,data=null,update=null,revisionSignature='',manualCheck=false,lastState='',renderedPacks='';
  function showView(name){view=name;resourcePage.hidden=name!=='resources';updatePage.hidden=name!=='updates';resourceTab.setAttribute('aria-selected',String(name==='resources'));updateTab.setAttribute('aria-selected',String(name==='updates'));}
  resourceTab.onclick=()=>showView('resources');updateTab.onclick=()=>{showView('updates');loadUpdate();};
  function renderPacks(){
    if(!data)return;
    const key=JSON.stringify([data,focused]);if(key===renderedPacks)return;renderedPacks=key;
    const active=document.activeElement,focusPack=active?.closest?.('[data-pack]')?.dataset.pack,focusAction=active?.textContent;
    resourceStatus.textContent=data.refreshing?'正在刷新 GitHub 目录…':data.error||'官方 GitHub 资源包 · 原创可编辑矢量';refresh.disabled=data.refreshing;
    rows.replaceChildren();
    const builtin=el('article','pack-row');builtin.append(el('div','pack-number','01'));const bio=el('div','pack-copy');bio.append(el('h3','','生物学'),el('p','muted small','细胞、分子、组织与机制图 · 已随软件提供'));builtin.append(bio,el('span','pack-installed','内置'));rows.append(builtin);
    data.packs.forEach((p,i)=>{
      const row=el('article','pack-row'+(focused===p.id?' focused':''));row.dataset.pack=p.id;
      const count=el('span','pack-number',String(i+2).padStart(2,'0')),copy=el('div','pack-copy'),h=el('h3','',p.title);
      copy.append(h,el('p','muted small',p.description),el('p','pack-meta',`${p.asset_count} 个素材 · ${p.template_count} 个模板 · ${byteSize(p.size)} · v${p.version}`));
      const action=packAction(p),buttons=el('div','pack-actions');
      if(action==='cancel'){
        const status=el('p','muted small',({queued:'等待下载',downloading:'正在下载',validating:'正在核对素材与模板',installing:'正在安装'})[p.task.state]);
        const progress=el('progress');progress.max=100;progress.value=p.task.progress||0;progress.setAttribute('aria-label',p.title+'下载进度');copy.append(progress,status);
        const b=el('button','button','取消');b.onclick=()=>perform('/api/resources/cancel',{id:p.id});buttons.append(b);
      }else if(action==='use'){
        h.append(el('span','pack-installed','已安装 v'+p.installed_version));
        const use=el('button','button','素材'),templates=el('button','button','模板'),remove=el('button','text-button','卸载');
        use.onclick=()=>{dialog.close();openAssets(p.id);};templates.onclick=()=>{dialog.close();openTemplates(p.id);};
        remove.onclick=async()=>{if(!confirm(`卸载「${p.title}」资源包？已保存图版中的素材快照会保留。`))return;if(!await flush())return toast('当前图版尚未保存，已停止卸载素材包',true);await perform('/api/resources/uninstall',{id:p.id});await syncCatalog();};buttons.append(use,templates,remove);
      }else{
        const b=el('button','button'+(focused===p.id?' primary':''),action==='upgrade'?'先更新软件':action==='update'?'更新资源包':p.task?.state==='failed'?'重新下载':'下载');
        b.onclick=()=>action==='upgrade'?(showView('updates'),loadUpdate()):perform('/api/resources/install',{id:p.id});buttons.append(b);
      }
      if(p.task?.error)copy.append(el('p','delivery-error',p.task.error));
      row.append(count,copy,buttons);rows.append(row);
    });
    if(focusPack){const row=rows.querySelector(`[data-pack="${focusPack}"]`);[...(row?.querySelectorAll('button')||[])].find(b=>b.textContent===focusAction)?.focus({preventScroll:true});}
  }
  async function syncCatalog(){const fresh=await api('/api/scene/catalog');await reloadCatalog(fresh);}
  async function loadPacks(){
    try{
      data=await api('/api/resources');renderPacks();
      const signature=data.packs.map(p=>p.id+':'+(p.installed_version||'')).join('|');
      if(revisionSignature&&signature!==revisionSignature)await syncCatalog();revisionSignature=signature;
    }catch(e){resourceStatus.textContent=e.message+' · 可关闭后重试';}
  }
  async function perform(path,body){try{data=await api(path,body);renderPacks();schedule();}catch(e){toast(e.message,true);}}
  refresh.onclick=()=>perform('/api/resources/refresh',{});
  function renderUpdate(){
    if(!update)return;const s=update.state;versionTitle.textContent=`当前版本 ${update.current_version}`;
    versionNote.textContent=s==='available'?`发现新版本 ${update.latest_version}`:s==='up_to_date'?'已是最新正式版本':s==='ready'?'新版已下载并通过校验':s==='installing'?'正在重启更新…':s==='cancelled'?'已取消下载，当前软件可继续使用':s==='failed'?'本次检查或下载未完成':s==='checking'?'正在检查 GitHub 最新版本…':s==='downloading'?`正在下载 ${update.latest_version}`:s==='validating'?'正在核对并解压安装包':'从 GitHub 检查最新正式版本';
    updateStatus.textContent=update.error||[update.message,s==='downloading'?`${byteSize(update.downloaded||0)} / ${byteSize(update.total||0)}`:''].filter(Boolean).join(' · ')||update.last_update_message||'';
    updateStatus.classList.toggle('delivery-error',s==='failed');updateProgress.hidden=!['downloading','validating','ready'].includes(s);updateProgress.value=update.progress||0;
    check.disabled=busyUpdate(s)||s==='ready';download.hidden=!update.latest_version||!['available','cancelled','failed'].includes(s);download.disabled=busyUpdate(s);
    cancel.hidden=!['downloading','validating','ready'].includes(s);cancel.textContent=s==='ready'?'放弃本次安装':'取消下载';apply.hidden=s!=='ready'||!update.can_apply;
    releaseLink.hidden=!update.release_url;releaseLink.href=update.release_url||'https://github.com/zhao060206/Rylume/releases';
    notes.hidden=!update.notes;notesText.textContent=update.notes||'';
    top.textContent=['available','downloading','validating','ready'].includes(s)?'发现新版本 · '+update.latest_version:'资源与更新';top.classList.toggle('has-update',['available','ready'].includes(s));
    document.querySelector('.settings-menu')?.classList.toggle('has-update',['available','ready'].includes(s));
    const showNotice=showUpdateNotice(update,dismissedVersion);
    notice.hidden=!showNotice;
    if(showNotice){noticeTitle.textContent=s==='ready'?'更新已准备好':s==='downloading'||s==='validating'?'正在准备更新':s==='failed'?'更新未完成':`发现新版本 ${update.latest_version}`;noticeText.textContent=update.error||[update.message,s==='downloading'?`${Math.round(update.progress||0)}%`:''].filter(Boolean).join(' · ')||'可选择下载，保存后重启更新。';noticePrimary.hidden=['downloading','validating'].includes(s)||(s==='ready'&&!update.can_apply);noticePrimary.textContent=s==='ready'?'保存并重启':s==='failed'||s==='cancelled'?'重试下载':'下载新版';}
    if(lastState!==s&&manualCheck&&s==='up_to_date')toast('当前已是最新版本');lastState=s;
  }
  async function loadUpdate(){try{update=await api('/api/updates');renderUpdate();}catch(e){updateStatus.textContent=e.message;}}
  async function updateAction(path){try{update=await api(path,{});renderUpdate();schedule();}catch(e){toast(e.message,true);}}
  check.onclick=()=>{manualCheck=true;updateAction('/api/updates/check');};download.onclick=()=>updateAction('/api/updates/download');cancel.onclick=()=>updateAction('/api/updates/cancel');
  apply.onclick=async()=>{
    if(state.active)return toast('请先等待生成任务完成',true);
    apply.disabled=true;
    try{if(!await flush())return toast('图版尚未保存，已停止重启更新',true);await updateAction('/api/updates/apply');}finally{apply.disabled=false;}
  };
  function schedule(){clearTimeout(timer);timer=setTimeout(async()=>{await Promise.all([loadPacks(),loadUpdate()]);if(dialog.open||data?.packs.some(p=>packAction(p)==='cancel')||busyUpdate(update?.state))schedule();},1100);}
  async function openResources(pid=''){focused=pid;showView('resources');if(!dialog.open)dialog.show();await loadPacks();schedule();if(pid)rows.querySelector(`[data-pack="${pid}"]`)?.scrollIntoView({block:'nearest'});}
  top.onclick=()=>{openResources();};assetOpen.onclick=()=>openResources();templateOpen.onclick=()=>openResources();
  dialog.addEventListener('close',()=>{if(!data?.packs.some(p=>packAction(p)==='cancel')&&!busyUpdate(update?.state))clearTimeout(timer);});
  async function checkWhenDue(){
    if(busyUpdate(update?.state)||update?.state==='ready')return;
    let last=0;try{last=Number(localStorage.getItem('rylume-last-update-check')||0);}catch{}
    if(Date.now()-last>24*60*60*1000){try{localStorage.setItem('rylume-last-update-check',String(Date.now()));}catch{}await updateAction('/api/updates/check');}
  }
  async function ready(){
    try{await api('/api/updates/health',{});}catch{}
    await loadUpdate();await checkWhenDue();
    setInterval(()=>{if(!document.hidden)checkWhenDue();},6*60*60*1000);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)checkWhenDue();});
  }
  return {openResources,ready};
}
