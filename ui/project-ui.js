/** Projects are durable records, including empty projects, rather than labels. */
export function creationProject(path,state){
 const parent=path.match(/^\/api\/jobs\/([^/]+)\/(revise|redraw|retry|editable-copy)$/);
 if(parent)return {parentId:parent[1],projectId:state.projectData?.documents[parent[1]]??state.activeProject??''};
 if(/^\/api\/(figure-imports\/imp_[a-f0-9]{24}\/accept|personal-templates\/tpl_[a-f0-9]{24}\/use)$/.test(path))return {projectId:state.activeProject||''};
 return ['/api/generate','/api/jobs','/api/scene/blank','/api/scene/example','/api/scene/import'].includes(path)?{projectId:state.activeProject||''}:null;
}
export function projectSections(jobs,data={},query=''){
 const q=query.trim().toLocaleLowerCase(),membership=data.documents||{},orders=data.order||{};
 const sections=[...(data.projects||[]).map(p=>({id:p.id,label:p.title})),{id:'',label:'未归入项目'}];
 return sections.map(section=>{
  const ranks=new Map((orders[section.id]||[]).map((id,i)=>[id,i]));
  const members=jobs.filter(j=>!j.archived&&(membership[j.id]||'')===section.id);
  const matches=members.filter(j=>!q||`${j.title||''} ${section.label}`.toLocaleLowerCase().includes(q));
  matches.sort((a,b)=>(ranks.get(a.id)??Infinity)-(ranks.get(b.id)??Infinity)||(b.created||0)-(a.created||0));
  return {...section,jobs:matches,count:members.length};
 }).filter(section=>!q||section.jobs.length||section.label.toLocaleLowerCase().includes(q));
}

export function setupProjects({state,api,toast,render,getDragId}){
 const $=id=>document.getElementById(id),make=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=text;return n;};
 let data={projects:[],documents:{},order:{}},loading=null,collapsed=new Set(),editId=null,moving=null;
 try{collapsed=new Set(JSON.parse(localStorage.getItem('rylume-project-folds')||'[]'));state.activeProject=localStorage.getItem('rylume-active-project')||'';}catch{state.activeProject='';}
 const context=make('p','sidebar-project-context');context.id='active-project-label';$('create-project').after(context);
 function select(id){state.activeProject=id;try{localStorage.setItem('rylume-active-project',id);}catch{}updateContext();render();}
 function updateContext(){const project=data.projects.find(p=>p.id===state.activeProject);context.hidden=!project;context.textContent=project?'新图保存到：'+project.title:'';context.title=context.textContent;}
 function accept(value){if(Number.isInteger(data.revision)&&value.revision<data.revision)return;data=value;state.projects=data.projects;state.projectData=data;
  if(state.activeProject&&!data.projects.some(p=>p.id===state.activeProject))state.activeProject='';
  for(const job of state.jobs){job.project_id=data.documents[job.id]||'';job.collection=data.projects.find(p=>p.id===job.project_id)?.title||'';}
  updateContext();
  document.dispatchEvent(new Event('projects-changed'));render();
 }
 async function refresh(){if(loading)return loading;loading=api('/api/projects').then(accept).catch(e=>toast(e.message,true)).finally(()=>loading=null);return loading;}
 const dialog=make('dialog','document-dialog project-dialog');dialog.id='project-dialog';
 const title=make('h2','','新建项目'),label=make('label','settings-field','项目名称'),name=make('input');name.maxLength=60;name.id='project-name';name.autocomplete='off';label.append(name);
 const hint=make('p','muted small','项目用来收纳图版。创建后，在此项目中新建或生成的图版会自动归入。');
 const error=make('p','project-error');error.setAttribute('role','alert');error.hidden=true;
 const actions=make('div','dialog-actions'),cancel=make('button','button','取消'),remove=make('button','text-button','移除项目'),save=make('button','button primary','创建项目');
 cancel.type=remove.type=save.type='button';cancel.onclick=()=>dialog.close();actions.append(remove,cancel,save);dialog.append(title,label,hint,error,actions);document.body.append(dialog);
 function open(id=null){editId=id;const p=data.projects.find(p=>p.id===id);title.textContent=p?'管理项目':'新建项目';name.value=p?.title||'';save.textContent=p?'保存名称':'创建项目';remove.hidden=!p;hint.textContent=p?'移除项目只会将其中图版移到“未归入项目”，不会删除图版。':'创建后，在此项目中新建或生成的图版会自动归入。';error.hidden=true;dialog.showModal();name.focus();name.select();}
 async function submit(){if(!name.value.trim()){error.textContent='请填写项目名称';error.hidden=false;name.focus();return;}save.disabled=remove.disabled=true;error.hidden=true;
  try{const value=await api('/api/projects'+(editId?'/'+editId:''),{title:name.value,base_revision:data.revision},editId?'PATCH':'POST');collapsed.delete(value.project.id);accept(value);select(value.project.id);dialog.close();toast(editId?'项目名称已保存':'项目已创建；接下来新建的图版会归入这里');}
  catch(e){error.textContent=e.message;error.hidden=false;if(e.status===409)await refresh();}finally{save.disabled=remove.disabled=false;}}
 save.onclick=submit;name.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();submit();}};
 remove.onclick=async()=>{remove.disabled=save.disabled=true;try{accept(await api('/api/projects/'+editId,{base_revision:data.revision},'DELETE'));dialog.close();toast('项目已移除，图版保留在“未归入项目”');}catch(e){error.textContent=e.message;error.hidden=false;}finally{remove.disabled=save.disabled=false;}};
 $('create-project').onclick=()=>{const grouping=$('navigator-grouping');if(grouping.value!=='collection'){grouping.value='collection';grouping.dispatchEvent(new Event('change'));}open();};
 const moveDialog=make('dialog','document-dialog project-dialog');moveDialog.id='move-project-dialog';const moveTitle=make('h2','','移动到项目'),moveSelect=make('select'),moveLabel=make('label','settings-field','选择项目'),moveError=make('p','project-error'),moveActions=make('div','dialog-actions'),moveCancel=make('button','button','取消'),moveSave=make('button','button primary','移动');moveSelect.id='move-project-select';moveLabel.append(moveSelect);moveError.setAttribute('role','alert');moveCancel.type=moveSave.type='button';moveCancel.onclick=()=>moveDialog.close();moveActions.append(moveCancel,moveSave);moveDialog.append(moveTitle,moveLabel,moveError,moveActions);document.body.append(moveDialog);
 async function move(id,pid,before){accept(await api('/api/projects/'+(pid||'unfiled')+'/documents',{job_ids:[id],...(before?{before_id:before}:{})}));}
 moveSave.onclick=async()=>{moveSave.disabled=true;moveError.textContent='';try{await move(moving,moveSelect.value);moveDialog.close();toast('图版已移动到'+(data.projects.find(p=>p.id===moveSelect.value)?.title||'未归入项目'));}catch(e){moveError.textContent=e.message;}finally{moveSave.disabled=false;}};
 function moveMenu(job){const b=make('button','project-document-menu','⋯');b.type='button';b.title='移动到项目';b.setAttribute('aria-label','移动「'+(job.title||'未命名图版')+'」到项目');b.onclick=()=>{moving=job.id;moveTitle.textContent='移动「'+(job.title||'未命名图版')+'」';moveSelect.replaceChildren();for(const p of [{id:'',title:'未归入项目'},...data.projects]){const option=make('option','',p.title);option.value=p.id;moveSelect.append(option);}moveSelect.value=data.documents[job.id]||'';moveError.textContent='';moveDialog.showModal();moveSelect.focus();};return b;}
 function header(section){const head=make('div','project-heading-row');head.dataset.projectId=section.id;const choose=make('button','project-folder'+(state.activeProject===section.id?' active':'')),caret=make('span','project-caret',collapsed.has(section.id)?'▸':'▾');choose.type='button';choose.setAttribute('aria-expanded',String(!collapsed.has(section.id)));choose.append(caret,make('span','project-name',section.label),make('span','project-count',String(section.count)));choose.onclick=()=>{if(state.activeProject===section.id){collapsed.has(section.id)?collapsed.delete(section.id):collapsed.add(section.id);}else{state.activeProject=section.id;collapsed.delete(section.id);}try{localStorage.setItem('rylume-project-folds',JSON.stringify([...collapsed]));}catch{}select(section.id);};head.append(choose);
  if(section.id){const edit=make('button','project-manage','⋯');edit.type='button';edit.title='管理项目';edit.setAttribute('aria-label','管理项目「'+section.label+'」');edit.onclick=()=>open(section.id);head.append(edit);}
  head.ondragover=e=>{if(!getDragId())return;e.preventDefault();head.classList.add('drag-target');};head.ondragleave=()=>head.classList.remove('drag-target');head.ondrop=async e=>{e.preventDefault();head.classList.remove('drag-target');const id=getDragId();if(!id)return;try{await move(id,section.id);collapsed.delete(section.id);render();toast('已移动到'+section.label);}catch(error){toast(error.message,true);}};return head;
 }
 refresh();return {refresh,open,move,moveMenu,header,sections:query=>projectSections(state.jobs,data,query),isCollapsed:id=>collapsed.has(id),
  signature:()=>JSON.stringify([data.revision,state.activeProject,[...collapsed]]),
  attachNew:async(id,pid=state.activeProject)=>{if(pid)await move(id,pid);},select,
  get data(){return data;}};
}
