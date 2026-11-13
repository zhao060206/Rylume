import {preserveCanvasView,syncPanelButtons} from './panel-layout.js';
/** View commands never alter the saved scientific document. */
export function setupWorkbench({editor,workspace}){
  const $=id=>document.getElementById(id);let savedPanels=null;
  document.querySelectorAll('[data-command]').forEach(b=>b.onclick=() => $(b.dataset.command)?.click());
  // Panel commands live in the compact “更多” menu. Keep them usable even
  // when the professional-mode module is unavailable or loads later.
  document.querySelectorAll('[data-panel-command]').forEach(b=>b.onclick=() => {
    const value=b.dataset.panelCommand;
    const target=[...document.querySelectorAll('[data-tab]')].find(node=>node.dataset.tab===value);
    if(target) target.click();
    else b.dispatchEvent(new CustomEvent('ui-action-error',{bubbles:true,detail:{message:'这个面板暂不可用'}}));
  });
  const menus=[...document.querySelectorAll('.app-menu')];
  for(const menu of menus){menu.addEventListener('toggle',()=>{if(menu.open)for(const other of menus)if(other!==menu)other.open=false;});menu.addEventListener('click',e=>{if(e.target.closest('button'))menu.open=false;});}
  document.addEventListener('pointerdown',e=>{for(const m of menus)if(!m.contains(e.target))m.open=false;});
  $('connection-type').onchange=e=>{editor.relationType=e.target.value;};
  $('fit-selection').onclick=()=>editor.fitSelection();
  $('zoom-presets').onchange=e=>{const v=e.target.value;if(v==='fit')$('zoom-fit').click();else if(v==='selection')editor.fitSelection();else if(v)editor.setZoom(Number(v));e.target.value='';};
  $('toggle-grid').onclick=()=>{const active=editor.host.classList.toggle('show-grid');$('toggle-grid').setAttribute('aria-pressed',String(active));};
  function focus(){
    preserveCanvasView(editor,()=>{
    if(savedPanels){workspace.classList.toggle('left-collapsed',savedPanels.left);workspace.classList.toggle('properties-hidden',savedPanels.right);savedPanels=null;}
    else{savedPanels={left:workspace.classList.contains('left-collapsed'),right:workspace.classList.contains('properties-hidden')};workspace.classList.add('left-collapsed','properties-hidden');}
    });syncPanelButtons(workspace);
    $('focus-canvas').setAttribute('aria-pressed',String(!!savedPanels));editor.host.focus({preventScroll:true});
  }
  $('focus-canvas').onclick=focus;
  $('show-shortcuts').onclick=()=>$('shortcuts-dialog').showModal();
  document.addEventListener('keydown',e=>{
    if(e.key==='Escape')for(const m of menus)m.open=false;
    if(e.target.closest('input,textarea,select,[contenteditable=true],dialog'))return;
    if(e.key==='?'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();$('shortcuts-dialog').showModal();}
  });
  // Common editing stays visible; a normal Tab key continues to navigate fields.
  const label=$('quick-label'),font=$('quick-font'),fill=$('quick-fill');
  const bindArrow=document.createElement('button');bindArrow.id='bind-imported-arrow';bindArrow.type='button';bindArrow.className='button full';bindArrow.textContent='改为跟随对象的连线';bindArrow.hidden=true;
  bindArrow.onclick=()=>{const arrow=editor.selectedIds[0];editor.setSelection([]);editor.setTool('connect');editor.replacingArrow=arrow;editor.onStatus('依次点击起点与终点；新连线完成后替换原箭头。按 Esc 可取消，撤销可恢复。');};$('quick-fields').after(bindArrow);
  const ocrPanel=document.createElement('section'),ocrStatus=document.createElement('p'),ocrUse=document.createElement('button'),ocrConfirm=document.createElement('button');
  ocrPanel.className='quick-ocr-review';ocrPanel.hidden=true;ocrStatus.className='muted small';ocrUse.type=ocrConfirm.type='button';ocrUse.className=ocrConfirm.className='button full';ocrConfirm.textContent='已对照原图，确认当前文字';ocrPanel.append(ocrStatus,ocrUse,ocrConfirm);$('quick-fields').after(ocrPanel);
  const importedStructureNote=document.createElement('p');importedStructureNote.className='muted small';importedStructureNote.hidden=true;importedStructureNote.textContent='这是从图片识别的独立结构；内部文字随其移动。原位置按周围颜色估计补底，无法恢复被遮挡的真实细节，请移动后对照原图。';ocrPanel.after(importedStructureNote);
  function selectedText(){return editor.scene?.objects.find(o=>editor.selectedIds.length===1&&editor.selectedIds[0]===o.id&&o.ocr);}
  ocrUse.onclick=()=>{const o=selectedText();if(o?.ocr.suggested)editor.changeSelection({label:o.ocr.suggested,ocr:{...o.ocr,confirmed:true}});};
  ocrConfirm.onclick=()=>{const o=selectedText();if(o)editor.changeSelection({ocr:{...o.ocr,confirmed:true}});};
  const commitLabel=()=>{if(!label.disabled)editor.changeSelection({label:label.value});};
  label.onchange=commitLabel;label.onblur=commitLabel;
  label.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commitLabel();label.blur();editor.host.focus({preventScroll:true});}};
  const commitFont=()=>{const v=Number(font.value);if(v>=7&&v<=48)editor.changeSelection({font_size_pt:v});else refresh();};
  font.onchange=commitFont;font.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commitFont();font.blur();editor.host.focus({preventScroll:true});}};
  fill.onchange=()=>editor.changeSelection({fill:fill.value});
  $('cancel-canvas-tool').onclick=()=>{editor.cancelGesture();editor.setTool('select');};
  $('toolbar-cancel').onclick=()=>$('cancel-canvas-tool').click();
  $('insert-legend')?.addEventListener('click', async () => {
    if (!editor.scene) return;
    editor.host.dispatchEvent(new CustomEvent('editor-request-legend'));
  });
  $('quick-label-focus').onclick=()=>{label.focus();label.select();};
  $('quick-bring-front')?.addEventListener('click', () => editor.bringToFront());
  $('quick-send-back')?.addEventListener('click', () => editor.sendToBack());
  $('beginner-help').onclick=()=>{$('beginner-tips').hidden=!$('beginner-tips').hidden;};
  $('close-beginner-tips').onclick=()=>$('beginner-tips').hidden=true;
  function refresh(){
    syncPanelButtons(workspace);
    for(const b of document.querySelectorAll('[data-tool]')){const active=b.dataset.tool===editor.tool;b.classList.toggle('active',active);b.setAttribute('aria-pressed',String(active));}
    $('add-text').classList.toggle('active',editor.tool==='text');
    $('add-text').setAttribute('aria-pressed',String(editor.tool==='text'));
    const objects=editor.scene?.objects.filter(o=>editor.selectedIds.includes(o.id))||[],relations=editor.scene?.relations.filter(o=>editor.selectedIds.includes(o.id))||[];
    const count=editor.selectedIds.length,o=objects[0]||relations[0];
    bindArrow.hidden=!(count===1&&o?.source_role==='arrow'&&!o.locked);
    importedStructureNote.hidden=!(count===1&&o?.source_role==='structure');
    ocrPanel.hidden=!(count===1&&o?.ocr);if(!ocrPanel.hidden){ocrStatus.textContent=`原图文字 · ${o.ocr.confirmed?'已核对':'请对照原图核对'} · OCR ${Math.round(o.ocr.confidence*100)}%`;ocrUse.hidden=!o.ocr.suggested||o.ocr.suggested===o.label;ocrUse.textContent='采用模型建议：'+(o.ocr.suggested||'');ocrConfirm.hidden=o.ocr.confirmed||o.locked;ocrUse.disabled=!!o.locked;}
    $('quick-label-title').textContent=relations.length&&!objects.length?'线上文字':'修改文字';
    label.placeholder=relations.length&&!objects.length?'可选：给连线加说明':'在这里输入文字';
    workspace.classList.toggle('has-selection',count>0);
    workspace.classList.toggle('tool-in-use',editor.tool!=='select');
    workspace.classList.toggle('editing-connection',editor.tool==='connect'||relations.length>0);
    const contextual=document.querySelector('.quick-edit'),hideContext=!count&&editor.tool!=='connect';
    if(contextual.hidden!==hideContext){
      if(editor.scene&&editor.offset)preserveCanvasView(editor,()=>contextual.hidden=hideContext);
      else contextual.hidden=hideContext;
    }
    document.querySelector('.quick-edit').setAttribute('aria-label',relations.length?'连线编辑':'所选对象快捷编辑');
    $('relation-context').hidden=editor.tool!=='connect'&&!relations.length;

    $('quick-fields').hidden=!count&&editor.tool!=='connect';$('quick-empty').hidden=true;
    $('quick-count').textContent=count===1?(relations.length?'所选连线':o?.display_name||'所选对象'):`已选 ${count} 项`;
    for(const [n,value] of [[label,count===1?o?.label||'':''],[font,objects[0]?.font_size_pt||8],[fill,objects[0]?.fill||'#dae8ed']])if(document.activeElement!==n)n.value=value;
    const connecting=editor.tool==='connect';
    label.closest('label').hidden=count!==1||connecting;
    $('duplicate').hidden=connecting||!objects.length;
    $('delete').hidden=connecting;
    document.querySelector('.selection-more').hidden=!count||editor.tool==='connect';
    label.disabled=count!==1||objects[0]?.locked||!o;font.disabled=!objects.length||objects.every(o=>o.locked);fill.disabled=font.disabled;
    $('quick-label-focus').disabled=label.disabled;
    for(const n of [font,fill])n.closest('label').hidden=!objects.length||editor.tool==='connect';
    $('quick-connect').hidden=!!relations.length&&!objects.length;
    $('cancel-canvas-tool').hidden=editor.tool==='select';
    $('toolbar-cancel').hidden=editor.tool==='select';
    $('toolbar-cancel').textContent=editor.tool==='connect'?'取消连线':'回到选择';
    $('toolbar-guidance').hidden=!hideContext;
    for(const b of document.querySelectorAll('.quick-overflow-action')){const target=$(b.dataset.command);b.disabled=target.disabled;b.hidden=target.hidden;}
    const source=editor.scene?.objects.find(o=>o.id===editor.connectStart);
    $('canvas-hint').textContent=editor.tool==='connect'?(source?`从“${source.label||'所选对象'}”连线：点击目标对象即可完成。`:'先点击起点，再点击终点；连好后自动回到选择。'):editor.tool==='text'?'点击画布放置文字，然后直接输入。':editor.tool==='pan'?'拖动画布查看其他位置；点“选择”继续编辑。':relations.length?'点击连线含义切换类型 · 拖动中间圆点调整弯曲 · 右侧设置虚线与核对状态':count?'拖动移动 · 双击对象改字 · 蓝色圆点可拖出连线':'单击选中 · 拖动框选 · 滚轮上下移动 · Ctrl + 滚轮缩放';
    $('toolbar-guidance-text').textContent=editor.tool==='text'?'在纸张上点击，输入文字。':editor.tool==='pan'?'拖动画布查看；要移动图形，请回到选择。':'点选后改字 · 拖动移动 · 双击文字编辑';
  }
  editor.host.addEventListener('editor-tool-change',refresh);refresh();
  return {refresh};
}
