/** A predictable home, a single tool strip, and a stationary editing inspector. */
export function setupWorkspaceExperience({imports,composer,blank}) {
 const $=id=>document.getElementById(id),make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const host=$('home-composer-host'),nav=make('div','start-modes');nav.setAttribute('role','tablist');nav.setAttribute('aria-label','选择开始方式');
 const panels={ai:host,import:make('section','start-option-panel'),manual:make('section','start-option-panel')};
 panels.import.id='home-import-panel';panels.manual.id='home-manual-panel';
 const options=[['ai','AI 绘图','写下想法，生成可编辑初稿','spark'],['import','导入已有图','拆分文字、图形和连线','download'],['manual','手动绘制','空白画布，像做 PPT 一样','pointer']];
 function choose(mode,focus=false){for(const [id]of options){const b=$('start-mode-'+id);b.setAttribute('aria-selected',String(id===mode));b.tabIndex=id===mode?0:-1;panels[id].hidden=id!==mode;}if(focus)$('start-mode-'+mode).focus();}
 for(const [id,title,description,icon]of options){const b=make('button','start-mode');b.type='button';b.id='start-mode-'+id;b.setAttribute('role','tab');b.setAttribute('aria-controls',panels[id].id);b.innerHTML=`<svg class="icon" aria-hidden="true"><use href="#${icon}"></use></svg>`;const copy=make('span');copy.append(make('strong','',title),make('small','',description));b.append(copy);b.onclick=()=>choose(id);nav.append(b);panels[id].setAttribute('role','tabpanel');panels[id].setAttribute('aria-labelledby',b.id);}
 nav.onkeydown=e=>{const keys=['ArrowLeft','ArrowRight','Home','End'];if(!keys.includes(e.key))return;e.preventDefault();const index=options.findIndex(([id])=>$('start-mode-'+id).getAttribute('aria-selected')==='true');const next=e.key==='Home'?0:e.key==='End'?2:(index+(e.key==='ArrowRight'?1:2))%3;choose(options[next][0],true);};
 host.before(nav);host.after(panels.import,panels.manual);
 const launch=(panel,title,copy,label,action)=>{panel.append(make('h3','',title),make('p','',copy));const b=make('button','button primary',label);b.type='button';b.onclick=action;panel.append(b);};
 launch(panels.import,'让已有图版，成为你的起点。','导入 PNG、JPG、WebP、SVG 或 PDF。先对照原图检查，再进入画布编辑。也可以把调整好的图版存为个人模板。','选择科研图…',imports.open);
 launch(panels.manual,'一张空白画布，随时开始。','添加图形和素材，双击改字，拖出连线。修改自动保存，也可以用 Ctrl+S 手动保存。','创建空白图版',blank);
 const links=document.querySelector('.home-start-links');$('welcome-blank').hidden=true;
 const title=document.querySelector('.home-heading h2');title.textContent='今天，从哪里开始？';document.querySelector('.home-intro').textContent='创建新图、继续已有图，或从一张空白画布开始。';
 const resources=make('div','start-resources-heading','也可以直接复用');links.before(resources);
 const personal=$('home-import-assets');if(personal)personal.querySelector('span').textContent='上传单个素材';
 // Keep source comparison and import available from the document toolbar as well.
 const action=make('button','rail-item');action.id='toolbar-import-figure';action.type='button';action.title='导入整张科研图，并创建独立的可编辑图版';action.innerHTML='<svg class="icon" aria-hidden="true"><use href="#download"></use></svg><span>导入图</span>';action.onclick=imports.open;
 document.querySelector('.top-tools [data-tab=templates]').after(action);
 const quick=document.querySelector('.quick-edit');quick.classList.add('inspector-quick-edit');$('property-content').before(quick);
 const guidance=$('toolbar-guidance');guidance.removeAttribute('hidden');$('toolbar-guidance-text').textContent='点选拖动 · 双击改字';
 $('toggle-properties').classList.remove('professional-only');
 document.addEventListener('creation-surface-requested',()=>choose('ai'));
 choose('ai');
 return {showAI(){choose('ai');composer.open();}};
}
