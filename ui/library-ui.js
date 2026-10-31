import {showFloatingWindow} from './floating-windows.js';
import {rankAssets,assetDisplayName,assetStyle,assetKey} from './asset-search.js';
/** Thumbnail-first, offline scientific library and composition gallery. */
export function filterAssets(assets,{domain='biology',category='',query=''}={}){
  return rankAssets(assets,{domain,category,query});
}
export function selectTemplates(templates,{group='recommended',category='',structure='',query='',legacy=false,drafts=false}={}){
  const q=query.trim().toLowerCase();
  return templates.filter(t=>(group==='recommended'?t.recommended:t.library_group===group)
    &&(legacy||!t.compatibility_only)&&(drafts||!t.draft)&&!t.variant_of
    &&(!category||t.category===category)&&(!structure||t.composition===structure)
    &&(!q||[t.title,t.description,t.usage,t.search_terms,t.category,t.composition,
      ...templates.filter(v=>v.variant_of===t.id).map(v=>v.title+' '+v.description)].join(' ').toLowerCase().includes(q)));
}
export function setupLibrary({editor,api,state,toast,blank,flush,follow,tab,requestResource=()=>{}}){
  const $=id=>document.getElementById(id);
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
  let filter='',structure='',group='recommended',legacy=false,drafts=false,assetCategory='',assetDomain='biology',pending=null,detail=null,assetLimit=60,selectedTemplate=null;
  let favorites=[],recent=[],creatingDocument=null;
  try{favorites=JSON.parse(localStorage.getItem('rylume-favorite-assets')||'[]');recent=JSON.parse(localStorage.getItem('rylume-recent-assets')||'[]');}catch{}
  function remember(){try{localStorage.setItem('rylume-favorite-assets',JSON.stringify(favorites));localStorage.setItem('rylume-recent-assets',JSON.stringify(recent));}catch{toast('素材偏好暂未保存；图版不受影响');}}
  const templateCategory=t=>t.category||({pathway:'通路排版',process:'过程排版',network:'互作排版',assembly:'组装排版'}[t.family]);

  async function insert(item,position){
    if(!state.id||!state.revision){if(!creatingDocument)creatingDocument=blank().finally(()=>creatingDocument=null);await creatingDocument;}
    if(!state.revision)return;
    const documentId=state.id,key=item.asset_id||item.type;
    if(!editor.artwork.has(key)){
      try{
        const {sanitizedSvg}=await import('./canvas-editor.js');
        const response=await fetch(item.thumbnail);
        if(!response.ok)throw Error();
        editor.artwork.set(key,sanitizedSvg(await response.text()));
      }catch{return toast('素材载入失败，请重试',true);}
    }
    if(state.id!==documentId)return toast('图版已切换，请在当前图版重新添加素材。');
    editor.insertObject(item.type,assetDisplayName(item),item,position);editor.ensureSelectionVisible();
    recent=[assetKey(item),...recent.filter(k=>k!==assetKey(item))].slice(0,60);remember();
    editor.host.focus({preventScroll:true});
    toast('已添加 '+item.label+' · 可拖动位置，双击改字');
  }

  function assetDetail(item){
    detail=item;
    $('asset-detail-title').textContent=assetDisplayName(item);
    $('asset-detail-image').src=item.thumbnail;
    const credits=$('asset-detail-credit');
    credits.replaceChildren();
    credits.append(el('p','',`${item.author||'理象原创图元'} · ${item.license||'CC BY 3.0'}`));
    if(item.source_url){
      const a=el('a','source-link','查看原始素材与许可 ↗');
      a.href=item.source_url;a.target='_blank';a.rel='noreferrer';
      credits.append(a,el('p','small','导出时会自动附带图注来源说明。素材为纯矢量路径，可无损缩放、旋转与编辑。'));
    }
    showFloatingWindow($('asset-dialog'));
  }

  function renderAssetChips(){
    const select=$('asset-category');if(!select)return;
    const assets=filterAssets(state.assets,{domain:assetDomain}),counts=new Map();for(const a of assets)counts.set(a.category,(counts.get(a.category)||0)+1);
    select.replaceChildren();for(const [value,title] of [['',`全部分类 (${assets.length})`],...[...counts].map(([c,n])=>[c,`${c} (${n})`])]){const o=el('option','',title);o.value=value;select.append(o);}select.value=assetCategory;
  }

  function renderAssets(){
    const list=$('asset-list');
    const q=($('asset-search')?.value||'').trim().toLowerCase();
    const category=assetCategory || ($('asset-category')?.value || '');
    const assets=rankAssets(state.assets,{domain:assetDomain,category,query:q,style:$('asset-style')?.value||'',view:$('asset-view')?.value||'all',favorites,recent});
    list.replaceChildren();
    if($('asset-count'))$('asset-count').textContent=`${state.assetDomains?.find(d=>d.id===assetDomain)?.title||'生物学'} / ${category||'全部素材'} · ${assets.length} 项`;
    
    for(const item of assets.slice(0,assetLimit)){
      const card=el('div','asset-card');
      const b=el('button','asset-insert');
      const img=el('img','asset-thumb');
      img.src=item.thumbnail;
      img.alt='';
      img.loading='lazy';
      img.draggable=false;
      b.setAttribute('aria-label','添加 '+assetDisplayName(item));
      b.append(img,el('span','asset-name',assetDisplayName(item)));
      const style=el('span','asset-style-tag',{native:'原生图元',flat:'简洁矢量',detailed:'精细插画'}[assetStyle(item)]);b.append(style);
      b.title='点击添加到画布：'+item.label;
      b.onclick=e=>{if(e.detail>1)return;insert(item);};
      card.draggable=true;
      card.ondragstart=e=>{
        e.dataTransfer.setData('application/cell-asset',JSON.stringify(item));
        e.dataTransfer.effectAllowed='copy';
      };
      const info=el('button','asset-license','i');info.setAttribute('aria-label','查看 '+item.label+' 的来源与详情');
      info.title='查看素材出处与大图';
      info.onclick=()=>assetDetail(item);
      const favorite=el('button','asset-favorite',favorites.includes(assetKey(item))?'已收藏':'收藏');favorite.setAttribute('aria-label',(favorites.includes(assetKey(item))?'取消收藏 ':'收藏 ')+assetDisplayName(item));favorite.setAttribute('aria-pressed',String(favorites.includes(assetKey(item))));favorite.onclick=()=>{const key=assetKey(item);favorites=favorites.includes(key)?favorites.filter(x=>x!==key):[...favorites,key];remember();renderAssets();};
      card.append(b,info,favorite);
      list.append(card);
    }
    if(assets.length>assetLimit){
      const more=el('button','button secondary asset-load-more',`再看 60 个 · 还有 ${assets.length-assetLimit} 个`);
      more.onclick=()=>{const y=list.scrollTop;assetLimit+=60;renderAssets();list.scrollTop=y;};
      list.append(more);
    }
    if(!assets.length){
      list.append(el('p','muted','没有找到匹配的素材。可以换一个关键词，或清空筛选。'));
      const reset=el('button','button full','清空搜索与筛选');reset.onclick=()=>{assetCategory='';$('asset-search').value='';$('asset-view').value='all';$('asset-style').value='';renderAssetChips();renderAssets();};list.append(reset);
    }
  }

  function compatible(t){
    return !t.new_scene_only && editor.scene && (editor.scene.compartments.length?'pathway':editor.scene.layout)===t.family;
  }

  async function create(t,canvas){
    if(state.active)return toast('已有生成任务，请等待完成或先取消');
    if(state.revision && !await flush())return;
    try{
      const created=await api('/api/scene/example',{template:t.id,colorway:$('colorway')?.value||'',...(canvas?{canvas_mm:canvas}:{})});
      for(const id of ['template-detail-dialog','gallery-dialog'])if($(id)?.open)$(id).close();
      await follow(created.job_id);
      editor.fit();
    }catch(e){toast(e.message,true);}
  }

  async function preview(t){
    if(!await flush())return;
    try{
      const result=await api('/api/scene/preview-template',{job_id:state.id,base_revision:state.revision,template:t.id});
      pending=result;
      const {sanitizedSvg}=await import('./canvas-editor.js');
      $('template-preview').replaceChildren(sanitizedSvg(result.svg));
      $('template-check').textContent=`${result.scene.objects.length} 个对象，${result.scene.relations.length} 条关系 · ${result.audit.errors} 项错误，${result.audit.warnings} 项待核对`;
      if($('gallery-dialog').open)$('gallery-dialog').close();
      showFloatingWindow($('template-preview-dialog'));
    }catch(e){toast(e.message,true);}
  }

  function templateCard(t,compact=false){
    const card=el('article','template-card');
    const img=el('img','template-thumb');
    img.src=t.thumbnail;img.alt=t.title;img.loading='lazy';
    const shot=el('button','template-shot');
    shot.append(img);
    shot.onclick=()=>showTemplate(t);
    shot.title='预览与了解 '+t.title;
    const body=el('div','template-card-body');
    body.append(el('span','template-category',({science:'机制示意',workflow:'流程骨架',layout:'仅排版'}[t.library_group]||'')+' / '+templateCategory(t)));
    body.append(el('h3','',t.title));
    if(!compact)body.append(el('p','muted',t.usage||t.description));
    if(!compact && t.includes?.length){
      const tags=el('div','template-tags');
      for(const inc of t.includes.slice(0,4))tags.append(el('span','template-tag',inc));
      body.append(tags);
    }
    const actions=el('div','template-actions');
    const start=el('button','button','预览与使用'+(t.variants?.length?` · ${t.variants.length} 个用途变体`:''));
    start.onclick=()=>showTemplate(t);
    actions.append(start);
    if(compatible(t)){
      const apply=el('button','button primary','应用到当前图');
      apply.onclick=()=>preview(t);
      actions.append(apply);
    }
    body.append(actions);
    card.append(shot,body);
    return card;
  }

  function renderTemplates(){
    const q=($('template-search')?.value||'').trim().toLowerCase();
    const sorted=[...state.templates].sort((a,b)=>Number(!!b.recommended)-Number(!!a.recommended));
    const matches=selectTemplates(sorted,{group,category:filter,structure,query:q,legacy,drafts});
    const list=$('template-list');
    if(list)list.replaceChildren(...sorted.filter(t=>t.recommended).map(t=>templateCard(t,true)));
    const grid=$('gallery-grid');
    if(grid){grid.replaceChildren(...matches.map(t=>templateCard(t)));if(!matches.length)grid.append(el('p','muted','没有匹配模板，请更换关键词或分类。'));}
    if($('template-count'))$('template-count').textContent=`${matches.length} 项 · `+({recommended:'按实际用途挑选；配色与摆放变体不另计为新模板。',science:'教学机制示意，使用前请核对科学内容。',workflow:'研究设计骨架，请替换为自己的步骤与条件。',layout:'仅调整已有对象位置；不增加科学机制。'}[group]);
  }

  function showTemplate(t){
    selectedTemplate=t;
    $('template-detail-title').textContent=t.title;
    $('template-detail-kind').textContent=(t.draft?'扩展草图 · 尚未精修':({science:'机制示意',workflow:'流程骨架',layout:'排版预设'}[t.library_group]||'样板'))+' / '+templateCategory(t);
    $('template-detail-usage').textContent=t.usage||t.description;
    $('template-detail-includes').replaceChildren(...(t.includes||[]).map(x=>el('li','',x)));
    $('template-detail-limit').textContent=t.limitations;
    const actual=$('template-actual-objects');actual.replaceChildren();
    actual.append(el('p','muted small',t.recommended?'精选工作起点 · 结构和尺寸检查不等于科学审图；请按使用范围核对。':t.draft?'扩展草图 · 未精修，不作为默认完成稿。':'构图预设 · 仅用于组织当前内容。'));
    if(t.object_labels?.length){
      const d=el('details');d.append(el('summary','',`查看实际对象 · ${t.object_count} 个对象 / ${t.relation_count} 条连接`),el('p','muted small',t.object_labels.join(' · ')));actual.append(d);
    }
    $('template-detail-size').value='default';
    $('template-detail-image').src=t.thumbnail;
    $('template-detail-image').parentElement.classList.remove('inspect');
    $('template-detail-zoom').textContent='放大查看细节';
    $('template-detail-image').alt=t.title+' 的实际图版预览';
    $('template-detail-caption').textContent=`${t.canvas_mm.join(' × ')} mm · 新建后对象、连线与文字均可编辑`;
    const variants=$('template-detail-variants');variants.replaceChildren();
    const parent=state.templates.find(x=>x.id===t.variant_of)||t;
    const options=[parent,...state.templates.filter(x=>x.variant_of===parent.id)];
    if(options.length>1){variants.append(el('h3','','同类用途的其他起点'));for(const v of options){const b=el('button','button'+(v.id===t.id?' selected':''),v.title);b.onclick=()=>showTemplate(v);variants.append(b);}}
    $('template-detail-apply').hidden=!compatible(t);
    $('template-detail-create').textContent=t.library_group==='layout'?'用示例新建图版':'使用模板，开始编辑';
    showFloatingWindow($('template-detail-dialog'));
  }

  function openGallery(){
    renderTemplates();
    showFloatingWindow($('gallery-dialog'));
  }

  function init(data){
    if(!$('asset-style')){const row=el('div','asset-filters');for(const[id,label,choices]of [['asset-view','浏览范围',[['all','全部素材'],['favorites','我的收藏'],['recent','最近使用'],['signaling','机制通路套装'],['trafficking','细胞转运套装']]],['asset-style','视觉风格',[['','全部风格'],['native','原生图元'],['flat','简洁矢量'],['detailed','精细插画']]]]){const select=el('select');select.id=id;select.setAttribute('aria-label',label);for(const[value,title]of choices){const option=el('option','',title);option.value=value;select.append(option);}select.onchange=()=>{assetLimit=60;renderAssets();};row.append(select);}const filters=el('details','panel-disclosure asset-filter-disclosure'),summary=el('summary','','风格与收藏筛选');filters.append(summary,row);$('asset-search').after(filters);}
    state.templates=data.templates||[];
    state.colorways=data.colorways||[];
    state.references=data.references||[];
    state.assetDomains=data.asset_domains||[{id:'biology',label:'生物学',available:true,count:state.assets.length}];
    if(!state.assetDomains.some(d=>d.id===assetDomain&&d.available))assetDomain='biology';
    const domainSelect=$('asset-domain');if(domainSelect){domainSelect.replaceChildren();for(const d of state.assetDomains){const o=el('option','',(d.title||d.label)+(d.available?` (${d.count||0})`:' · 下载资源包'));o.value=d.id;domainSelect.append(o);}domainSelect.value=assetDomain;}
    const categorySelect=$('asset-category');
    if(categorySelect){
      categorySelect.replaceChildren(el('option','','全部分类'));
      categorySelect.options[0].value='';
      for(const c of [...new Set(state.assets.map(a=>a.category).filter(Boolean))]){
        const o=el('option','',c);o.value=c;categorySelect.append(o);
      }
    }
    const colorSelect=$('colorway');
    if(colorSelect){
      colorSelect.replaceChildren();
      const recommended=el('option','','使用模板推荐配色');recommended.value='';colorSelect.append(recommended);
      for(const c of state.colorways){
        const o=el('option','',c.title);o.value=c.id;colorSelect.append(o);
      }
    }
    const filtersContainer=$('gallery-filters');
    if(filtersContainer){
      if(!$('template-search')){
        const search=el('input','template-search');search.type='search';search.id='template-search';
        search.placeholder='搜索主题、分子或用途，例如 PIP2、内体、对照…';search.setAttribute('aria-label','搜索模板');
        search.oninput=renderTemplates;filtersContainer.before(search);
        const count=el('p','muted small');count.id='template-count';filtersContainer.before(count);
      }
      if(!$('template-groups')){
        const groups=el('div','template-groups');groups.id='template-groups';groups.setAttribute('role','group');groups.setAttribute('aria-label','模板类型');
        for(const [id,title] of [['recommended','精选起点'],['science','机制示意'],['workflow','实验流程'],['layout','调整排版']]){const b=el('button',id===group?'active':'',title);b.setAttribute('aria-pressed',String(id===group));b.onclick=()=>{group=id;filter='';structure='';for(const n of groups.children){n.classList.toggle('active',n===b);n.setAttribute('aria-pressed',String(n===b));}renderGalleryFilters();renderTemplates();};groups.append(b);}
        filtersContainer.before(groups);
      }
      renderGalleryFilters();
    }
    function renderGalleryFilters(){
      filtersContainer.replaceChildren();
      const cats=[...new Set(selectTemplates(state.templates,{group,legacy,drafts}).map(t=>t.category).filter(Boolean))];
      for(const [value,title] of [['','全部主题'],...cats.map(c=>[c,c])]){
        const b=el('button','filter-chip'+(value===filter?' active':''),title);
        b.setAttribute('aria-pressed',String(value===filter));
        b.onclick=()=>{
          filter=value;
          for(const n of filtersContainer.querySelectorAll('.filter-chip')){n.classList.toggle('active',n===b);n.setAttribute('aria-pressed',String(n===b));}
          renderTemplates();
        };
        filtersContainer.append(b);
      }
      if(group==='layout'){
        const label=el('label','legacy-layout-toggle');const check=el('input');check.type='checkbox';check.checked=legacy;check.onchange=()=>{legacy=check.checked;renderGalleryFilters();renderTemplates();};label.append(check,'显示旧版排版预设');filtersContainer.append(label);
      }
      if(group==='science'){
        const label=el('label','legacy-layout-toggle');const check=el('input');check.type='checkbox';check.checked=drafts;check.onchange=()=>{drafts=check.checked;filter='';renderGalleryFilters();renderTemplates();};label.append(check,'显示扩展草图（尚未精修）');filtersContainer.append(label);
      }
    }
    renderAssetChips();
    renderAssets();
    renderTemplates();
    renderReferences();
  }

  $('template-detail-size')?.addEventListener('change',e=>{
    if(!selectedTemplate)return;const single=e.target.value==='single';
    $('template-detail-image').src=single?selectedTemplate.thumbnail_single:selectedTemplate.thumbnail;
    $('template-detail-caption').textContent=(single?'90 × 150':selectedTemplate.canvas_mm.join(' × '))+' mm · 实际导出比例预览';
  });
  $('template-detail-zoom')?.addEventListener('click',()=>{
    const zoomed=$('template-detail-image').parentElement.classList.toggle('inspect');
    $('template-detail-zoom').textContent=zoomed?'适合预览窗口':'放大查看细节';
    $('template-detail-zoom').setAttribute('aria-pressed',String(zoomed));
  });
  $('template-detail-create')?.addEventListener('click',()=>{if(selectedTemplate)create(selectedTemplate,$('template-detail-size').value==='single'?[90,150]:null);});
  $('template-detail-apply')?.addEventListener('click',()=>{if(selectedTemplate){$('template-detail-dialog').close();preview(selectedTemplate);}});

  $('asset-search')?.addEventListener('input', ()=>{assetLimit=60;renderAssets();});
  $('asset-domain')?.addEventListener('change',e=>{if(!state.assetDomains.find(d=>d.id===e.target.value)?.available){requestResource(e.target.value);e.target.value=assetDomain;return;}assetDomain=e.target.value;assetCategory='';assetLimit=60;renderAssetChips();renderAssets();});
  $('asset-category')?.addEventListener('change', e=>{
    assetCategory=e.target.value;
    assetLimit=60;
    renderAssetChips();
    renderAssets();
  });
  $('insert-detail-asset')?.addEventListener('click', ()=>{
    if(detail)insert(detail);
    $('asset-dialog').close();
  });
  for(const id of ['open-gallery','welcome-gallery','toolbar-templates']){
    const elBtn=$(id);
    if(elBtn)elBtn.onclick=openGallery;
  }
  $('colorway')?.addEventListener('change', ()=>{
    if(!editor.scene)return;
    const c=state.colorways.find(c=>c.id===$('colorway').value);
    if(c)editor.applyOperations([{op:'style',changes:{palette:c.palette,colorway:c.id}}],'切换配色');
  });
  $('apply-template')?.addEventListener('click', ()=>{
    if(!pending||pending.base_revision!==state.revision||state.pending.length)return toast('图版已变化，请重新预览',true);
    editor.applyOperations([{op:'replace',scene:pending.scene}],'应用排版模板');
    editor.updateDocument(pending.scene,pending.svg);
    editor.fit();
    $('template-preview-dialog').close();
    toast('排版已应用 · Ctrl+Z 可随时撤销');
  });

  editor.host.addEventListener('dragover',e=>{
    e.preventDefault();
    e.dataTransfer.dropEffect='copy';
  });
  editor.host.addEventListener('drop',async e=>{
    e.preventDefault();
    try{
      const item=JSON.parse(e.dataTransfer.getData('application/cell-asset'));
      await insert(item,editor.scene?editor.world(e):null);
    }catch{
      toast('素材放置失败',true);
    }
  });

  
  function referenceDetail(ref){
    $('reference-detail-title').textContent = ref.title;
    $('reference-detail-journal').textContent = ref.journal || '论文图参考';
    $('reference-detail-cat').textContent = ref.category || '机制图范式';
    $('reference-detail-desc').textContent = ref.style_notes || '经典科研机制图构图布局。';
    const img = $('reference-detail-img');
    img.hidden = !ref.web_url;
    if(ref.web_url)img.src = ref.web_url;else img.removeAttribute('src');
    img.alt = ref.title;
    const wrap=img.parentElement;wrap.classList.remove('reference-zoomed');
    let zoom=$('reference-zoom');if(!zoom){zoom=el('button','button secondary','放大查看细节 / 适合窗口');zoom.id='reference-zoom';$('reference-detail-desc').after(zoom);}
    zoom.hidden=!ref.web_url;zoom.onclick=()=>wrap.classList.toggle('reference-zoomed');
    let source=$('reference-source-link');if(!source){source=el('a','source-link');source.id='reference-source-link';source.target='_blank';source.rel='noreferrer';$('reference-detail-desc').after(source);}source.textContent='打开论文原文与图注 ↗';source.href=ref.source_url;
    showFloatingWindow($('reference-dialog'));
  }

  function renderReferences(){
    const list = $('reference-list');
    if (!list) return;
    const refs = state.references || [];
    list.replaceChildren();
    for (const ref of refs) {
      const card = el('article', 'reference-card');
      const shot = el('button', 'reference-shot');
      const img = el('img', 'reference-thumb');
      if(ref.web_url)img.src = ref.web_url;
      img.alt = ref.title;
      img.loading = 'lazy';
      if(ref.web_url){shot.append(img);img.onerror=()=>{img.hidden=true;shot.textContent='图片暂未加载 · 打开来源查看';};}
      else shot.append(el('span','reference-placeholder','打开来源查看图示 ↗'));
      shot.onclick = () => referenceDetail(ref);
      
      const body = el('div', 'reference-card-body');
      const badgeRow = el('div', 'ref-badge-row');
      badgeRow.append(el('span', 'ref-journal-badge', (ref.journal||'绘图参考').split('/')[0].trim()));
      badgeRow.append(el('span', 'ref-cat-badge', ref.category));
      body.append(badgeRow, el('h3', '', ref.title));
      
      const notes = el('p', 'muted small', ref.style_notes);
      const btn = el('button', 'button secondary full', '查看大图与构图解析 ↗');
      btn.onclick = () => referenceDetail(ref);
      body.append(notes, btn);
      
      card.append(shot, body);
      list.append(card);
    }
    if (!refs.length) {
      list.append(el('p', 'muted', '暂无收录的顶刊参考图。'));
    }
  }

  function selectDomain(pid){assetDomain=pid;assetCategory='';assetLimit=60;$('asset-domain').value=pid;renderAssetChips();renderAssets();}
  function openPackTemplates(pid){group='science';filter=state.assetDomains.find(d=>d.id===pid)?.title||'';structure='';for(const b of $('template-groups').children){b.classList.toggle('active',b.textContent==='机制示意');b.setAttribute('aria-pressed',String(b.textContent==='机制示意'));}for(const b of $('gallery-filters').querySelectorAll('button')){if(b.textContent===filter||b.textContent==='全部主题'){b.classList.toggle('active',b.textContent===filter);b.setAttribute('aria-pressed',String(b.textContent===filter));}}openGallery();}
  return {init,renderReferences,renderAssets,renderTemplates,openGallery,showTemplate,insert,selectDomain,openPackTemplates,applyTemplate:preview};
}

