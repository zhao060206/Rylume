import {setupFloatingWindows,showFloatingWindow} from './floating-windows.js';

export function setupReleaseNotes({api,toast}){
 const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 const dialog=el('dialog','release-history-dialog');dialog.id='release-history-dialog';dialog.setAttribute('aria-labelledby','release-history-title');
 const head=el('div','dialog-heading'),title=el('h2','','更新日志');title.id='release-history-title';
 const close=el('button','icon-button','×');close.setAttribute('aria-label','关闭更新日志');close.onclick=()=>dialog.close();head.append(title,close);
 const intro=el('p','muted','每次更新的新增、改进与修复都保留在这里，可离线查看。'),body=el('div','release-history');dialog.append(head,intro,body);document.body.append(dialog);setupFloatingWindows(dialog);
 const entry=el('button','','更新日志');entry.id='open-release-notes';document.getElementById('settings-menu-items').append(entry);
 let data=null;
 const notice=el('aside','whats-new-corner');notice.hidden=true;notice.setAttribute('aria-label','本次更新说明');
 const dismiss=el('button','icon-button','×');dismiss.setAttribute('aria-label','知道了，关闭更新说明');
 const label=el('strong'),copy=el('p'),read=el('button','text-button','查看更新日志');notice.append(dismiss,label,copy,read);document.body.append(notice);
 async function acknowledge(){if(!data)return;try{await api('/api/release-notes/acknowledge',{version:data.current_version});notice.hidden=true;}catch(e){toast(e.message,true);}}
 async function open(){try{data=await api('/api/release-notes');body.replaceChildren();for(const release of data.releases){const section=el('section','release-entry');section.append(el('h3','',`v${release.version}`),el('time','',release.date));const list=el('ul');for(const item of release.items)list.append(el('li','',item));section.append(list);body.append(section);}showFloatingWindow(dialog);await acknowledge();}catch(e){toast(e.message,true);}}
 entry.onclick=read.onclick=open;dismiss.onclick=acknowledge;
 return {open,async ready(){try{data=await api('/api/release-notes');const current=data.releases.find(r=>r.version===data.current_version);if(data.unread&&current){label.textContent=`Rylume ${data.current_version} · 本次更新`;copy.textContent=current.items.slice(0,2).map(s=>s.split('：')[0]).join(' · ');notice.hidden=false;}}catch{}}};
}
