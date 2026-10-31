import {preserveCanvasView} from './panel-layout.js';

export const LESSON_STEPS=['select','edit','asset','export'];
export function lessonBaseline(scene){return {labels:Object.fromEntries((scene?.objects||[]).map(o=>[o.id,o.label||''])),ids:(scene?.objects||[]).map(o=>o.id)};}
export function lessonEvidence(scene,baseline,selectedIds=[]){
 const objects=(scene?.objects||[]).filter(o=>o.visible!==false&&!o.locked),ids=new Set(baseline.ids);
 return {select:objects.some(o=>selectedIds.includes(o.id)),
  edit:objects.some(o=>ids.has(o.id)&&o.label?.trim()&&o.label!==baseline.labels[o.id]),
  asset:objects.some(o=>!ids.has(o.id))};
}
export function practiceScene(){
 return {schema_version:2,title:'我的第一张练习图',source_text:'操作练习：准备样本 → 进行测量 → 分析结果。此图用于学习编辑，不代表特定实验方案。',layout:'process',
  canvas:{width_mm:180,height_mm:110},style:{colorway:'lagoon',font_size_pt:10,min_font_size_pt:7},
  objects:['准备样本','进行测量','分析结果'].map((label,i)=>({id:'practice_'+i,type:'process',label,x:16+i*54,y:34,w:40,h:25,fill:['#e4eeeb','#e5edf2','#f3ecdf'][i],stroke:'#55746c',font_size_pt:10})),
  relations:[0,1].map(i=>({id:'practice_link_'+i,source:'practice_'+i,target:'practice_'+(i+1),type:'sequence'})),
  provenance:{method:'onboarding-practice'}};
}

/** One offline practice document. The coach occupies its own row, never a modal mask. */
export function setupOnboarding({state,editor,api,flush,canLeave,openJob,refreshJobs,tab,toast}){
 const $=id=>document.getElementById(id),ws=$('workspace');
 let record={version:1,status:'unseen',step:'welcome',practice_job_id:null},active=false,busy=false,baseline=lessonBaseline(null),exported=false,persistQueue=Promise.resolve(),saveNotice=false,previousFocus=null,sessionEpoch=0;
 const welcome=document.createElement('dialog');welcome.id='onboarding-welcome';welcome.className='onboarding-welcome';welcome.setAttribute('aria-labelledby','onboarding-title');welcome.setAttribute('aria-describedby','onboarding-intro');
 welcome.innerHTML=`<button type="button" class="icon-button onboarding-close" id="onboarding-dismiss" aria-label="关闭新手引导">×</button>
 <div class="onboarding-welcome-copy"><div class="onboarding-wordmark"><img src="/ui/rylume-mark.svg" alt=""/>理象 <span>Rylume</span></div>
 <p class="onboarding-eyebrow">很高兴和你一起开始</p><h1 id="onboarding-title">让第一张图，<br>从容开始。</h1>
 <p id="onboarding-intro">用一份练习图，试试改字、加素材和导出。<br>大约 2 分钟，不需要配置 AI。</p>
 <div class="onboarding-welcome-actions"><button type="button" class="button primary" id="onboarding-start">用示例试一试 <span aria-hidden="true">→</span></button><button type="button" class="text-button" id="onboarding-explore">先自己探索</button></div>
 <p class="onboarding-return-note">随时可以跳过。之后可在「设置 → 新手引导」重新打开。</p><p id="onboarding-welcome-status" role="status"></p></div>
 <div class="onboarding-preview" aria-label="对象、文字和连线都可以单独编辑的示意图" role="img">
 <span class="onboarding-preview-heading">一点点，画出你的想法</span><svg viewBox="0 0 360 260" aria-hidden="true"><defs><marker id="lesson-arrow" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M1 1 6 3.5 1 6" fill="none" stroke="#71887e" stroke-width="1.2"/></marker></defs><path d="M117 87H229V146" fill="none" stroke="#71887e" stroke-width="1.5" marker-end="url(#lesson-arrow)"/><rect x="32" y="52" width="86" height="70" rx="9" fill="#e1ece6" stroke="#77958a"/><circle cx="75" cy="82" r="13" fill="#aacabe"/><text x="75" y="108" text-anchor="middle" font-size="12" fill="#3d5b4e">准备样本</text><rect x="187" y="149" width="86" height="70" rx="9" fill="#e7edf3" stroke="#8a9da9"/><path d="M215 177h31m-24-9v19m17-19v19" stroke="#869ea9" stroke-width="3"/><text x="230" y="205" text-anchor="middle" font-size="12" fill="#445e6c">进行测量</text><rect x="24" y="44" width="102" height="86" rx="3" fill="none" stroke="#64867a" stroke-dasharray="3 4"/><path d="m119 113 18 8-8 3-3 9z" fill="#416457" stroke="white" stroke-width="2"/><text x="177" y="68" font-size="11" fill="#8b998f">连线跟随对象</text><path d="M55 160v32h78" fill="none" stroke="#bdc9c0"/><text x="48" y="214" font-size="11" fill="#8b998f">文字随时改</text></svg>
 <div class="onboarding-preview-note"><span>01 选中</span><span>02 改字</span><span>03 添加</span><span>04 导出</span></div></div>`;
 document.body.append(welcome);
 const coach=document.createElement('section');coach.id='onboarding-coach';coach.className='onboarding-coach';coach.hidden=true;coach.setAttribute('aria-label','新手练习');
 coach.innerHTML=`<div class="onboarding-coach-heading"><span>新手练习</span><ol aria-label="练习进度"></ol><button type="button" class="text-button" id="onboarding-pause">稍后继续</button><button type="button" class="text-button" id="onboarding-exit" title="保留练习图，不再自动提示">结束引导</button></div><div class="onboarding-coach-body"><div><h2 id="onboarding-step-title"></h2><p id="onboarding-step-copy"></p><p id="onboarding-step-status" role="status" aria-live="polite"></p></div><div class="onboarding-coach-actions"><button type="button" class="text-button" id="onboarding-back">上一步</button><button type="button" class="button" id="onboarding-action"></button><button type="button" class="button primary" id="onboarding-next">下一步</button><button type="button" class="text-button" id="onboarding-skip-step" hidden>稍后再导出</button></div></div>`;
 document.querySelector('.canvas-footer').before(coach);
 const finish=document.createElement('dialog');finish.id='onboarding-finish';finish.className='onboarding-finish';finish.setAttribute('aria-labelledby','onboarding-finish-title');
 finish.innerHTML=`<div class="onboarding-finish-mark" aria-hidden="true">✓</div><p class="onboarding-eyebrow">已经迈出第一步</p><h2 id="onboarding-finish-title">现在，画你的想法。</h2><p>练习图和修改都已保留在左侧。<br>接下来可以用模板、自己绘制，或让 AI 帮你起稿。</p><div class="onboarding-finish-actions"><button type="button" class="button primary" id="onboarding-own">画我自己的图</button><button type="button" class="button" id="onboarding-ai">设置 AI 服务</button><button type="button" class="text-button" id="onboarding-keep">继续编辑练习图</button></div><small>AI 功能需要你自己的服务配置。模板和手动编辑可以离线使用。</small>`;
 document.body.append(finish);
 const replay=document.createElement('button');replay.type='button';replay.id='open-onboarding';replay.textContent='新手引导';$('settings-menu-items').prepend(replay);
 // A quiet home entry also makes the lesson discoverable after dismissing it.
 const homeHelp=document.createElement('button');homeHelp.type='button';homeHelp.className='text-button';homeHelp.id='home-onboarding';homeHelp.textContent='新手引导';document.querySelector('.home-ai-note').append(homeHelp);

 const steps={
  select:{title:'先点选一个图形',copy:'点一下画布里的任意步骤框。出现选框后，就可以拖动它；连线会跟着移动。',action:'找到整张图'},
  edit:{title:'让文字变成你的说法',copy:'在上方「修改文字」里改一个名称，例如把「准备样本」改为「采集样本」。按 Enter 或点击别处保存。',action:'去修改文字'},
  asset:{title:'再添一个素材',copy:'点击顶部「添加素材」，搜索或选择一个素材。点一下就会加入练习图，再拖到合适的位置。',action:'打开素材库'},
  export:{title:'把图保存成文件',copy:'点击右上角「导出图片」。PNG 适合直接使用，PPTX 可以继续改字。文件保存成功后，这一步才会完成。',action:'打开导出'}
 };
 function persist(patch){
  record={...record,...patch};const value={status:record.status,step:record.step,practice_job_id:record.practice_job_id};
  persistQueue=persistQueue.catch(()=>{}).then(()=>api('/api/onboarding',value)).catch(()=>{if(!saveNotice){saveNotice=true;toast('引导进度暂未保存，当前练习仍可继续；稍后可从设置重新打开。',true);}});
  return persistQueue;
 }
 function reflow(change){if(editor.host.clientWidth)preserveCanvasView(editor,change);else change();}
 function clearHighlights(){document.querySelectorAll('.onboarding-focus').forEach(e=>e.classList.remove('onboarding-focus'));}
 function context(){return active&&state.id===record.practice_job_id&&$('welcome').hidden;}
 function update(){
  clearHighlights();if(!active)return;
  const valid=context(),step=steps[record.step],index=LESSON_STEPS.indexOf(record.step);if(!step)return;
  const hidden=!$('welcome').hidden;if(coach.hidden!==hidden)reflow(()=>coach.hidden=hidden);
  $('onboarding-step-title').textContent=valid?step.title:'先回到练习图';$('onboarding-step-copy').textContent=valid?step.copy:'你正在查看其他图版。练习不会改动这张图，返回练习后可以继续。';
  $('onboarding-action').textContent=valid?step.action:'返回练习图';$('onboarding-action').disabled=busy;
  const evidence=lessonEvidence(editor.scene,baseline,editor.selectedIds),done=valid&&(record.step==='export'?exported:evidence[record.step]);
  $('onboarding-next').disabled=!done||busy;$('onboarding-next').textContent=record.step==='export'?'完成练习':'下一步';$('onboarding-back').disabled=index===0||busy;$('onboarding-skip-step').hidden=record.step!=='export'||!valid;
  $('onboarding-step-status').textContent=busy?'正在保存，请稍候…':!valid?'练习图已保留。':done?(record.step==='export'?'文件已经保存。':'做到了，可以继续下一步。'):'不着急，跟着上面的提示试一次。';
  const progress=coach.querySelector('ol');progress.replaceChildren();['选中','改字','添加','导出'].forEach((name,i)=>{const li=document.createElement('li');li.textContent=name;li.className=i<index?'done':i===index?'current':'';if(i===index)li.setAttribute('aria-current','step');progress.append(li);});
  if(valid){const targets=record.step==='select'?['#canvas-host [data-object-id="practice_0"]']:record.step==='edit'?['#quick-label']:record.step==='asset'?['.toolbar [data-tab="assets"]']:['#toggle-export'];for(const selector of targets)document.querySelector(selector)?.classList.add('onboarding-focus');}
 }
 function hideCoach(){active=false;clearHighlights();reflow(()=>coach.hidden=true);}
 function restoreFocus(){if(previousFocus?.isConnected&&!previousFocus.closest?.('[hidden]'))previousFocus.focus({preventScroll:true});else if($('welcome').hidden)editor.host.focus({preventScroll:true});else $('home-onboarding').focus();}
 async function dismiss(){sessionEpoch++;welcome.close();hideCoach();await persist({status:'skipped'});restoreFocus();}
 async function pause(){sessionEpoch++;hideCoach();await persist({status:'in_progress'});toast('练习和进度已保留，在「设置 → 新手引导」可继续。');}
 function openWelcome(){
  if(busy||state.active)return toast('先完成或取消当前生成，再开始新手练习。');
  if(document.querySelector('dialog[open]'))return toast('先关闭当前窗口，再打开新手引导。');
  sessionEpoch++;previousFocus=document.activeElement;hideCoach();const resume=record.status==='in_progress'&&record.practice_job_id;
  $('onboarding-start').textContent=resume?'继续上次的练习 →':'用示例试一试 →';$('onboarding-title').replaceChildren();$('onboarding-title').textContent=resume?'接着上次，慢慢来。':'让第一张图，从容开始。';
  $('onboarding-welcome-status').textContent='';welcome.showModal();$('onboarding-start').focus();
 }
 async function start(){
  if(busy||state.active)return;const epoch=++sessionEpoch;busy=true;$('onboarding-start').disabled=true;$('onboarding-welcome-status').textContent='正在准备你的练习图…';
  try{
   if(!await canLeave())throw Error('当前图版还有未保存的修改，请先处理保存提示。');if(epoch!==sessionEpoch)return;
   let jobId=record.status==='in_progress'?record.practice_job_id:null,step=record.step;
   if(jobId){try{await api('/api/jobs/'+jobId+'/scene');}catch(e){if(e.status!==404)throw e;jobId=null;}}if(epoch!==sessionEpoch)return;
   if(!jobId){const result=await api('/api/scene/import',{scene:practiceScene()});jobId=result.job_id;step='select';await refreshJobs();}
   if(epoch!==sessionEpoch)return;if(!LESSON_STEPS.includes(step))step='select';
   await persist({status:'in_progress',practice_job_id:jobId,step});
   if(epoch!==sessionEpoch)return;const opened=await openJob(jobId,{isCurrent:()=>epoch===sessionEpoch});if(epoch!==sessionEpoch)return;if(!opened)throw Error('练习图还没打开，请重试。');
   baseline=lessonBaseline(editor.scene);exported=false;welcome.close();active=true;
   reflow(()=>{ws.classList.add('left-collapsed','properties-hidden');coach.hidden=false;});editor.fit();update();
   $('onboarding-action').focus({preventScroll:true});
  }catch(e){if(epoch===sessionEpoch){$('onboarding-welcome-status').textContent=e.message;toast(e.message,true);}}finally{busy=false;$('onboarding-start').disabled=false;update();}
 }
 async function next(){
  if(!context()||busy)return;const evidence=lessonEvidence(editor.scene,baseline,editor.selectedIds);if(!(record.step==='export'?exported:evidence[record.step]))return;
  const epoch=sessionEpoch;let advanced=false;busy=true;update();try{
   if(!await flush())throw Error('修改还未保存，请先重试保存，再继续练习。');
   if(epoch!==sessionEpoch)return;const index=LESSON_STEPS.indexOf(record.step);if(index===LESSON_STEPS.length-1){await complete(epoch);return;}
   await persist({step:LESSON_STEPS[index+1]});advanced=epoch===sessionEpoch;
  }catch(e){if(epoch===sessionEpoch)toast(e.message,true);}finally{busy=false;update();if(advanced)$('onboarding-action').focus({preventScroll:true});}
 }
 async function complete(epoch=sessionEpoch){
  if(!await flush())throw Error('练习图还未保存，请先重试保存。');
  if(epoch!==sessionEpoch)return;await persist({status:'completed',step:'finish'});if(epoch!==sessionEpoch)return;hideCoach();finish.showModal();
 }
 async function action(){
  if(busy)return;
  if(!context()){const epoch=sessionEpoch;try{if(await canLeave()&&epoch===sessionEpoch&&await openJob(record.practice_job_id,{isCurrent:()=>epoch===sessionEpoch})){editor.fit();update();}}catch(e){if(epoch===sessionEpoch)toast(e.message,true);}return;}
  if(record.step==='select'){editor.fit();editor.host.focus({preventScroll:true});}
  if(record.step==='edit'){
   if(!editor.selectedIds.length)editor.setSelection([editor.scene.objects.find(o=>!o.locked&&o.visible!==false)?.id].filter(Boolean));
   const input=$('quick-label');input.focus();input.select();
  }
  if(record.step==='asset')tab('assets');if(record.step==='export')$('toggle-export').click();
 }
 $('onboarding-start').onclick=start;$('onboarding-dismiss').onclick=$('onboarding-explore').onclick=dismiss;
 welcome.addEventListener('cancel',e=>{e.preventDefault();dismiss();});
 $('onboarding-pause').onclick=pause;$('onboarding-next').onclick=next;$('onboarding-action').onclick=action;
 $('onboarding-exit').onclick=dismiss;
 $('onboarding-back').onclick=async()=>{if(busy)return;const i=LESSON_STEPS.indexOf(record.step);if(i>0){await persist({step:LESSON_STEPS[i-1]});update();}};
 $('onboarding-skip-step').onclick=async()=>{if(busy)return;busy=true;try{await complete();}catch(e){toast(e.message,true);}finally{busy=false;update();}};
 $('onboarding-keep').onclick=()=>{finish.close();editor.host.focus({preventScroll:true});};
 $('onboarding-own').onclick=async()=>{finish.close();await $('open-start').onclick();$('brief-input').focus({preventScroll:true});};
 $('onboarding-ai').onclick=()=>{finish.close();$('open-settings').click();};
 replay.onclick=homeHelp.onclick=()=>openWelcome();
 new MutationObserver(update).observe($('welcome'),{attributes:true,attributeFilter:['hidden']});
 return {refresh:update,exported(jobId){if(active&&record.practice_job_id===jobId){exported=true;update();}},async ready(){try{const saved=(await api('/api/onboarding')).state;if(saved?.version===1)record=saved;if(['unseen','in_progress'].includes(record.status)&&!state.id&&$('welcome').hidden===false)openWelcome();}catch{ /* An unavailable guide must never block the workspace. */ }}};
}
