/** A known newer release stays reachable until the installed version catches up. */
export function newerRelease(update){
 const version=value=>/^v?\d+\.\d+\.\d+$/.test(String(value))?String(value).replace(/^v/,'').split('.').map(Number):null;
 const next=version(update?.latest_version),current=version(update?.current_version||'0.0.0');
 if(!next||!current)return false;
 for(let i=0;i<3;i++){if(next[i]!==current[i])return next[i]>current[i];}return false;
}
export function dockLabel(update){
 if(update.state==='downloading')return `正在下载 · ${Math.round(update.progress||0)}%`;
 if(update.state==='validating')return '正在校验更新';
 if(update.state==='ready')return update.can_apply?'重启更新':'下载已完成';
 if(update.state==='installing')return '正在重启';
 return '点击更新';
}
export function setupUpdateDock({openUpdate}){
 const el=(tag,cls,text)=>{const node=document.createElement(tag);node.className=cls;if(text!=null)node.textContent=text;return node;};
 const dock=el('div','update-dock');dock.id='update-dock';dock.hidden=true;
 const button=el('button','update-dock-button');button.id='click-update';button.type='button';
 const icon=el('span','update-dock-icon');icon.setAttribute('aria-hidden','true');icon.innerHTML='<svg class="icon" viewBox="0 0 24 24"><path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/></svg>';
 const copy=el('span','update-dock-copy'),label=el('strong','','点击更新'),version=el('small','');copy.append(label,version);button.append(icon,copy);dock.append(button);
 const preview=el('aside','update-dock-preview');preview.id='update-dock-preview';preview.hidden=true;preview.setAttribute('role','tooltip');
 const heading=el('strong',''),notes=el('pre',''),hint=el('p','','点击下载新版；下载完成后，可保存并重启更新。');preview.append(heading,notes,hint);
 button.setAttribute('aria-describedby',preview.id);
 const footer=document.querySelector('.app-sidebar .sidebar-footer');
 if(footer)footer.prepend(dock);else {dock.classList.add('update-dock-fallback');document.body.append(dock);}
 document.body.append(preview);
 let known=null,hideTimer=null,suppressed=false,cached=null;
 // Cache display metadata only. Downloads still require a fresh backend release.
 const cacheKey='rylume-known-update-preview';
 try{const value=JSON.parse(localStorage.getItem(cacheKey)||'null');if(typeof value?.latest_version==='string'&&typeof value?.notes==='string')cached=value;}catch{}
 function hide(){clearTimeout(hideTimer);preview.hidden=true;}
 function position(){const rect=button.getBoundingClientRect(),width=Math.min(430,innerWidth-24);
  preview.style.width=width+'px';preview.style.left=Math.max(12,Math.min(rect.right+12,innerWidth-width-12))+'px';
  preview.style.bottom=Math.max(12,Math.min(innerHeight-rect.bottom,innerHeight-120))+'px';
 }
 function show(){clearTimeout(hideTimer);if(dock.hidden||suppressed)return;position();preview.hidden=false;}
 function leave(){hideTimer=setTimeout(()=>{if(!dock.contains(document.activeElement))hide();},180);}
 button.addEventListener('mouseenter',()=>{suppressed=false;show();});
 button.addEventListener('mouseleave',leave);button.addEventListener('focus',()=>{suppressed=false;show();});button.addEventListener('blur',leave);
 preview.addEventListener('mouseenter',()=>{clearTimeout(hideTimer);});preview.addEventListener('mouseleave',leave);
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!preview.hidden){suppressed=true;hide();}});
 window.addEventListener('resize',()=>{if(!preview.hidden)position();});
 button.onclick=()=>{hide();if(known)openUpdate(known);};
 return {render(update){
  if(cached&&update?.current_version){
   if(newerRelease({...cached,current_version:update.current_version}))known={latest_version:cached.latest_version,notes:cached.notes,current_version:update.current_version,state:'cached'};
   cached=null;
  }
  if(newerRelease(update)){known={...update,notes:update.notes||(known?.latest_version===update.latest_version?known.notes:'')};}
  else if(update?.state==='up_to_date'||(update?.latest_version&&!newerRelease(update))){known=null;}
  if(known&&update?.current_version&&!newerRelease({...known,current_version:update.current_version}))known=null;
  try{if(known)localStorage.setItem(cacheKey,JSON.stringify({latest_version:known.latest_version,notes:known.notes||''}));else localStorage.removeItem(cacheKey);}catch{}
  // A failed/transient recheck must not remove the last known available release.
  dock.hidden=!known;if(!known){hide();return;}
  label.textContent=dockLabel(known);version.textContent='v'+known.latest_version.replace(/^v/,'');
  button.disabled=known.state==='installing';button.setAttribute('aria-label',`${label.textContent}，新版本 ${version.textContent}`);
  heading.textContent=`${version.textContent} · 本次更新日志`;
  notes.textContent=known.notes?.trim()||'发布者暂未提供更新日志。点击可查看更新详情。';
  hint.textContent=known.state==='cached'?'已保留上次发现的新版。点击先检查最新版本，再下载更新。':known.state==='ready'?'新版已通过校验。点击可保存图版并重启更新。':'点击下载新版；下载完成后，可保存并重启更新。';
 }};
}
