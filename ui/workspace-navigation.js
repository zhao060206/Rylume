import {preserveCanvasView} from './panel-layout.js';

export function recentSections(jobs, query='', now=new Date(), options={}){
 const day=d=>`${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
 const today=day(now),yesterday=day(new Date(now.getFullYear(),now.getMonth(),now.getDate()-1));
 const q=query.trim().toLocaleLowerCase();
 const mode=options.mode==='collection'?'collection':'date',order=Array.isArray(options.order)?options.order:[],rank=new Map(order.map((id,index)=>[id,index]));
 const visible=jobs.filter(j=>!j.archived&&(!q||`${j.title||''} ${j.collection||''}`.toLocaleLowerCase().includes(q)))
  .sort((a,b)=>{const ar=rank.has(a.id)?rank.get(a.id):Number.MAX_SAFE_INTEGER,br=rank.has(b.id)?rank.get(b.id):Number.MAX_SAFE_INTEGER;return ar-br||(b.created||0)-(a.created||0)}).slice(0,80);
 const groups=new Map();
 for(const job of visible){const date=day(new Date((job.created||0)*1000));const label=mode==='collection'?(job.collection||'未分类'):(date===today?'今天':date===yesterday?'昨天':'更早');if(!groups.has(label))groups.set(label,[]);groups.get(label).push(job);}
 return [...groups].map(([label,jobs])=>({label,jobs}));
}

export function normalizeRecentOrder(jobs, order=[]){
 const ids=new Set(jobs.filter(j=>!j.archived).map(j=>j.id));
 return [...new Set(order.filter(id=>ids.has(id))),...jobs.filter(j=>!j.archived&&!order.includes(j.id)).sort((a,b)=>(b.created||0)-(a.created||0)).map(j=>j.id)];
}

export function recentStatus(job){
 if(['queued','processing','running'].includes(job.status))return {kind:'running',label:'生成中'};
 if(['failed','error'].includes(job.status))return {kind:'failed',label:'未完成'};
 if(job.status==='cancelled')return {kind:'cancelled',label:'已取消'};
 if(job.illustration_result?.state==='partial')return {kind:'draft',label:'草稿'};
 return {kind:'ready',label:''};
}

/** Persistent document navigation; canvas libraries and tools live above the art. */
export function setupWorkspaceNavigation({state,editor,api,openJob,follow,tab,toast}){
 const $=id=>document.getElementById(id),root=document.documentElement,list=$('home-recent-list');
 const ORDER_KEY='rylume-recent-order-v1',GROUP_KEY='rylume-recent-grouping-v1';
 let signature='',loading=null,openEpoch=0,dragId=null,suppressClickUntil=0,order=[],grouping='date';
 try{order=JSON.parse(localStorage.getItem(ORDER_KEY)||'[]');if(!Array.isArray(order))order=[];grouping=localStorage.getItem(GROUP_KEY)==='collection'?'collection':'date';}catch{}
 const groupSelect=$('navigator-grouping');if(groupSelect){groupSelect.value=grouping;groupSelect.onchange=()=>{grouping=groupSelect.value==='collection'?'collection':'date';try{localStorage.setItem(GROUP_KEY,grouping);}catch{}signature='';render();};}
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const errorDialog=make('dialog','document-dialog recent-job-dialog'),errorHead=make('div','dialog-heading'),errorTitle=make('h2'),errorClose=make('button','icon-button','×'),errorText=make('p'),errorActions=make('div','dialog-actions');
 errorClose.setAttribute('aria-label','关闭任务详情');errorClose.onclick=()=>errorDialog.close();errorHead.append(errorTitle,errorClose);errorDialog.append(errorHead,errorText,errorActions);document.body.append(errorDialog);
 async function open(job){
  if(loading===job.id)return;
  loading=job.id;const epoch=++openEpoch;
  try{
   const latest=await api('/api/jobs/'+job.id);if(epoch!==openEpoch)return;
   if(latest.scene_revision||latest.svg_url||latest.png_url)await openJob(job.id);
   else if(['queued','processing','running'].includes(latest.status)){
    tab('generate');if(!state.active)follow(job.id);
   }else{
    errorTitle.textContent=latest.title||'任务详情';errorText.textContent=latest.error||latest.message||'这次任务未生成可打开的图版。';
    const retry=make('button','button primary','重新尝试');retry.onclick=async()=>{retry.disabled=true;try{const result=await api('/api/jobs/'+job.id+'/retry',{});errorDialog.close();tab('generate');await follow(result.job_id);}catch(e){errorText.textContent=e.message;}finally{retry.disabled=false;}};
    errorActions.replaceChildren(retry);errorDialog.showModal();
   }
  }catch(e){if(epoch===openEpoch)toast(e.message,true);}finally{if(epoch===openEpoch)loading=null;}
 }
 function render(){
  const home=!$('welcome').hidden;document.body.classList.toggle('view-home',home);
  order=normalizeRecentOrder(state.jobs,order);const sections=recentSections(state.jobs,$('navigator-search').value,new Date(),{mode:grouping,order});
  const next=JSON.stringify([grouping,order,sections.map(g=>[g.label,g.jobs.map(j=>[j.id,j.title,j.status,j.illustration_result?.state])])]);
  if(next!==signature){
   signature=next;list.replaceChildren();
   for(const section of sections){
    list.append(make('h3','recent-date',section.label));
    for(const job of section.jobs){
     const status=recentStatus(job),row=make('button','recent-document');row.type='button';row.draggable=true;row.dataset.jobId=job.id;row.title=(job.title||'未命名图版')+(status.label?' · '+status.label:'')+' · 可拖动排序，Alt+↑置顶';row.setAttribute('aria-label',(job.title||'未命名图版')+'，拖动调整顺序');
     const icon=make('span','recent-document-icon');icon.innerHTML='<svg class="icon" aria-hidden="true"><use href="#icon-journal"></use></svg>';
     row.append(icon,make('span','recent-document-title',job.title||'未命名图版'));
     if(status.label)row.append(make('span','recent-document-status '+status.kind,status.label));
     row.onclick=()=>{if(Date.now()<suppressClickUntil)return;open(job);};
     row.onkeydown=e=>{if(e.altKey&&e.key==='ArrowUp'){e.preventDefault();moveBefore(job.id,order.find(id=>id!==job.id));}};
     row.ondragstart=e=>{dragId=job.id;suppressClickUntil=Date.now()+400;row.classList.add('dragging');e.dataTransfer?.setData('text/plain',job.id);if(e.dataTransfer)e.dataTransfer.effectAllowed='move';};
     row.ondragover=e=>{if(!dragId||dragId===job.id)return;e.preventDefault();e.dataTransfer&&(e.dataTransfer.dropEffect='move');row.classList.add('drag-target');};
     row.ondragleave=()=>row.classList.remove('drag-target');
     row.ondrop=e=>{e.preventDefault();row.classList.remove('drag-target');if(dragId&&dragId!==job.id)moveBefore(dragId,job.id);};
     row.ondragend=()=>{dragId=null;row.classList.remove('dragging','drag-target');suppressClickUntil=Date.now()+300;};
     list.append(row);
    }
   }
  }
  $('navigator-empty').hidden=!!sections.length;
  $('navigator-empty').textContent=$('navigator-search').value?'没有匹配的图版。':'新建或生成的图版会保存在这里。';
  for(const row of list.querySelectorAll('[data-job-id]')){const active=!home&&row.dataset.jobId===state.id;row.classList.toggle('active',active);if(active)row.setAttribute('aria-current','page');else row.removeAttribute('aria-current');}
 }
 function persistOrder(){try{localStorage.setItem(ORDER_KEY,JSON.stringify(order));}catch{}}
 function moveBefore(id,target){order=normalizeRecentOrder(state.jobs,order).filter(value=>value!==id);const index=target?order.indexOf(target):0;order.splice(index<0?order.length:index,0,id);persistOrder();signature='';render();list.querySelector(`[data-job-id="${id}"]`)?.focus({preventScroll:true});}
 function collapse(value){
  preserveCanvasView(editor,()=>root.classList.toggle('navigation-collapsed',value));
  $('collapse-navigation').setAttribute('aria-expanded',String(!value));$('expand-navigation').setAttribute('aria-expanded',String(!value));
  try{localStorage.setItem('rylume-navigation-collapsed',String(value));}catch{}
 }
 let collapsed=false;try{collapsed=localStorage.getItem('rylume-navigation-collapsed')==='true';}catch{}
 root.classList.toggle('navigation-collapsed',collapsed);
 $('collapse-navigation').setAttribute('aria-expanded',String(!collapsed));$('expand-navigation').setAttribute('aria-expanded',String(!collapsed));
 $('collapse-navigation').onclick=()=>collapse(true);$('expand-navigation').onclick=()=>collapse(false);
 $('navigator-search').oninput=()=>{signature='';render();};
 document.querySelector('.app-sidebar .brand').onclick=e=>{e.preventDefault();$('open-start').click();};
 new MutationObserver(render).observe($('welcome'),{attributes:true,attributeFilter:['hidden']});
 render();return {render};
}
