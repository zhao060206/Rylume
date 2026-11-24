/** Work dock: tool windows open beside the canvas instead of covering it.
 * Feature modules keep calling dialog.showModal()/show(). Windows listed here
 * open without a backdrop and dock to the right edge, so the canvas stays
 * usable. Decisions that must block (onboarding, destructive confirmation,
 * recovery, sketch pad) stay modal. */
const DOCK_IDS=new Set(['export-menu','history-dialog','audit-dialog','ai-dialog','asset-library-dialog','gallery-dialog','template-detail-dialog','template-preview-dialog','asset-dialog','reference-dialog','models-dialog','brief-preview-dialog','guide-dialog','original-revise-dialog','redraw-object-dialog','shortcuts-dialog','fix-preview-dialog','generation-preview-dialog']);
const proto=HTMLDialogElement.prototype,nativeShow=proto.show,nativeModal=proto.showModal;
const stack=[];let strip=null;
export function isDocked(d){return !!d&&(DOCK_IDS.has(d.id)||d.dataset.dock==='true');}
export function plainMessage(message){
 let s=String(message==null?'':message);
 if(/Failed to fetch|NetworkError|ERR_CONNECTION/i.test(s))return '暂时连接不上本机服务，修改仍在本机，请稍后重试。';
 if(/ModuleNotFoundError|ImportError|No module named/.test(s))return '缺少运行组件，请重新安装理象 Rylume 后再试；图版已保留。';
 s=s.replace(/(^|[；;。，]\s*)[A-Z][A-Za-z]*(?:Error|Exception):\s*/g,'$1');
 return s.trim();
}
function titleOf(d){return ((d.querySelector('h2,h1')||{}).textContent||'面板').trim().slice(0,16);}
function ensureStrip(){
 if(strip)return strip;
 strip=document.createElement('nav');strip.className='dock-tabs';strip.setAttribute('aria-label','已打开的面板');strip.hidden=true;document.body.append(strip);return strip;
}
function relayout(){
 for(let i=stack.length-1;i>=0;i--)if(!stack[i].open||stack[i].hidden)stack.splice(i,1);
 const shown=stack.filter(d=>!d.classList.contains('is-minimized'));
 const top=shown[shown.length-1];
 for(const d of stack)d.classList.toggle('dock-behind',!!top&&d!==top&&shown.includes(d));
 document.body.classList.toggle('dock-open',!!top);
 document.body.classList.toggle('dock-multi',shown.length>1);
 const s=ensureStrip();s.replaceChildren();s.hidden=shown.length<2;
 for(const d of shown){
  const item=document.createElement('div');item.className='dock-tab'+(d===top?' active':'');
  const b=document.createElement('button');b.type='button';b.textContent=titleOf(d);b.onclick=()=>front(d);
  const x=document.createElement('button');x.type='button';x.className='dock-tab-close';x.textContent='×';x.setAttribute('aria-label','关闭'+titleOf(d));x.onclick=()=>d.close();
  item.append(b,x);s.append(item);
 }
 requestAnimationFrame(()=>window.dispatchEvent(new Event('resize')));
}
function front(d){const i=stack.indexOf(d);if(i>=0)stack.splice(i,1);stack.push(d);relayout();}
function dock(d){
 if(d.hidden)return;
 d.classList.add('docked');
 if(!d.hasAttribute('tabindex'))d.tabIndex=-1;
 if(!d.open)nativeShow.call(d);
 if(!d.dataset.dockBound){d.dataset.dockBound='1';d.addEventListener('close',relayout);new MutationObserver(()=>{const m=d.classList.contains('is-minimized');if(m!==(d.dataset.dockMin==='1')){d.dataset.dockMin=m?'1':'';if(m)relayout();else front(d);}}).observe(d,{attributes:true,attributeFilter:['class']});}
 front(d);
 setTimeout(()=>{if(d.open&&!d.contains(document.activeElement))(d.querySelector('[autofocus]')||d).focus({preventScroll:true});},0);
}
proto.showModal=function(){if(isDocked(this)){dock(this);return;}return nativeModal.call(this);};
proto.show=function(){if(isDocked(this)){dock(this);return;}return nativeShow.call(this);};
document.addEventListener('keydown',e=>{
 if(e.key!=='Escape')return;
 const top=stack[stack.length-1];
 if(top&&top.open&&top.contains(document.activeElement)){e.preventDefault();e.stopPropagation();top.close();}
},true);
function settle(){
 const t=document.getElementById('toast'),h=document.querySelector('.topbar .project-heading');
 if(t&&h&&t.previousElementSibling!==h)h.after(t);
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',settle);else settle();
