/** Modeless windows share one stacking order and one restore strip. */
export function clampPosition(value,size,limit){return Math.max(0,Math.min(value,Math.max(0,limit-size)));}
export function fitWindow(rect,area){
 const width=Math.min(Math.max(0,rect.width),area.width),height=Math.min(Math.max(0,rect.height),area.height);
 return {left:clampPosition(rect.left,width,area.width),top:clampPosition(rect.top,height,area.height),width,height};
}
const entries=new Map();let nextLayer=40,dock=null;
function restoreStrip(){
 if(dock)return dock;
 dock=document.createElement('nav');dock.className='window-restore-strip';dock.setAttribute('aria-label','已收起的窗口');dock.hidden=true;
 dock.addEventListener('keydown',e=>e.stopPropagation());document.body.append(dock);return dock;
}
function arrangeStrip(){
 if(!dock)return;
 const workspace=document.getElementById('workspace'),r=workspace?.getBoundingClientRect();
 dock.style.left=Math.max(12,(r?.left||0)+12)+'px';dock.style.maxWidth=Math.max(180,Math.min(680,(r?.width||innerWidth)-32))+'px';
 for(const item of dock.children)item.hidden=item.dataset.windowKind==='panel'&&!!workspace?.classList.contains('showing-start');
 dock.hidden=![...dock.children].some(item=>!item.hidden);
}
export function showFloatingWindow(win){
 if(!win)return;
 const entry=entries.get(win);
 if(entry){entry.open();return;}
 if(!win.open)win.show();
}
export function setupFloatingWindows(only=null){
 const panel=only?null:document.querySelector('.workspace>.left-panel');
 const dialogs=only?[only]:['asset-library-dialog','asset-dialog','gallery-dialog','template-detail-dialog','template-preview-dialog','reference-dialog'].map(id=>document.getElementById(id)).filter(Boolean);
 for(const win of [...(panel?[panel]:[]),...dialogs]){
  if(entries.has(win))continue;
  const isPanel=win===panel,headings=[...win.querySelectorAll(isPanel?'.panel-heading':'.dialog-heading')];
  let savedRect=null,pill=null,drag=null,opener=null;
  const area=()=>{
   if(!isPanel)return {left:8,top:8,width:Math.max(0,innerWidth-16),height:Math.max(0,innerHeight-16)};
   const ws=win.parentElement,r=ws.getBoundingClientRect(),top=(ws.querySelector('.toolbar')?.getBoundingClientRect().bottom||r.top)+8;
   return {left:r.left+8,top,width:Math.max(0,r.width-16),height:Math.max(0,r.bottom-44-top)};
  };
  const visible=()=>!win.classList.contains('is-minimized')&&(isPanel?!win.parentElement.classList.contains('left-collapsed')&&!win.parentElement.classList.contains('showing-start'):win.open);
  const title=()=>((isPanel?win.querySelector('.left-tab:not([hidden]) h1'):win.querySelector('h2'))?.textContent||'窗口').trim();
  const front=()=>{if(!isPanel)win.style.zIndex=String(++nextLayer);};
  function locate(rect){
   const a=area(),v=fitWindow(rect,a);
   const parent=isPanel?win.parentElement.getBoundingClientRect():{left:0,top:0};
   Object.assign(win.style,{left:(v.left+a.left-parent.left)+'px',top:(v.top+a.top-parent.top)+'px',right:'auto',bottom:'auto',width:v.width+'px',height:v.height+'px',minWidth:Math.min(isPanel?270:290,a.width)+'px',minHeight:Math.min(160,a.height)+'px'});
  }
  function currentRect(){const a=area(),r=win.getBoundingClientRect();return {left:r.left-a.left,top:r.top-a.top,width:r.width,height:r.height};}
  function constrain(){if(visible())locate(currentRect());}
  function removePill(){pill?.remove();pill=null;arrangeStrip();}
  function setMinimized(value){win.classList.toggle('is-minimized',value);for(const b of win.querySelectorAll('.floating-minimize'))b.setAttribute('aria-expanded',String(!value));}
  function focusHeading(){(isPanel?win.querySelector('.left-tab:not([hidden]) .panel-heading'):headings[0])?.focus({preventScroll:true});}
  function open(){
   const minimized=win.classList.contains('is-minimized');setMinimized(false);removePill();
   if(!isPanel){for(const b of win.querySelectorAll('.floating-minimize'))b.setAttribute('aria-label','收起'+title());for(const summary of win.querySelectorAll('.floating-options>summary'))summary.setAttribute('aria-label',title()+'窗口选项');}
   if(isPanel)win.parentElement.classList.remove('left-collapsed');else if(!win.open){opener=document.activeElement;win.show();}
   if(minimized&&savedRect)locate(savedRect);else constrain();front();focusHeading();
  }
  function close(){
   setMinimized(false);removePill();savedRect=null;
   if(isPanel)win.parentElement.classList.add('left-collapsed');else win.close();
  }
  function minimize(){
   if(!visible())return;savedRect=currentRect();
   for(const options of win.querySelectorAll('.floating-options'))options.open=false;
   setMinimized(true);if(isPanel)win.parentElement.classList.add('left-collapsed');
   const strip=restoreStrip();pill=document.createElement('div');pill.className='window-restore-item';pill.dataset.windowKind=isPanel?'panel':'dialog';
   const restore=document.createElement('button');restore.type='button';restore.className='window-restore-button';restore.textContent=title();restore.title='恢复 '+title();restore.setAttribute('aria-label','恢复 '+title());restore.onclick=open;
   const dismiss=document.createElement('button');dismiss.type='button';dismiss.textContent='×';dismiss.className='window-restore-close';dismiss.setAttribute('aria-label','关闭已收起的'+title());dismiss.onclick=()=>{close();document.querySelector('[data-tab=assets]')?.focus({preventScroll:true});};
   pill.append(restore,dismiss);strip.append(pill);arrangeStrip();restore.focus({preventScroll:true});
  }
  function reset(){
   Object.assign(win.style,{width:'',height:'',left:'',top:'',right:'',bottom:''});
   if(visible()){
    if(!isPanel){const a=area(),r=win.getBoundingClientRect();locate({left:(a.width-r.width)/2,top:Math.min(72,(a.height-r.height)/2),width:r.width,height:r.height});}
    else constrain();
   }else savedRect=null;
  }
  const entry={open,close,minimize,reset,constrain};entries.set(win,entry);win.classList.add('floating-library');
  for(const heading of headings){
   const controls=document.createElement('div');controls.className='floating-window-actions';
   const options=document.createElement('details');options.className='floating-options';
   const summary=document.createElement('summary');summary.textContent='⋯';summary.title='窗口选项';const headingTitle=(heading.querySelector('h1,h2')?.textContent||title()).trim();summary.setAttribute('aria-label',headingTitle+'窗口选项');
   const menu=document.createElement('div');menu.className='floating-options-menu';
   for(const [label,width,height] of [['紧凑窗口',isPanel?286:440,360],['放大查看',isPanel?480:1000,720]]){const size=document.createElement('button');size.type='button';size.textContent=label;size.onclick=()=>{options.open=false;locate({...currentRect(),width,height});front();focusHeading();};menu.append(size);}
   const resetButton=document.createElement('button');resetButton.type='button';resetButton.textContent='恢复默认位置和大小';resetButton.onclick=()=>{options.open=false;reset();focusHeading();};menu.append(resetButton);options.append(summary,menu);
   const min=document.createElement('button');min.type='button';min.className='floating-minimize';min.textContent='收起';min.title='收起到底部，点击名称可恢复';min.setAttribute('aria-label','收起'+headingTitle);min.setAttribute('aria-expanded','true');min.onclick=minimize;
   const closeButton=heading.querySelector('button');controls.append(options,min);if(closeButton){closeButton.title='关闭';if(isPanel)closeButton.setAttribute('aria-label','关闭'+headingTitle);controls.append(closeButton);}heading.append(controls);
   heading.tabIndex=0;heading.title='拖动标题移动窗口；方向键微调';
   heading.addEventListener('keydown',e=>{if(e.target!==heading||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const r=currentRect(),step=e.shiftKey?40:10;locate({...r,left:r.left+(e.key==='ArrowRight'?step:e.key==='ArrowLeft'?-step:0),top:r.top+(e.key==='ArrowDown'?step:e.key==='ArrowUp'?-step:0)});});
   heading.addEventListener('pointerdown',e=>{
    if(e.button!==0||e.target.closest('button,input,select,a,details'))return;e.preventDefault();front();
    drag={rect:currentRect(),x:e.clientX,y:e.clientY,id:e.pointerId};heading.setPointerCapture(e.pointerId);
   });
   heading.addEventListener('pointermove',e=>{if(!drag||e.pointerId!==drag.id)return;locate({...drag.rect,left:drag.rect.left+e.clientX-drag.x,top:drag.rect.top+e.clientY-drag.y});});
   const end=()=>{drag=null;};for(const name of ['pointerup','pointercancel','lostpointercapture'])heading.addEventListener(name,end);
  }
  win.addEventListener('pointerdown',front);win.addEventListener('pointerup',constrain);
  win.addEventListener('keydown',e=>{e.stopPropagation();if(e.key==='Escape'&&!e.defaultPrevented){e.preventDefault();e.stopPropagation();close();}});
  if(!isPanel){
   win.addEventListener('close',()=>{setMinimized(false);removePill();savedRect=null;if(opener?.isConnected&&!opener.closest('.is-minimized'))opener.focus({preventScroll:true});});
   new MutationObserver(()=>{if(win.open&&visible())constrain();else if(!win.open){setMinimized(false);removePill();}}).observe(win,{attributes:true,attributeFilter:['open']});
  }
 }
 if(!only){
  addEventListener('resize',()=>{for(const entry of entries.values())entry.constrain();arrangeStrip();});
  const ws=document.getElementById('workspace');if(ws)new MutationObserver(arrangeStrip).observe(ws,{attributes:true,attributeFilter:['class']});
  document.addEventListener('pointerdown',e=>{for(const o of document.querySelectorAll('.floating-options[open]'))if(!o.contains(e.target))o.open=false;});
 }
 return {restorePanel(){if(panel?.classList.contains('is-minimized'))entries.get(panel)?.open();},constrainPanel(){if(panel)entries.get(panel)?.constrain();}};
}
