import {preserveCanvasView} from './panel-layout.js';

export const DOCUMENT_API='/api/document-assistant';
export const documentReady=d=>d.status==='ready'&&!d.archived;
export const activeDocumentTask=value=>['queued','converting','running'].includes(value?.status);
export const documentLength=n=>n<1000?n+' 字':(n/1000).toFixed(1)+' 千字';
export function selectedDocumentIds(documents,selected){return documents.filter(d=>selected.has(d.id)&&!d.archived).map(d=>d.id);}
export function canAnalyzeDocuments(documents,selected){const chosen=documents.filter(d=>selected.has(d.id)&&!d.archived);return chosen.length>0&&chosen.length<=8&&chosen.every(documentReady);}
export function canReuseFigure(suggestion){return !!suggestion?.prompt&&suggestion.kind!=='data_chart'&&suggestion.evidence?.length>0;}

export function setupDocumentAssistant({state,editor,api,toast,composer}){
 const $=id=>document.getElementById(id),make=(tag,cls,text)=>{const e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;};
 const pane=make('aside','document-assistant');pane.id='document-assistant';pane.hidden=true;pane.setAttribute('aria-label','文档助手');
 pane.innerHTML=`<header class="document-assistant-heading"><div><h2>文档助手</h2><span>从资料里，找到值得画的图</span></div><button type="button" class="icon-button" id="close-documents" aria-label="关闭文档助手">×</button></header>
 <div class="document-assistant-body"><section class="document-source-section"><button type="button" class="document-dropzone" id="document-upload"><svg class="icon"><use href="#plus"></use></svg><strong>添加文档</strong><span>PDF · PPT / PPTX · DOC / DOCX 等</span><small>也可以拖到这里 · 每份最多 16 MB</small></button><input type="file" id="document-files" hidden multiple accept=".pdf,.pptx,.ppt,.docx,.doc,.txt,.md,.markdown,.html,.htm,.csv,.xlsx,.json,.xml,.rtf,.odt,.odp"/><p class="document-local-note">先在本机转换为 Markdown，原文件保留。</p><p id="document-upload-status" role="status" class="document-message"></p>
 <div class="document-section-heading"><h3>我的文档</h3><label><input type="checkbox" id="document-show-archived"/>已移出</label></div><div id="document-list"></div><p id="document-empty" class="document-empty">添加一篇论文、实验方案或汇报，开始规划。</p></section>
 <section class="document-analysis-section"><label for="document-focus">希望重点画什么？<span>可选</span></label><textarea id="document-focus" maxlength="1500" rows="2" placeholder="例如：重点看作用机制和实验流程，适合放进论文。"></textarea><button type="button" id="document-analyze" class="button primary" disabled>分析绘图建议</button><p class="document-send-note">点击分析后，将所选 Markdown 发送给你配置的文本模型。</p><div class="document-model-line"><span id="document-model"></span><button type="button" class="text-button" id="document-model-settings">模型设置</button></div></section>
 <section class="document-results-section"><div class="document-section-heading"><h3>绘图建议</h3><select id="document-analysis-history" aria-label="查看建议历史" hidden></select></div><div id="document-analysis-progress" hidden><p id="document-analysis-status" role="status"></p><progress id="document-analysis-bar" max="100"></progress><button type="button" class="text-button" id="document-analysis-cancel">取消分析</button></div><p class="document-message" id="document-analysis-error" role="status"></p><div id="document-results"><p class="document-empty">建议会注明原文依据，并提供可编辑的绘图提示词。</p></div></section>
 <details class="document-method"><summary>转换器与提示词依据</summary><p id="document-converter-note"></p><div id="document-method-sources"></div><p>提示词借鉴公开项目的结构规划与忠实性核验方法，由理象重新编写。原文定位不等同于科学内容已经人工核准。</p></details></div>`;
 document.body.append(pane);
 const preview=make('dialog','document-markdown-dialog');preview.setAttribute('aria-labelledby','document-preview-title');preview.innerHTML=`<div class="dialog-heading"><h2 id="document-preview-title">Markdown</h2><button type="button" class="icon-button" id="document-preview-close" aria-label="关闭 Markdown 预览">×</button></div><p id="document-preview-meta"></p><textarea id="document-markdown" readonly aria-label="转换后的 Markdown"></textarea><div class="dialog-actions"><a class="button" id="document-markdown-download">下载 Markdown</a><button type="button" class="button" id="document-markdown-copy">复制文本</button></div>`;document.body.append(preview);
 const promptDialog=make('dialog','document-prompt-dialog');promptDialog.setAttribute('aria-labelledby','document-prompt-title');promptDialog.innerHTML=`<div class="dialog-heading"><h2 id="document-prompt-title">绘图提示词</h2><button type="button" class="icon-button" id="document-prompt-close" aria-label="关闭文档提示词">×</button></div><p>可以先改写，再放入 AI 绘图描述。此操作不会立即生成图片。</p><textarea id="document-figure-prompt" maxlength="8000" aria-label="文档建议绘图提示词"></textarea><div class="dialog-actions"><button type="button" class="button" id="document-prompt-copy">复制提示词</button><button type="button" class="button primary" id="document-prompt-use">用于 AI 绘图</button></div>`;document.body.append(promptDialog);
 let opened=false,data=null,selected=new Set(),selectionInitialized=false,listSignature='',historySignature='',timer=null,loading=false,uploading=false,submitting=false,currentAnalysis=null,resultSignature='',requestEpoch=0,chosenPrompt=null;
 const button=(label,run,cls='text-button')=>{const b=make('button',cls,label);b.type='button';b.onclick=run;return b;};
 const message=(text,error=false)=>{$('document-upload-status').textContent=text;$('document-upload-status').classList.toggle('error',error);};
 function setOpen(value,focusToggle=true){
  preserveCanvasView(editor,()=>{opened=value;pane.hidden=!value;document.body.classList.toggle('documents-open',value);if(value)$('workspace').classList.add('properties-hidden');});
  $('toggle-documents').setAttribute('aria-expanded',String(value));
  if(value){refresh();$('document-upload').focus({preventScroll:true});}else{requestEpoch++;clearTimeout(timer);if(focusToggle)$('toggle-documents').focus({preventScroll:true});}
 }
 function controls(){
  $('document-analyze').disabled=uploading||submitting||!canAnalyzeDocuments(data?.documents||[],selected);
  const count=selectedDocumentIds(data?.documents||[],selected).length;
  $('document-analyze').textContent=count?'分析 '+count+' 份文档的绘图建议':'分析绘图建议';
 }
 async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制');}catch{toast('复制未完成，可以在预览中选中文字复制。',true);}}
 function renderDocuments(){
  const docs=(data?.documents||[]).filter(d=>!!d.archived===$('document-show-archived').checked),signature=JSON.stringify(docs.map(d=>[d.id,d.status,d.message,d.revision,d.archived]));
  if(signature===listSignature){controls();return;}listSignature=signature;$('document-list').replaceChildren();$('document-empty').hidden=!!docs.length;
  for(const doc of docs){
   const row=make('article','document-source-row'),head=make('label','document-source-name'),checkbox=make('input');checkbox.type='checkbox';checkbox.checked=selected.has(doc.id);checkbox.disabled=!!doc.archived;checkbox.setAttribute('aria-label','选择文档 '+doc.name);checkbox.onchange=()=>{checkbox.checked?selected.add(doc.id):selected.delete(doc.id);controls();};
   const name=make('span','',doc.name);name.title=doc.name;head.append(checkbox,name);row.append(head);
   const detail=make('p','document-source-state '+doc.status,doc.status==='ready'?(doc.pages+' 页 / 节 · '+documentLength(doc.characters)+' · Markdown 已就绪'):doc.message);row.append(detail);
   if(doc.warnings?.length)row.append(make('p','document-source-warning',doc.warnings.slice(0,2).join('；')+(doc.warnings.length>2?'；还有 '+(doc.warnings.length-2)+' 项，请在预览核对。':'')));
   const actions=make('div','document-source-actions');
   if(doc.revision)actions.append(button('查看 Markdown',()=>showMarkdown(doc.id)));
   if(activeDocumentTask(doc))actions.append(button('取消',()=>documentAction(doc.id,'cancel',{})));
   else if(!doc.archived){if(['failed','cancelled'].includes(doc.status))actions.append(button('重试转换',()=>documentAction(doc.id,'retry',{})));if(doc.extension==='.pdf'&&(doc.scanned_pages?.length||doc.status==='failed'))actions.append(button('本机 OCR 重试',()=>documentAction(doc.id,'retry',{ocr:true})));}
   actions.append(button(doc.archived?'移回列表':'移出',()=>documentAction(doc.id,'archive',{archived:!doc.archived})));row.append(actions);$('document-list').append(row);
  }controls();
 }
 async function documentAction(identity,action,body){try{await api(DOCUMENT_API+'/documents/'+identity+'/'+action,body);if(action==='archive')selected.delete(identity);listSignature='';await refresh();}catch(e){message(e.message,true);}}
 async function showMarkdown(identity){
  const epoch=++requestEpoch;
  try{const content=await api(DOCUMENT_API+'/documents/'+identity);if(epoch!==requestEpoch||!opened)return;$('document-preview-title').textContent=content.document.name;$('document-preview-meta').textContent=content.converter+' · '+content.document.characters+' 字'+(content.warnings.length?' · '+content.warnings.join('；'):'');$('document-markdown').value=content.markdown;$('document-markdown-download').href=DOCUMENT_API+'/documents/'+identity+'/markdown';preview.showModal();}catch(e){toast(e.message,true);}
 }
 function renderResult(value){
  const result=value.result,record=value.analysis,running=activeDocumentTask(record);$('document-analysis-progress').hidden=!running;$('document-analysis-status').textContent=record.message;$('document-analysis-bar').value=record.progress||0;$('document-analysis-error').textContent=['failed','cancelled'].includes(record.status)?record.message:'';
  if(!result)return;const signature=record.id+':'+record.status;if(signature===resultSignature)return;resultSignature=signature;
  const host=$('document-results');host.replaceChildren();const coverage=result.coverage;host.append(make('p','document-coverage',`已阅读 ${coverage.documents} 份文档 · ${coverage.sections} 节 · ${documentLength(coverage.characters)}`));
  if(result.summary){const details=make('details','document-summary'),summary=make('summary','','文档概要');details.append(summary,make('p','',result.summary));host.append(details);}
  if(result.warnings?.length){const warning=make('details','document-result-warnings'),summary=make('summary','',result.warnings.length+' 项需要核对');warning.append(summary);for(const text of result.warnings)warning.append(make('p','',text));host.append(warning);}
  if(!result.suggestions.length)host.append(make('p','document-empty','本次没有得到可定位原文依据的建议。可以补充分析重点，或查看 Markdown 是否完整。'));
  for(const suggestion of result.suggestions){
   const card=make('article','document-figure-card'),tag=make('span','document-figure-kind',suggestion.kind_label),title=make('h4','',suggestion.title);card.append(tag,title,make('p','document-figure-reason',suggestion.reason));
   const structure=make('details'),structureHead=make('summary','','结构与排版');structure.append(structureHead,make('p','','对象：'+suggestion.elements.join('、')),make('p','',suggestion.visual_plan));card.append(structure);
   const evidence=make('details','document-evidence');evidence.append(make('summary','','原文依据 · '+suggestion.evidence.length+' 处'));for(const e of suggestion.evidence){evidence.append(make('strong','',e.document_name+' · '+e.locator),make('blockquote','',e.quote));}card.append(evidence);
   if(suggestion.needs_confirmation?.length)card.append(make('p','document-confirmation','待确认：'+suggestion.needs_confirmation.join('；')));
   const actions=make('div','document-figure-actions'),use=button('用于 AI 绘图',()=>usePrompt(suggestion.prompt),'button primary');use.disabled=!canReuseFigure(suggestion);if(suggestion.kind==='data_chart')use.title='数据图需要先提供原始数据；可复制建议供后续使用。';
   actions.append(use,button('编辑提示词',()=>{chosenPrompt=suggestion;$('document-figure-prompt').value=suggestion.prompt;$('document-prompt-use').disabled=!canReuseFigure(suggestion);promptDialog.showModal();}),button('复制',()=>copy(suggestion.prompt)));card.append(actions);host.append(card);
  }
 }
 async function loadResult(){
  if(!currentAnalysis)return;const identity=currentAnalysis;
  try{const value=await api(DOCUMENT_API+'/analyses/'+identity);if(identity!==currentAnalysis)return;renderResult(value);}catch(e){$('document-analysis-error').textContent=e.message;}
 }
 async function refresh(){
  if(loading)return;loading=true;
  try{
   data=await api(DOCUMENT_API);const visible=data.documents.filter(d=>!d.archived);if(!selectionInitialized){selectionInitialized=true;visible.filter(documentReady).slice(0,8).forEach(d=>selected.add(d.id));}renderDocuments();
   $('document-model').textContent=data.text_model.configured?'文本模型：'+data.text_model.model:'尚未配置文本模型';
   $('document-converter-note').textContent=data.capabilities.converter+'（MIT）。'+(data.capabilities.legacy_office_available?'本机 LibreOffice 已就绪，可转换旧版 Office。':'旧版 PPT、DOC、RTF 需要本机 LibreOffice，或先另存为 PPTX / DOCX。');
   if(!$('document-method-sources').children.length)for(const source of data.capabilities.prompt_sources){const link=make('a','',source.name+' · '+source.license);link.href=source.url;link.target='_blank';link.rel='noopener noreferrer';$('document-method-sources').append(link);}
   const history=data.analyses,signature=JSON.stringify(history.map(a=>[a.id,a.status]));if(signature!==historySignature){historySignature=signature;const select=$('document-analysis-history');select.replaceChildren();for(const entry of history){const opt=make('option','',new Date(entry.created*1000).toLocaleString()+' · '+entry.document_ids.length+' 份 · '+({completed:'已完成',failed:'失败',cancelled:'已取消',queued:'排队中',running:'分析中'}[entry.status]||entry.status));opt.value=entry.id;select.append(opt);}if(!currentAnalysis&&history[0])currentAnalysis=history[0].id;select.value=currentAnalysis||'';select.hidden=history.length<2;}
   await loadResult();
  }catch(e){message('连接文档助手失败：'+e.message,true);}finally{loading=false;clearTimeout(timer);if(opened)timer=setTimeout(refresh,(data?.documents.some(activeDocumentTask)||data?.analyses.some(activeDocumentTask))?1000:6000);}
 }
 async function upload(files){
  if(uploading||!files.length)return;uploading=true;controls();
  try{for(let index=0;index<files.length;index++){
   const file=files[index];if(file.size>16*1024*1024){message(file.name+' 超过 16 MB，未上传。',true);continue;}
   message('正在保存 '+(index+1)+' / '+files.length+'：'+file.name);
   try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',',2)[1]);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});const response=await api(DOCUMENT_API+'/upload',{name:file.name,data:content});selected.add(response.document.id);message(response.duplicate?'此文件已在库中，已选中。':'文件已保留，正在本机转换。');}catch(e){message(file.name+'：'+e.message,true);}
  }}finally{uploading=false;$('document-files').value='';await refresh();controls();}
 }
 function usePrompt(text){
  const wasDialog=promptDialog.open;
  if(wasDialog)promptDialog.close();
  if(composer.usePrompt(text)===true){if(innerWidth<1450)setOpen(false,false);composer.open();}
  else if(wasDialog)promptDialog.showModal();
 }
 $('toggle-documents').onclick=()=>setOpen(!opened);$('composer-documents').onclick=()=>{if($('creation-dialog').open)$('creation-dialog').close();setOpen(true);};$('close-documents').onclick=()=>setOpen(false);
 $('document-upload').onclick=()=>$('document-files').click();$('document-files').onchange=e=>upload([...e.target.files]);
 $('document-upload').addEventListener('dragover',e=>{e.preventDefault();$('document-upload').classList.add('drag-over');});$('document-upload').addEventListener('dragleave',()=>$('document-upload').classList.remove('drag-over'));$('document-upload').addEventListener('drop',e=>{e.preventDefault();$('document-upload').classList.remove('drag-over');upload([...e.dataTransfer.files]);});
 $('document-show-archived').onchange=()=>{listSignature='';renderDocuments();};$('document-model-settings').onclick=()=>$('open-settings').click();
 $('document-analyze').onclick=async()=>{const ids=selectedDocumentIds(data?.documents||[],selected);if(submitting||!canAnalyzeDocuments(data?.documents||[],selected))return;submitting=true;controls();try{const value=await api(DOCUMENT_API+'/analyze',{document_ids:ids,focus:$('document-focus').value});currentAnalysis=value.analysis.id;resultSignature='';$('document-results').replaceChildren(make('p','document-empty','正在依据文档规划图的类型、结构和提示词。历史结果保留在上方选择器中。'));await refresh();}catch(e){$('document-analysis-error').textContent=e.message;toast(e.message,true);}finally{submitting=false;controls();}};
 $('document-analysis-history').onchange=async e=>{currentAnalysis=e.target.value;resultSignature='';$('document-results').replaceChildren();await loadResult();};$('document-analysis-cancel').onclick=async()=>{try{if(currentAnalysis){await api(DOCUMENT_API+'/analyses/'+currentAnalysis+'/cancel',{});await refresh();}}catch(e){$('document-analysis-error').textContent=e.message;toast(e.message,true);}};
 $('document-preview-close').onclick=()=>{requestEpoch++;preview.close();};preview.addEventListener('cancel',()=>requestEpoch++);$('document-markdown-copy').onclick=()=>copy($('document-markdown').value);
 $('document-prompt-close').onclick=()=>promptDialog.close();$('document-prompt-copy').onclick=()=>copy($('document-figure-prompt').value);$('document-prompt-use').onclick=()=>{if(canReuseFigure(chosenPrompt))usePrompt($('document-figure-prompt').value);};
 new MutationObserver(()=>{if(opened&&(!$('workspace').classList.contains('properties-hidden')||$('workspace').classList.contains('annotations-open')))setOpen(false);}).observe($('workspace'),{attributes:true,attributeFilter:['class']});
 return {open:()=>setOpen(true),close:()=>setOpen(false)};
}
