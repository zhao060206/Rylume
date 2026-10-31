import {RELATION_DEFINITIONS,relationPreview,legendOperations} from './canvas-editor.js';

/** The same visual vocabulary is used to choose, inspect and explain a link. */
export function relationChoices(editor,{compact=false,types=null}={}){
  const box=document.createElement('div');box.className=compact?'relation-choices compact':'relation-choices';
  const selected=()=>editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];
  for(const def of RELATION_DEFINITIONS.filter(d=>!types||types.includes(d.id))){
    const button=document.createElement('button');button.type='button';button.className='relation-choice';
    button.dataset.relationChoice=def.id;button.setAttribute('aria-label',def.title+'：'+def.description);
    button.setAttribute('aria-pressed',String(selected().length>0&&selected().every(r=>r.type===def.id)));
    button.append(relationPreview(def.id));
    const body=document.createElement('span'),title=document.createElement('strong'),description=document.createElement('small');
    title.textContent=def.title;description.textContent=def.description;body.append(title,description);button.append(body);
    button.onclick=()=>{
      const relations=selected();
      if(relations.length)editor.applyOperations(relations.map(r=>({op:'update_relation',id:r.id,changes:{type:def.id,...(def.id==='associates'?{uncertain:true}:{})}})),'更改连线含义');
      editor.relationType=def.id;
      editor.host.dispatchEvent(new CustomEvent('editor-relation-change'));
      button.closest('dialog')?.close();
    };
    box.append(button);
  }
  return box;
}

export function pendingRelationDefinitions(scene,unsaved=[]){
  const ids=new Set(unsaved);return (scene?.relations||[]).filter(r=>r.uncertain||ids.has(r.id));
}
export function confirmedDefinition(relation,type,label){
  if(!RELATION_DEFINITIONS.some(d=>d.id===type))throw Error('请选择有效的连线含义');
  return {op:'update_relation',id:relation.id,changes:{type,label:String(label).trim().slice(0,300),uncertain:false}};
}
export function setupRelations(editor,{flush=async()=>true,getDocumentId=()=>editor.scene}={}){
  const $=id=>document.getElementById(id),select=$('connection-type');
  const picker=document.createElement('button');picker.className='tool relation-picker';picker.id='relation-picker';
  picker.title='查看符号与含义；选中连线时可直接更改';select.hidden=true;$('relation-context').append(picker);
  const inline=relationChoices(editor,{types:['sequence','activates','inhibits']});inline.classList.add('inline-relation-choices');inline.setAttribute('role','group');inline.setAttribute('aria-label','常用连线含义');$('relation-context').prepend(inline);
  const dialog=document.createElement('dialog');dialog.id='relation-guide';dialog.className='relation-guide';
  const header=document.createElement('div');header.className='dialog-heading';
  const heading=document.createElement('h2');heading.textContent='连线表达什么';
  const close=document.createElement('button');close.className='icon-button';close.textContent='×';close.setAttribute('aria-label','关闭连线含义');close.onclick=()=>dialog.close();header.append(heading,close);
  const intro=document.createElement('p');intro.id='relation-guide-context';intro.className='muted';
  const notes=document.createElement('div');notes.className='relation-notes';
  for(const text of ['实线：直接作用；虚线：间接作用，端点仍表示关系类型。','顶部“连线待核对”集中提醒含义或证据待确认的连线，不显示在导出图中。','符号是本软件的图例约定；转换与转运不表示激活。']){const p=document.createElement('p');p.textContent=text;notes.append(p);}
  const option=document.createElement('label');option.className='relation-label-option';const check=document.createElement('input');check.type='checkbox';check.id='relation-labels';
  check.onchange=()=>editor.scene&&editor.applyOperations([{op:'style',changes:{relation_labels:check.checked}}],'显示连线类型文字');
  option.append(check,document.createTextNode('在图中为无自定义文字的连线显示类型名称（随导出保留）'));
  const legend=document.createElement('button');legend.type='button';legend.className='button';legend.textContent='将当前连线图例放入图中';
  legend.onclick=()=>{if(!editor.scene)return;dialog.close();editor.host.dispatchEvent(new CustomEvent('editor-request-legend'));};
  dialog.append(header,intro,relationChoices(editor),notes,option,legend);document.body.append(dialog);
  picker.onclick=()=>{const rs=editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];intro.textContent=rs.length?`选中了 ${rs.length} 条连线，点选类型即可修改。`:'先选这条线的含义，再依次点击图中的起点和终点。';check.checked=!!editor.scene?.style.relation_labels;check.disabled=!editor.scene;legend.disabled=!editor.scene;dialog.showModal();};
  const pendingButton=document.createElement('button');pendingButton.type='button';pendingButton.className='pending-relations';pendingButton.id='pending-relation-definitions';pendingButton.hidden=true;
  document.querySelector('.topbar').insertBefore(pendingButton,$('toggle-documents'));
  const definitions=document.createElement('dialog');definitions.className='relation-definitions';definitions.setAttribute('aria-labelledby','relation-definitions-title');
  const definitionHead=document.createElement('div');definitionHead.className='dialog-heading';
  const definitionTitle=document.createElement('h2');definitionTitle.id='relation-definitions-title';definitionTitle.textContent='核对连线含义';
  const definitionClose=document.createElement('button');definitionClose.className='icon-button';definitionClose.textContent='×';definitionClose.setAttribute('aria-label','关闭连线定义');definitionClose.onclick=()=>definitions.close();definitionHead.append(definitionTitle,definitionClose);
  const explanation=document.createElement('p');explanation.className='muted';explanation.textContent='核对方向、类型和科学依据，再保存定义。此提醒不进入导出图片；也可以暂时保留待核对。';
  const rows=document.createElement('div');rows.className='relation-definition-list';definitions.append(definitionHead,explanation,rows);document.body.append(definitions);
  const unsaved=new Map();let openedDocument=null;
  const unsavedIds=()=>unsaved.get(getDocumentId())||new Set();
  function renderDefinitions(){
    rows.replaceChildren();const scene=editor.scene,key=getDocumentId(),pending=pendingRelationDefinitions(scene,unsavedIds());
    if(!pending.length){const done=document.createElement('p');done.className='relation-definitions-done';done.textContent='这些连线的定义已保存。';rows.append(done);return;}
    for(const r of pending){
      const card=document.createElement('section');card.className='relation-definition-card';
      const names=document.createElement('h3'),objects=scene.objects;names.textContent=(objects.find(o=>o.id===r.source)?.label||r.source)+' → '+(objects.find(o=>o.id===r.target)?.label||r.target);
      const typeLabel=document.createElement('label');typeLabel.textContent='连线含义';const type=document.createElement('select');type.setAttribute('aria-label',names.textContent+' 的连线含义');
      for(const d of RELATION_DEFINITIONS){const option=document.createElement('option');option.value=d.id;option.textContent=d.title;type.append(option);}type.value=r.type;
      const description=document.createElement('p');description.className='muted';const updateDescription=()=>description.textContent=RELATION_DEFINITIONS.find(d=>d.id===type.value).description;type.onchange=updateDescription;updateDescription();typeLabel.append(type);
      const textLabel=document.createElement('label');textLabel.textContent='线上文字（可选）';const text=document.createElement('input');text.type='text';text.maxLength=300;text.value=r.label||'';text.setAttribute('aria-label',names.textContent+' 的线上文字');textLabel.append(text);
      const actions=document.createElement('div');actions.className='relation-definition-actions';const locate=document.createElement('button');locate.className='button';locate.textContent='定位连线';locate.onclick=()=>{if(getDocumentId()!==key)return;definitions.close();editor.setTool('select');editor.setSelection([r.id]);editor.revealSelection();};
      const save=document.createElement('button');save.className='button primary';save.textContent='保存定义';const message=document.createElement('p');message.className='relation-definition-status';message.setAttribute('role','status');
      save.onclick=async()=>{
        if(getDocumentId()!==key||!editor.scene?.relations.some(x=>x.id===r.id))return;
        save.disabled=true;type.disabled=true;text.disabled=true;message.textContent='正在保存定义…';
        const ids=unsaved.get(key)||new Set();ids.add(r.id);unsaved.set(key,ids);
        try{editor.applyOperations([confirmedDefinition(r,type.value,text.value)],'核对并保存连线定义');const ok=await flush();if(getDocumentId()!==key)return;
          if(!ok){message.textContent='保存未完成，修改已保留。请重试保存。';return;}
          ids.delete(r.id);if(!ids.size)unsaved.delete(key);message.textContent='定义已保存';refresh();renderDefinitions();
        }catch(e){if(getDocumentId()===key)message.textContent='保存未完成：'+e.message;}
        finally{save.disabled=false;type.disabled=false;text.disabled=false;refresh();}
      };
      actions.append(locate,save);card.append(names,typeLabel,description,textLabel,actions,message);rows.append(card);
    }
  }
  pendingButton.onclick=()=>{openedDocument=getDocumentId();renderDefinitions();definitions.showModal();};
  function refresh(){
    const pending=pendingRelationDefinitions(editor.scene,unsavedIds());pendingButton.hidden=!pending.length;pendingButton.textContent=pending.length+' 条连线待核对';pendingButton.title='核对类型与说明，然后保存定义（不会显示在导出图中）';
    if(definitions.open&&openedDocument!==getDocumentId())definitions.close();
    const rs=editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];
    const type=rs.length===1?rs[0].type:editor.relationType||'associates',def=RELATION_DEFINITIONS.find(x=>x.id===type);
    picker.replaceChildren(relationPreview(type),document.createTextNode(def.title+' ▾'));picker.setAttribute('aria-label','连线含义：'+def.title);
    select.value=editor.relationType||'associates';
    for(const b of document.querySelectorAll('[data-relation-choice]'))b.setAttribute('aria-pressed',String(b.dataset.relationChoice===type));
  }
  editor.host.addEventListener('editor-relation-change',refresh);refresh();return{refresh};
}
