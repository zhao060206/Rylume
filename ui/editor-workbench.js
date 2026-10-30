import {preserveCanvasView,syncPanelButtons} from './panel-layout.js';
/** View commands never alter the saved scientific document. */
export function setupWorkbench({editor,workspace}){
  const $=id=>document.getElementById(id);let savedPanels=null;
  document.querySelectorAll('[data-command]').forEach(b=>b.onclick=() => $(b.dataset.command)?.click());
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
  const commitLabel=()=>{if(!label.disabled)editor.changeSelection({label:label.value});};
  label.onchange=commitLabel;label.onblur=commitLabel;
  label.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commitLabel();label.blur();editor.host.focus({preventScroll:true});}};
  const commitFont=()=>{const v=Number(font.value);if(v>=7&&v<=48)editor.changeSelection({font_size_pt:v});else refresh();};
  font.onchange=commitFont;font.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commitFont();font.blur();editor.host.focus({preventScroll:true});}};
  fill.onchange=()=>editor.changeSelection({fill:fill.value});
  $('cancel-canvas-tool').onclick=()=>{editor.cancelGesture();editor.setTool('select');};
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
    $('quick-label-title').textContent=relations.length&&!objects.length?'线上文字':'修改文字';
    label.placeholder=relations.length&&!objects.length?'可选：给连线加说明':'在这里输入文字';
    workspace.classList.toggle('has-selection',count>0);
    workspace.classList.toggle('tool-in-use',editor.tool!=='select');
    workspace.classList.toggle('editing-connection',editor.tool==='connect'||relations.length>0);
    document.querySelector('.quick-edit').hidden=!count&&editor.tool!=='connect';
    document.querySelector('.quick-edit').setAttribute('aria-label',relations.length?'连线编辑':'所选对象快捷编辑');
    $('relation-context').hidden=editor.tool!=='connect'&&!relations.length;

    $('quick-fields').hidden=!count&&editor.tool!=='connect';$('quick-empty').hidden=true;
    $('quick-count').textContent=count===1?(relations.length?'所选连线':'所选对象'):`已选 ${count} 项`;
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
    const source=editor.scene?.objects.find(o=>o.id===editor.connectStart);
    $('canvas-hint').textContent=editor.tool==='connect'?(source?`从“${source.label||'所选对象'}”连线：点击目标对象即可完成。`:'先点击起点，再点击终点；连好后自动回到选择。'):editor.tool==='text'?'点击画布放置文字，然后直接输入。':editor.tool==='pan'?'拖动画布查看其他位置；点“选择”继续编辑。':relations.length?'点击连线含义切换类型 · 拖动中间圆点调整弯曲 · 右侧设置虚线与核对状态':count?'拖动移动 · 双击对象改字 · 蓝色圆点可拖出连线':'单击选中 · 拖动框选 · 滚轮上下移动 · Ctrl + 滚轮缩放';
  }
  editor.host.addEventListener('editor-tool-change',refresh);refresh();
  return {refresh};
}
