import {setupImportRegions} from './import-regions.js';
import {setupFigureCompare} from './figure-compare.js';
import {setupFloatingWindows,showFloatingWindow} from './floating-windows.js';

export const importBusy = state => ['queued','recognizing','verifying'].includes(state);
export function importFileError(file) {
 if(!file || !/\.(png|jpe?g|webp|svg|pdf)$/i.test(file.name))return '请选择 PNG、JPG、WebP、SVG 或 PDF 文件';
 if(file.size>(/\.svg$/i.test(file.name)?16:10)*1024*1024)return /\.svg$/i.test(file.name)?'SVG 文件请小于 16 MB':'文件请小于 10 MB';
 return '';
}
export function importSummary(report={}) {
 if(report.segmentation_method)return `${report.structures||0} 个独立结构 / 箭头 / 标签 · ${report.assigned_foreground_percent}% 前景已分配 · 0 个位图`;
 if(report.vector_paths)return `${report.texts||0} 个可改字标签 · ${report.vector_groups||0} 组 / ${report.vector_paths} 条矢量路径 · 0 个位图`;
 return `${report.texts||0} 处文字 · ${Math.max(0,(report.objects||0)-(report.texts||0)-(report.image_blocks||0))} 个矢量图形 · ${report.connections||0} 条绑定连线 · ${report.image_blocks||0} 个图片块`;
}
const $=id=>document.getElementById(id);
const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
const button=(text,run,cls='button')=>{const b=make('button',cls,text);b.type='button';b.onclick=run;return b;};
const readFile=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('读取文件失败'));reader.readAsDataURL(file);});

export function setupFigureImport({state,editor,api,flush,canLeave,openJob,refreshJobs,toast}) {
 let selected=null,rows=[],candidate=null,epoch=0,timer=null,mutation=false,selectedFile=null;
 const dialog=make('dialog','figure-import-dialog');dialog.id='figure-import-dialog';dialog.setAttribute('aria-labelledby','figure-import-title');
 dialog.innerHTML=`<header class="dialog-heading"><div><h2 id="figure-import-title">导入科研图</h2><p>保持原图外观，转换为可编辑对象，核对后再继续创作。</p></div><button type="button" class="icon-button" id="close-figure-import" aria-label="关闭导入科研图">×</button></header>
 <div class="figure-import-layout"><aside class="figure-import-sidebar"><button type="button" class="button primary" id="figure-choose">选择科研图</button><input type="file" hidden id="figure-import-file" accept=".png,.jpg,.jpeg,.webp,.svg,.pdf"><p class="small muted">PNG / JPG / WebP / SVG / PDF<br>图片 / PDF 最大 10 MB · SVG 最大 16 MB</p><div class="figure-page-picker" id="figure-page-picker" hidden><label>PDF 页码<input type="number" min="1" max="10000" value="1" id="figure-page"></label><button type="button" class="button" id="figure-upload-page">导入此页</button></div><h3>最近导入</h3><div id="figure-import-list"></div></aside>
 <section class="figure-import-detail"><div id="figure-import-empty" class="figure-drop-zone" tabindex="0" role="button" aria-label="选择或拖入科研图"><svg class="icon"><use href="#download"></use></svg><h3>选择一张科研图</h3><p>点击选择文件，或把图片拖到这里</p><p class="small muted">PNG / JPG / WebP / SVG / PDF · SVG 最大 16 MB · 其他 10 MB<br>原文件保留，转换后对照核对</p></div>
 <div id="figure-import-content" hidden><div class="figure-import-document"><strong id="figure-import-name"></strong><span id="figure-import-badge"></span></div><ol class="figure-import-steps" aria-label="导入步骤"><li>1 选择文件</li><li>2 转换与核对</li><li>3 打开编辑</li></ol>
 <div class="figure-import-comparison"><figure><figcaption>原图<span>原文件保留在本机</span></figcaption><img id="figure-import-source" alt="导入科研图的原图"></figure><figure><figcaption>可编辑候选<span id="figure-import-count"></span></figcaption><div id="figure-import-preview"><p>开始转换后在这里对照结果</p></div></figure></div>
 <p id="figure-import-status" role="status" aria-live="polite"></p><div id="figure-import-report"></div></div></section></div>
 <footer class="figure-import-footer"><div><label>转换方式 <select id="figure-import-mode"><option value="semantic">AI 识别结构 + 本机矢量化</option><option value="vector">本机路径描摹 · 按细节编辑</option><option value="ai">AI 语义拆分 · 保留图片块</option><option value="native">本机拆分 SVG 元素</option></select></label><p id="figure-import-privacy">高保真模式在本机描摹；未配置模型时使用本机 OCR。</p></div><div class="figure-import-buttons"><button type="button" class="button" id="figure-import-cancel" hidden>取消转换</button><button type="button" class="button" id="figure-import-retry-poll" hidden>重新连接</button><button type="button" class="button" id="figure-import-convert" disabled>开始转换</button><button type="button" class="button primary" id="figure-import-accept" hidden>打开为可编辑图版</button></div></footer>`;
 document.body.append(dialog);setupFloatingWindows(dialog);
 const regionEditor=setupImportRegions($('figure-import-source'),()=>render());dialog.querySelector('.figure-import-comparison').before(regionEditor.element);regionEditor.set();
 const compareFigure=setupFigureCompare(),compareButton=button('放大 / 叠加对照',()=>{if(candidate&&current())compareFigure(current().source_url,candidate.svg);});compareButton.id='figure-import-compare';compareButton.hidden=true;$('figure-import-status').before(compareButton);
 const states={uploaded:'已上传',queued:'等待中',recognizing:'识别中',verifying:'检查中',ready:'待核对',failed:'可重试',cancelled:'已取消',interrupted:'已中断'};
 function current(){return rows.find(r=>r.id===selected);}
 function list(){const target=$('figure-import-list');target.replaceChildren();for(const row of rows){const b=button('',()=>select(row.id),'figure-import-row');b.setAttribute('aria-pressed',String(row.id===selected));b.append(make('strong','',row.name),make('small','',`${states[row.state]||row.state}${row.pages>1?' · 第 '+row.page+' 页':''}`));target.append(b);}}
 function update(row){const index=rows.findIndex(r=>r.id===row.id);if(index<0)rows.unshift(row);else rows[index]=row;}
 function render(){
  list();const row=current(),busy=importBusy(row?.state);$('figure-import-content').hidden=!row;$('figure-import-empty').hidden=!!row;
  dialog.classList.toggle('is-empty',!row&&!rows.length);
  $('figure-import-convert').disabled=!row||busy||mutation;$('figure-import-mode').disabled=!row||busy||mutation;
  $('figure-import-cancel').hidden=!busy;$('figure-import-cancel').disabled=mutation;
  $('figure-import-accept').hidden=!candidate||busy;$('figure-import-accept').disabled=mutation||regionEditor.dirty||!!(candidate?.report.vector_paths&&candidate.report.fidelity?.target_met!==true);
  $('figure-import-mode').querySelector('[value=native]').disabled=!row?.name.toLowerCase().endsWith('.svg');
  if(!row)return;
  $('figure-import-name').textContent=row.name+(row.pages>1?` · 第 ${row.page} / ${row.pages} 页`:'');
  $('figure-import-badge').textContent=states[row.state]||row.state;$('figure-import-source').src=row.source_url;
  $('figure-import-status').textContent=row.message;$('figure-import-status').classList.toggle('is-busy',busy);
  $('figure-import-convert').textContent=regionEditor.dirty?'按调整后的边界重新转换':row.state==='uploaded'?'开始转换':'重新转换';
  $('figure-import-count').textContent=candidate?importSummary(candidate.report):'';
  compareButton.hidden=!candidate;
  const report=$('figure-import-report');report.replaceChildren();
  if(candidate){
   report.append(make('p','',candidate.report.segmentation_method?'已识别的结构、文字与箭头可独立移动。未分配的细节保留在背景层，可在上方补选边界后重新转换。':candidate.report.vector_paths?'候选不含位图。插画保留为路径图层，路径分组不等于科学结构；文字独立。':candidate.report.image_blocks?'含独立图片块：可以移动、缩放和替换；内部细节与像素中的文字不能直接编辑。':'文字与图形已拆分，可在画布中独立选中。'));
   if(candidate.report.segmentation_method&&candidate.report.assigned_foreground_percent<98)report.append(make('p','import-coverage-warning',`${candidate.report.assigned_foreground_percent}% 前景已分配；其余背景细节尚未识别为独立对象。请核对边界，或先打开草稿继续调整。`));
   if(candidate.report.fidelity?.available)report.append(make('p','',`原始分辨率前景像素接近度 ${candidate.report.fidelity.foreground_similarity}%；${candidate.report.fidelity.target_met===false?'未达到 99% 验收目标，请重新转换或使用更清晰的原图。':'仍需放大核对文字与布局；此分数不代表内容已经核验。'}`));
   if(candidate.report.outline_labels)report.append(make('p','',`${candidate.report.outline_labels} 个标签保留原字形轮廓，避免字体替换；在本软件中改字后切换为文字。PPTX 中原字形以路径保留，已改写标签为文本框。`));
   const details=make('details');details.append(make('summary','','需要核对的内容'));
   const ul=make('ul');for(const note of [...(candidate.report.warnings||[]),'请检查遗漏、错字、箭头端点和科学含义。自动检查不代表科学内容已核实。'])ul.append(make('li','',note));details.append(ul);report.append(details);
  }
 }
 async function select(id){
  selected=id;candidate=null;regionEditor.set();const token=++epoch;clearTimeout(timer);$('figure-import-preview').replaceChildren(make('p','','转换结果会显示在这里'));
  const row=current();$('figure-import-mode').value=row?.mode||(row?.name.toLowerCase().endsWith('.svg')?'native':'semantic');privacy();render();
  if(row?.state==='ready'){try{const result=await api(`/api/figure-imports/${id}/candidate`);if(token!==epoch)return;candidate=result;regionEditor.set(result.report.regions||[]);const image=new Image();image.alt='高保真矢量候选预览';image.decoding='async';image.src=URL.createObjectURL(new Blob([result.svg],{type:'image/svg+xml'}));image.onload=()=>URL.revokeObjectURL(image.src);$('figure-import-preview').replaceChildren(image);render();}catch(e){if(token===epoch)toast(e.message,true);}}
  schedule();
 }
 function schedule(){clearTimeout(timer);if(dialog.open&&importBusy(current()?.state))timer=setTimeout(poll,1100);}
 async function poll(){const id=selected,token=epoch;try{const row=await api('/api/figure-imports/'+id);if(token!==epoch)return;update(row);$('figure-import-retry-poll').hidden=true;if(row.state==='ready'){await select(id);return;}render();schedule();}catch{if(token!==epoch)return;$('figure-import-status').textContent='暂时连接不上本机服务，原文件已保留。请重新连接查看进度。';$('figure-import-retry-poll').hidden=false;}}
 async function open(){showFloatingWindow(dialog);try{rows=(await api('/api/figure-imports')).imports;await select(selected&&rows.some(r=>r.id===selected)?selected:rows[0]?.id||null);}catch(e){toast(e.message,true);}}
 function privacy(){const mode=$('figure-import-mode').value;$('figure-import-privacy').textContent=mode==='native'?'本机处理，不上传图片。复杂 SVG 可切换高保真重建；路径型箭头不会自动绑定对象。':mode==='semantic'?'将当前页发送给已配置的可读图模型，识别独立结构与边界；原图在本机转为矢量。不调用生图。':mode==='vector'?'优先使用本机 OCR 与矢量描摹；本机未识别出文字时，才会将当前页发送到已配置的可读图模型。候选不嵌入位图。':'AI 拆解会将当前页图片发送到你配置的视觉模型；留空时复用文本模型。复杂插画保留图片块。';}
 $('figure-import-mode').onchange=privacy;
 async function upload(file,page=1){
  if(mutation)return;const error=importFileError(file);if(error)return toast(error,true);
  mutation=true;render();$('figure-choose').disabled=true;
  try{const row=await api('/api/figure-imports',{name:file.name,data:await readFile(file),page});update(row);await select(row.id);}
  catch(e){toast(e.message,true);}finally{mutation=false;$('figure-choose').disabled=false;render();}
 }
 function choose(file){if(!file)return;const error=importFileError(file);if(error)return toast(error,true);selectedFile=file;const pdf=/\.pdf$/i.test(file.name);$('figure-page-picker').hidden=!pdf;$('figure-page').value='1';if(pdf){toast('请填写需要导入的 PDF 页码，再点击“导入此页”');$('figure-page').focus();}else upload(file);}
 $('figure-choose').onclick=()=>$('figure-import-file').click();$('figure-import-file').onchange=e=>{choose(e.target.files[0]);e.target.value='';};
 $('figure-upload-page').onclick=()=>upload(selectedFile,Number($('figure-page').value));
 const drop=$('figure-import-empty');drop.onclick=()=>$('figure-import-file').click();drop.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();drop.click();}};
 dialog.addEventListener('dragover',e=>{e.preventDefault();dialog.classList.add('file-over');});dialog.addEventListener('dragleave',()=>dialog.classList.remove('file-over'));
 dialog.addEventListener('drop',e=>{e.preventDefault();dialog.classList.remove('file-over');choose(e.dataTransfer?.files?.[0]);});
 $('close-figure-import').onclick=()=>dialog.close();dialog.addEventListener('close',()=>clearTimeout(timer));
 $('figure-import-retry-poll').onclick=poll;
 $('figure-import-convert').onclick=async()=>{if(mutation||!current()||importBusy(current().state))return;mutation=true;render();try{const row=await api(`/api/figure-imports/${selected}/convert`,{mode:$('figure-import-mode').value,...(regionEditor.dirty?{regions:regionEditor.get()}:{} )});update(row);await select(row.id);}catch(e){toast(e.message,true);}finally{mutation=false;render();schedule();}};
 $('figure-import-cancel').onclick=async()=>{mutation=true;render();try{await api(`/api/figure-imports/${selected}/cancel`,{});$('figure-import-status').textContent='正在取消；不会创建图版。正在发送的模型请求可能仍需等待返回。';}catch(e){toast(e.message,true);}finally{mutation=false;render();schedule();}};
 $('figure-import-accept').onclick=async()=>{
  if(mutation||!candidate)return;const id=selected,run=candidate.run;mutation=true;render();
  try{if(!await canLeave())throw Error('请先保存当前图版，再打开导入结果');const result=await api(`/api/figure-imports/${id}/accept`,{run});await refreshJobs();await openJob(result.job_id);if(state.id!==result.job_id)throw Error('图版已创建，请从左侧最近图版重新打开');dialog.close();toast('已创建可编辑图版。点选拖动、双击改字；可在文件菜单保存为模板。');}
  catch(e){toast(e.message,true);}finally{mutation=false;render();}
 };

 const templates=make('dialog','personal-template-dialog');templates.id='personal-template-dialog';templates.setAttribute('aria-labelledby','personal-template-title');
 templates.innerHTML='<header class="dialog-heading"><div><h2 id="personal-template-title">我的模板</h2><p>保留布局和对象，每次使用创建独立图版。</p></div></header><div class="personal-template-save"><label>模板名称<input id="personal-template-name" maxlength="120" placeholder="例如：我的实验流程"></label><button type="button" class="button" id="personal-template-save">把当前图版存为模板</button></div><div class="personal-template-grid" id="personal-template-grid"></div>';
 templates.querySelector('header').append(button('关闭',()=>templates.close()));document.body.append(templates);setupFloatingWindows(templates);
 async function loadTemplates(){const rows=(await api('/api/personal-templates')).templates,grid=$('personal-template-grid');grid.replaceChildren();if(!rows.length)grid.append(make('p','template-empty','还没有个人模板。导入一张图，或打开任意图版，编辑后保存到这里。'));
  for(const row of rows){const card=make('article','personal-template-card'),img=make('img');img.src=row.thumbnail;img.alt=row.title;img.loading='lazy';const use=button('用此模板创建',async()=>{use.disabled=true;try{if(!await canLeave())throw Error('请先保存当前图版');const result=await api(`/api/personal-templates/${row.id}/use`,{});await refreshJobs();await openJob(result.job_id);if(state.id===result.job_id)templates.close();}catch(e){toast(e.message,true);}finally{use.disabled=false;}});card.append(img,make('h3','',row.title),make('small','',`${row.objects} 个对象 · 来源 r${row.source_revision}`),use);grid.append(card);}}
 async function openTemplates(){showFloatingWindow(templates);$('personal-template-name').value=editor.scene?.title||'';$('personal-template-save').disabled=!state.revision;try{await loadTemplates();}catch(e){toast(e.message,true);}}
 $('personal-template-save').onclick=async()=>{const b=$('personal-template-save');b.disabled=true;try{if(!await flush())throw Error('当前修改尚未保存，请先保存');await api('/api/personal-templates',{job_id:state.id,base_revision:state.revision,title:$('personal-template-name').value});await loadTemplates();toast('模板已保存，每次使用都会创建独立副本');}catch(e){toast(e.message,true);}finally{b.disabled=!state.revision;}};
 const menu=$('file-menu-items');menu.append(button('导入科研图…',open),button('保存为模板 / 我的模板…',openTemplates));
 const entry=button('我的模板',openTemplates);entry.id='open-personal-templates';document.querySelector('.home-start-links').append(entry);
 const gallery=$('gallery-dialog');gallery?.querySelector('.dialog-heading')?.append(button('我的模板',openTemplates));
 const compare=button('对照导入原图',async()=>{const id=editor.scene?.provenance?.reference_id;if(/^imp_/.test(id||'')){selected=id;await open();}});compare.id='compare-import-original';compare.hidden=true;menu.append(compare);
 const updateCompare=()=>compare.hidden=!/^imp_/.test(editor.scene?.provenance?.reference_id||'');
 document.addEventListener('document-save-state',updateCompare);
 return {open,openTemplates};
}
