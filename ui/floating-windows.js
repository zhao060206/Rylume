/** Movable library windows leave the artwork interactive. */
export function clampPosition(value, size, limit){return Math.max(0,Math.min(value,Math.max(0,limit-size)));}
export function setupFloatingWindows(only=null){
 const panel=only?null:document.querySelector('.workspace>.left-panel');
 const dialogs=only?[only]:['asset-dialog','gallery-dialog','template-detail-dialog','template-preview-dialog','reference-dialog'].map(id=>document.getElementById(id)).filter(Boolean);
 const windows=[...(panel?[panel]:[]),...dialogs];let z=30;
 function bounds(win){return win===panel?win.parentElement.getBoundingClientRect():{left:0,top:0,width:innerWidth,height:innerHeight};}
 function constrain(win){if(win.hidden||win===panel&&win.parentElement.classList.contains('left-collapsed')||win instanceof HTMLDialogElement&&!win.open)return;const area=bounds(win),rect=win.getBoundingClientRect();if(rect.width>area.width)win.style.width=Math.max(0,area.width-8)+'px';if(rect.height>area.height)win.style.height=Math.max(0,area.height-8)+'px';win.style.left=clampPosition(rect.left-area.left,Math.min(rect.width,area.width),area.width)+'px';win.style.top=clampPosition(rect.top-area.top,Math.min(rect.height,area.height),area.height)+'px';win.style.right='auto';win.style.bottom='auto';}
 for(const win of windows){
  let expandedSize=null;
  win.classList.add('floating-library');
  const headings=win===panel?[...win.querySelectorAll('.panel-heading')]:[win.querySelector('.dialog-heading')].filter(Boolean);
  for(const heading of headings){
   const button=document.createElement('button');button.type='button';button.className='floating-minimize icon-button';button.textContent='−';button.title='收起窗口';button.setAttribute('aria-label','收起窗口');button.setAttribute('aria-expanded','true');heading.insertBefore(button,heading.querySelector("button"));
   button.addEventListener('click',()=>{const minimized=win.classList.toggle('is-minimized');if(minimized){expandedSize=win.style.height;win.style.height='';}else{win.style.height=expandedSize||'';expandedSize=null;}for(const b of win.querySelectorAll('.floating-minimize')){b.textContent=minimized?'□':'−';b.title=minimized?'展开窗口':'收起窗口';b.setAttribute('aria-label',b.title);b.setAttribute('aria-expanded',String(!minimized));}constrain(win);});
   heading.tabIndex=0;heading.setAttribute('aria-label','拖动标题移动窗口；聚焦后可用方向键移动');heading.title='拖动标题移动窗口；方向键可微调';heading.addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)||e.target!==heading)return;e.preventDefault();const r=win.getBoundingClientRect(),area=bounds(win),step=e.shiftKey?40:10;win.style.left=clampPosition(r.left-area.left+(e.key==='ArrowRight'?step:e.key==='ArrowLeft'?-step:0),r.width,area.width)+'px';win.style.top=clampPosition(r.top-area.top+(e.key==='ArrowDown'?step:e.key==='ArrowUp'?-step:0),r.height,area.height)+'px';win.style.right='auto';win.style.bottom='auto';});heading.addEventListener('pointerdown',e=>{if(e.button!==0||e.target.closest('button,input,select,a'))return;const r=win.getBoundingClientRect(),area=bounds(win),x=e.clientX,y=e.clientY;win.style.left=(r.left-area.left)+'px';win.style.top=(r.top-area.top)+'px';win.style.right='auto';win.style.bottom='auto';if(win!==panel)win.style.zIndex=String(++z);heading.setPointerCapture(e.pointerId);const move=ev=>{win.style.left=clampPosition(r.left-area.left+ev.clientX-x,r.width,area.width)+'px';win.style.top=clampPosition(r.top-area.top+ev.clientY-y,r.height,area.height)+'px';};const end=()=>{heading.removeEventListener('pointermove',move);heading.removeEventListener('pointerup',end);heading.removeEventListener('pointercancel',end);};heading.addEventListener('pointermove',move);heading.addEventListener('pointerup',end);heading.addEventListener('pointercancel',end);});
  }
  win.addEventListener('pointerdown',()=>{if(win!==panel)win.style.zIndex=String(++z);});
  win.addEventListener('pointerup',()=>constrain(win));
  if(win!==panel){win.addEventListener('close',()=>{if(win.classList.contains('is-minimized'))win.querySelector('.floating-minimize')?.click();});}
  if(win!==panel)win.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();win.close();}});
 }
 addEventListener('resize',()=>windows.forEach(constrain));
 return {restorePanel(){if(panel?.classList.contains('is-minimized'))panel.querySelector('.left-tab:not([hidden]) .floating-minimize')?.click();},constrainPanel(){if(panel)constrain(panel);}};
}
