import {setupFloatingWindows,showFloatingWindow} from './floating-windows.js';
import {assetMatch} from './asset-search.js';

export const assetBusy = asset => ['queued','analyzing','tracing','verifying'].includes(asset?.state);
export function candidateWarnings(candidate){
 const notes=[...(candidate?.warnings||[])];
 for(const source of [candidate?.analysis,candidate?.review])if(Array.isArray(source?.warnings))notes.push(...source.warnings.filter(s=>typeof s==='string'));
 return [...new Set(notes)];
}

/** Import and review are separate actions; no background task changes the canvas. */
export function setupPersonalAssets({api,toast,library,state}){
 const make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const dialog=make('dialog','asset-import-dialog');dialog.id='personal-assets-dialog';dialog.setAttribute('aria-labelledby','personal-assets-title');
 dialog.innerHTML=`<div class="dialog-heading"><div><h2 id="personal-assets-title">我的素材</h2><p class="muted small">上传自己的图片，转换后在每张图中重复使用。</p></div><button type="button" class="icon-button" aria-label="关闭我的素材">×</button></div>
 <div class="personal-layout"><aside class="personal-library"><button type="button" class="button primary full" id="personal-choose">上传素材图片</button><input type="file" id="personal-file" accept="image/png,image/jpeg,image/webp" hidden><input type="search" id="personal-search" aria-label="搜索我的素材" placeholder="搜索我的素材"><div class="personal-items" id="personal-items"></div><label class="checkbox-field"><input type="checkbox" id="personal-archived">显示已收起素材</label></aside>
 <section class="personal-detail"><div id="personal-empty" class="personal-empty"><svg class="icon"><use href="#layers"></use></svg><h3>把常用素材，留在自己的库里</h3><p>上传一个细胞、仪器或其他独立素材。支持 PNG、JPG、WebP，最大 10 MB。</p><p class="small muted">原始文件保留在本机。转换结果确认后才加入素材库。</p></div>
 <div id="personal-content" hidden><div class="personal-meta"><label>素材名称<input id="personal-name" maxlength="100" readonly></label><span class="personal-badge" id="personal-state"></span></div><div class="personal-comparison"><figure><figcaption>原图 <span>始终保留</span></figcaption><div class="asset-checker"><img id="personal-source" alt="上传的原始素材"></div></figure><figure><figcaption>矢量候选 <span id="personal-score">尚未转换</span></figcaption><div class="asset-checker"><img id="personal-vector" alt="矢量化结果" hidden><p id="personal-vector-empty">转换后在这里并排对照</p></div></figure></div>
 <div class="personal-progress" role="status" aria-live="polite" id="personal-progress"></div><div id="personal-report" class="personal-report" hidden></div><div class="personal-actions"><label class="checkbox-field"><input id="personal-use-model" type="checkbox" checked>使用已配置模型分析与复核</label><p class="muted small">勾选后，图片会发送至你配置的视觉模型；未配置时使用本机描摹。</p><div class="dialog-actions"><button type="button" class="button" id="personal-convert">高保真矢量化</button><button type="button" class="button" id="personal-cancel" hidden>取消转换</button><button type="button" class="button primary" id="personal-accept" hidden>确认并加入素材库</button><button type="button" class="button primary" id="personal-insert" hidden>插入画布</button><button type="button" class="text-button" id="personal-archive">收起素材</button></div></div></div></section></div>`;
 document.body.append(dialog);setupFloatingWindows(dialog);
 const $=id=>dialog.querySelector('#'+id);dialog.querySelector('[aria-label="关闭我的素材"]').onclick=()=>dialog.close();
 const fields=make('div','personal-classification'),domainLabel=make('label','','学科'),domain=make('select'),categoryLabel=make('label','','分类'),category=make('input'),saveMeta=make('button','button','保存名称与分类');
 domain.id='personal-domain';category.id='personal-category';category.maxLength=80;saveMeta.id='personal-save-meta';saveMeta.type='button';
 for(const [id,label]of [['biology','生物学'],['chemistry','化学'],['physics','物理学'],['materials','材料科学'],['engineering','工程技术'],['earth-environment','地球与环境'],['computing-math','计算机与数学'],['medicine','医学']]){const option=make('option','',label);option.value=id;domain.append(option);}
 domainLabel.append(domain);categoryLabel.append(category);fields.append(domainLabel,categoryLabel,saveMeta);dialog.querySelector('.personal-meta').after(fields);$('personal-name').readOnly=false;
 const reviewScroll=make('div','personal-review-scroll'),content=$('personal-content'),actions=dialog.querySelector('.personal-actions');
 for(const child of [...content.children])if(child!==actions)reviewScroll.append(child);
 content.prepend(reviewScroll);
 let assets=[],selected=null,timer=null,uploading=false,mutation=false,rendered='';
 const entry=make('div','personal-entry'),open=make('button','button','我的素材'),upload=make('button','button','上传素材');
 open.id='open-personal-assets';upload.id='upload-personal-assets';entry.append(open,upload);
 document.getElementById('panel-assets').prepend(entry);
 const home=make('button','','导入自己的素材');home.type='button';home.id='home-import-assets';home.innerHTML='<svg class="icon" aria-hidden="true"><use href="#download"></use></svg><span>导入素材</span>';document.querySelector('.home-start-links').append(home);
 const states={uploaded:'原图已保存',queued:'排队中',analyzing:'模型分析中',tracing:'矢量转换中',verifying:'对照核验中',ready:'等待确认',failed:'可重新转换',cancelled:'已取消',interrupted:'上次转换已中断'};
 function schedule(){clearTimeout(timer);if(dialog.open&&assets.some(assetBusy))timer=setTimeout(load,1100);}
 async function load(){try{assets=(await api('/api/personal-assets')).assets;if(!selected)selected=assets.find(a=>!a.archived)?.id||null;render();schedule();}catch(e){toast(e.message,true);}}
 function render(){
  const query=$('personal-search').value.trim().toLowerCase(),archive=$('personal-archived').checked;
  const visible=assets.filter(a=>(archive||!a.archived)&&assetMatch(a,query).score>=0);
  const list=$('personal-items');list.replaceChildren();
  for(const a of visible){const b=make('button','personal-item'+(a.id===selected?' active':''));b.type='button';b.setAttribute('aria-pressed',String(a.id===selected));const img=make('img');img.src=a.source_url;img.alt='';const copy=make('span');copy.append(make('strong','',a.label),make('small','',a.archived?'已收起':a.accepted_run?'已在素材库':states[a.state]||a.state));if(query&&assetMatch(a,query).kind==='fuzzy')copy.append(make('small','asset-match-tag','近似匹配'));b.append(img,copy);b.onclick=()=>{selected=a.id;rendered='';render();};list.append(b);}
  if(!visible.length)list.append(make('p','muted small',query?'没有匹配的素材':'上传的素材会保存在这里。'));
  const a=assets.find(a=>a.id===selected);$('personal-empty').hidden=!!a;$('personal-content').hidden=!a;if(!a)return;
  const signature=JSON.stringify(a);if(signature===rendered)return;rendered=signature;
  $('personal-name').value=a.label;$('personal-source').src=a.source_url;
  $('personal-state').textContent=a.accepted_run?'已在素材库':states[a.state]||a.state;
  const candidate=a.candidate,busy=assetBusy(a);
  domain.value=a.domain;category.value=a.category;for(const field of [domain,category,saveMeta,$('personal-name')])field.disabled=busy;
  $('personal-progress').textContent=a.message;
  $('personal-progress').classList.toggle('is-busy',busy);
  $('personal-convert').disabled=busy||mutation||a.archived;
  $('personal-convert').textContent=candidate?'重新转换':'高保真矢量化';
  $('personal-cancel').hidden=!busy;$('personal-use-model').disabled=busy;
  $('personal-accept').hidden=!candidate||a.accepted_run===candidate.run||busy||a.archived;
  $('personal-insert').hidden=!a.accepted_run||a.archived;
  $('personal-archive').disabled=busy;$('personal-archive').textContent=a.archived?'恢复素材':'收起素材';
  $('personal-vector').hidden=!candidate;$('personal-vector-empty').hidden=!!candidate;
  $('personal-score').textContent=candidate?`前景接近度 ${candidate.quality.foreground_similarity}%`:'尚未转换';
  if(candidate)$('personal-vector').src=a.candidate_url;
  const report=$('personal-report');report.replaceChildren();report.hidden=!candidate;
  if(candidate){
   report.append(make('strong','',candidate.review_status==='completed'?'模型复核已返回 · 请对照确认':'本机对照已完成 · 请确认效果'));
   if(typeof candidate.analysis?.summary==='string')report.append(make('p','',candidate.analysis.summary));
   if(typeof candidate.review?.summary==='string')report.append(make('p','',candidate.review.summary));
   report.append(make('p','small muted',candidate.quality.note));
   const notes=make('ul');for(const text of candidateWarnings(candidate))notes.append(make('li','',text));report.append(notes);
   const download=make('a','text-button','下载候选 SVG');download.href=a.candidate_url;download.download=a.label+'.svg';report.append(download);
  }
 }
 async function refreshCatalog(){const data=await api('/api/scene/catalog');state.assets=data.assets;library.init(data);}
 async function action(action,body={}){
  if(!selected||mutation)return;mutation=true;const id=selected;
  try{const result=await api(`/api/personal-assets/${id}/${action}`,body);const i=assets.findIndex(a=>a.id===id);assets[i]=result;
   if(['accept','archive','restore','metadata'].includes(action))await refreshCatalog();rendered='';render();schedule();
   if(action==='accept')toast('已加入我的素材，可插入画布并重复使用');
  }catch(e){toast(e.message,true);}finally{mutation=false;rendered='';render();}
 }
 $('personal-convert').onclick=()=>action('vectorize',{use_model:$('personal-use-model').checked});
 saveMeta.onclick=()=>action('metadata',{label:$('personal-name').value,domain:domain.value,category:category.value});
 $('personal-cancel').onclick=()=>action('cancel');
 $('personal-accept').onclick=()=>{const a=assets.find(a=>a.id===selected);if(a?.candidate)action('accept',{run:a.candidate.run});};
 $('personal-archive').onclick=()=>action(assets.find(a=>a.id===selected)?.archived?'restore':'archive');
 $('personal-insert').onclick=async()=>{try{await refreshCatalog();const item=state.assets.find(a=>a.asset_id===selected);if(!item)return toast('素材尚未确认加入素材库',true);await library.insert(item);dialog.close();}catch(e){toast(e.message,true);}};
 $('personal-search').oninput=render;$('personal-archived').onchange=render;
 $('personal-choose').onclick=()=>$('personal-file').click();
 async function uploadFile(file){
  if(!file||uploading)return;
  if(!['image/png','image/jpeg','image/webp'].includes(file.type))return toast('请选择 PNG、JPG 或 WebP 图片',true);
  if(file.size>10*1024*1024)return toast('素材图片请小于 10 MB',true);
  uploading=true;$('personal-choose').disabled=true;$('personal-choose').textContent='正在保留原图…';
  try{const image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('图片读取失败'));reader.readAsDataURL(file);});
   const a=await api('/api/personal-assets',{image,label:file.name.replace(/\.[^.]+$/,''),domain:document.getElementById('asset-domain').value||'biology'});
   selected=a.id;await load();toast('原图已保存。点击高保真矢量化开始转换。');
  }catch(e){toast(e.message,true);}finally{uploading=false;$('personal-choose').disabled=false;$('personal-choose').textContent='上传素材图片';$('personal-file').value='';}
 }
 $('personal-file').onchange=e=>uploadFile(e.target.files?.[0]);
 dialog.addEventListener('dragover',e=>{if(e.dataTransfer?.types.includes('Files')){e.preventDefault();dialog.classList.add('file-drag-over');}});
 dialog.addEventListener('dragleave',e=>{if(!dialog.contains(e.relatedTarget))dialog.classList.remove('file-drag-over');});
 dialog.addEventListener('drop',e=>{e.preventDefault();dialog.classList.remove('file-drag-over');uploadFile(e.dataTransfer?.files?.[0]);});
 async function show(choose=false){showFloatingWindow(dialog);await load();if(choose)$('personal-file').click();}
 open.onclick=()=>show();upload.onclick=()=>show(true);home.onclick=()=>show();
 dialog.addEventListener('close',()=>clearTimeout(timer));
 return {open:show};
}
