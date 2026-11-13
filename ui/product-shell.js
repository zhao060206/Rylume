import {enhanceSegments, setupMenuKeyboard, setupOptionsDisclosure} from './components/controls.js';
import {setupCommandPalette} from './components/command-palette.js';
import {preserveCanvasView} from './panel-layout.js';

const svg = name => `<svg class="icon" aria-hidden="true"><use href="#${name}"></use></svg>`;

/** Product chrome owns navigation, not scientific scene data or editor gestures. */
export function setupProductShell({state, editor, composer, imports, library, blank, tab, rename, toast}) {
  const $ = id => document.getElementById(id);
  const click = id => () => $(id).click();
  const palette = setupCommandPalette({hasDocument:()=>!!state.id&&$('welcome').hidden,toast,actions:{
    new:click('open-start'), blank, generate:()=>composer.open(), import:()=>imports.open(),
    assets:()=>tab('assets'), templates:click('open-gallery'), documents:click('toggle-documents'),
    guide:click('open-guide'),sketch:click('draw-sketch'),personal:click('open-personal-assets'),mytemplates:click('open-personal-templates'),
    project:click('create-project'), rename, save:click('save-document'), export:click('toggle-export'),
    fit:click('zoom-fit'), focus:click('focus-canvas'), properties:()=>document.querySelector('[data-inspector=properties]').click(),
    annotations:click('open-annotations'),review:click('open-check-toolbar'), settings:click('open-settings'), shortcuts:click('show-shortcuts'),
  }});
  setupMenuKeyboard();
  setupOptionsDisclosure(document.querySelector('.composer-options'));
  enhanceSegments(document.querySelector('.workspace-mode-switch'),{attribute:'aria-pressed',keyboard:false});
  $('rename-document').onclick = rename;
  $('sidebar-assets').onclick = () => tab('assets');
  $('sidebar-templates').onclick = click('open-gallery');
  $('home-all-templates').onclick = click('open-gallery');
  $('home-open-documents').onclick = click('toggle-documents');
  $('open-start').innerHTML = svg('plus') + '<span>新建图版</span>';
  $('create-project').textContent = '新建项目';
  $('create-project').insertAdjacentHTML('afterbegin',svg('folder-plus'));
  $('brief-input').placeholder = '例如：画出 JAK–STAT 信号通路，区分胞外、细胞质和细胞核，标出激活与转运。';
  $('brief-input').setAttribute('aria-label','绘图描述');
  $('expand-brief').title = '保留科学原意，优化表达；核对后再采用';
  $('preview-generation').title = '先查看科研对象、连接和排版，再决定是否生成';
  $('composer-attach').title = '上传参考图、绘制草稿或使用当前画布';
  // Drawing mode and structure preview are decisions users need before generation.
  const keyHint = document.createElement('span'); keyHint.className='composer-key-hint'; keyHint.textContent='Ctrl + Enter 生成';
  document.querySelector('.composer-submit-row').prepend(keyHint);
  document.querySelector('.creation-submit').prepend(document.querySelector('.composer-output'));
  document.querySelector('.composer-options-body').append(document.querySelector('.composer-settings'));
  document.querySelector('.composer-submit-row').insertBefore($('preview-generation'),$('generate'));
  $('composer-attach').after($('draw-sketch'));
  $('draw-sketch').innerHTML=svg('compose')+'<span>手绘草图</span>';
  $('draw-sketch').classList.add('button');
  document.querySelector('.composer-options>summary').textContent='更多设置';
  for(const button of document.querySelectorAll('[data-generation-mode]'))button.title=button.textContent.trim();
  const short = document.createElement('span'); short.className='canvas-shortcuts';short.textContent='V 选择 · C 连线 · 双击改字';
  $('canvas-size').after(short);
  document.querySelector('.toolbar [data-tool=pan] .tool-caption').textContent='平移';
  document.querySelector('.toolbar [data-tool=connect] .tool-caption').textContent='连线';
  $('add-text').querySelector('.tool-caption').textContent='文字';
  $('canvas-settings').onclick=()=>{editor.setSelection([]);preserveCanvasView(editor,()=>{
    $('workspace').classList.remove('properties-hidden');
    document.querySelector('[data-inspector=properties]').click();
    inspectorMore.open=true;
  });};
  $('open-annotations').textContent='批注修改';
  // Primary actions live on the workbench; the menu holds secondary parameters.
  const inspectorMore=document.createElement('details');inspectorMore.className='inspector-details';
  const inspectorSummary=document.createElement('summary');inspectorSummary.textContent='更多属性';
  $('property-content').before(inspectorMore);inspectorMore.append(inspectorSummary,$('property-content'));
  const inspectorTabs=document.querySelector('.inspector-tabs');
  document.querySelector('.properties-heading').after(inspectorTabs);
  const rail=document.querySelector('.top-tools');rail.classList.add('creation-tools');
  const toolbar=document.querySelector('.toolbar');toolbar.insertBefore(rail,document.querySelector('.insert-menu'));
  rail.append(document.querySelector('[data-tab=assets]'),document.querySelector('[data-tab=templates]'),$('toolbar-import-figure'),document.querySelector('[data-tab=generate]'));
  $('toolbar-import-figure').querySelector('span').textContent='导入科研图';
  document.querySelector('[data-tab=templates] span').textContent='模板库';
  document.querySelector('[data-tab=assets] span').textContent='素材库';
  document.querySelector('.canvas-actions').append($('toggle-properties'));
  $('toggle-properties').removeAttribute('hidden');
  const modeSwitch=document.querySelector('.workspace-mode-switch');
  document.querySelector('.document-bar-actions').prepend(modeSwitch);
  const resourceMenu=document.querySelector('.insert-menu .menu-items');
  for(const id of ['home-import-assets','open-personal-templates']){const control=$(id);if(control)resourceMenu.append(control);}
  const helpMenu=$('settings-menu-items');
  for(const id of ['empty-model-settings','home-onboarding','home-open-documents'])if($(id))helpMenu.append($(id));
  document.querySelector('.home-ai-note').remove();
  const libraries=document.createElement('div');libraries.className='sidebar-library-links';
  libraries.append($('sidebar-assets'),$('sidebar-templates'));
  document.querySelector('.sidebar-documents').before(libraries);
  $('toggle-documents').innerHTML=svg('icon-journal')+'<span>文档助手</span>';
  $('open-commands').querySelector('span').textContent='查找操作';
  const documentMenu=document.querySelector('.document-menu');
  const documentMenuRoot=documentMenu.closest('.app-menu');
  documentMenuRoot.addEventListener('toggle',()=>{if(!documentMenuRoot.open)for(const submenu of documentMenu.querySelectorAll('.document-submenu'))submenu.open=false;});
  const sections=[...documentMenu.querySelectorAll(':scope>.document-menu-section')];
  const names=['文件与版本','排列与编辑','显示与吸附','工作区设置'];
  for(const [index,group] of sections.entries()){
    const disclosure=document.createElement('details');disclosure.className='document-submenu';
    const label=document.createElement('summary');label.textContent=names[index];
    group.querySelector('h3')?.remove();group.before(disclosure);disclosure.append(label,group);
    disclosure.addEventListener('toggle',()=>{if(disclosure.open)for(const other of documentMenu.querySelectorAll('.document-submenu'))if(other!==disclosure)other.open=false;});
  }
  for(const [label,run]of [['图版设置',()=> $('canvas-settings').click()],['检查图版',()=>document.querySelector('[data-inspector=review]').click()]]){
    const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=run;
    documentMenu.insertBefore(button,documentMenu.querySelector('.document-submenu'));
  }
  // Compatibility targets keep their listeners, while repeated launchers leave the UI.
  for(const selector of ['#empty-model-settings','#home-onboarding','#home-open-documents',
    '.document-menu #toggle-properties','.document-menu #open-check-toolbar','.document-menu [data-command=toggle-properties]',
    '.document-menu [data-command=open-check-toolbar]','.document-menu [data-panel-command]',
    '.document-menu [data-command=beginner-help]'])document.querySelector(selector)?.setAttribute('hidden','');
  for(const id of ['sidebar-assets','sidebar-templates'])$(id).removeAttribute('hidden');
  for(const button of document.querySelectorAll('[data-tab=generate] span'))button.textContent='AI 绘图';
  const observer = new MutationObserver(() => {
    $('rename-document').disabled=!state.id;
    $('home-template-shelf').hidden=$('welcome').hidden;
  });
  observer.observe($('welcome'),{attributes:true,attributeFilter:['hidden']});
  editor.host.addEventListener('editor-tool-change',()=>{
    if(editor.tool==='connect'&&$('welcome').hidden&&!$('workspace').classList.contains('annotations-open'))
      document.querySelector('[data-inspector=properties]').click();
  });
  function refresh() {
    const assets=$('panel-assets');
    if(!assets.querySelector('.asset-search-row')){
      const searchRow=document.createElement('div');searchRow.className='asset-search-row';
      searchRow.append($('asset-search'),$('asset-language-toggle'));
      const taxonomy=document.createElement('div');taxonomy.className='asset-taxonomy';
      for(const id of ['asset-domain','asset-category']){
        const field=document.createElement('div');field.className='asset-taxonomy-field';
        field.append(document.querySelector(`label[for="${id}"]`),$(id));taxonomy.append(field);
      }
      const tools=document.createElement('div');tools.className='asset-library-footer';
      const personal=$('open-personal-assets')?.parentElement;
      if(personal)tools.append(personal);
      tools.append($('download-discipline-assets'));
      for(const button of assets.querySelectorAll(':scope > button'))tools.append(button);
      assets.querySelector(':scope>p.muted')?.setAttribute('hidden','');
      assets.prepend(searchRow,taxonomy);
      assets.append(tools);
    }
    const host=$('home-template-examples');host.replaceChildren();
    const all=(state.templates||[]).filter(item=>item.recommended&&item.thumbnail&&!item.variant_of&&!item.draft&&!item.compatibility_only);
    const chosen=[],families=new Set();
    for(const item of all){const family=item.family||item.category;if(!families.has(family)){chosen.push(item);families.add(family);}if(chosen.length===3)break;}
    for(const item of chosen){
      const button=document.createElement('button');button.type='button';button.className='home-template-example';
      button.title='预览模板：'+item.title;
      const image=document.createElement('img');image.src=item.thumbnail;image.alt=item.title+'模板预览';image.loading='lazy';
      const label=document.createElement('span');label.textContent=item.title;button.append(image,label);
      button.onclick=()=>library.showTemplate(item);host.append(button);
    }
    $('home-template-shelf').hidden=!chosen.length||$('welcome').hidden;
  }
  return {refresh, palette};
}
