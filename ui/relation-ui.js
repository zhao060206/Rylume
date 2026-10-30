import {RELATION_DEFINITIONS,relationPreview,legendOperations} from './canvas-editor.js';

/** The same visual vocabulary is used to choose, inspect and explain a link. */
export function relationChoices(editor,{compact=false}={}){
  const box=document.createElement('div');box.className=compact?'relation-choices compact':'relation-choices';
  const selected=()=>editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];
  for(const def of RELATION_DEFINITIONS){
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

export function setupRelations(editor){
  const $=id=>document.getElementById(id),select=$('connection-type');
  const picker=document.createElement('button');picker.className='tool relation-picker';picker.id='relation-picker';
  picker.title='查看符号与含义；选中连线时可直接更改';select.hidden=true;select.after(picker);
  const dialog=document.createElement('dialog');dialog.id='relation-guide';dialog.className='relation-guide';
  const header=document.createElement('div');header.className='dialog-heading';
  const heading=document.createElement('h2');heading.textContent='连线表达什么';
  const close=document.createElement('button');close.className='icon-button';close.textContent='×';close.setAttribute('aria-label','关闭连线含义');close.onclick=()=>dialog.close();header.append(heading,close);
  const intro=document.createElement('p');intro.id='relation-guide-context';intro.className='muted';
  const notes=document.createElement('div');notes.className='relation-notes';
  for(const text of ['实线：直接作用；虚线：间接作用，端点仍表示关系类型。','问号：含义或证据待作者核对，与虚线分别设置。','符号是本软件的图例约定；转换与转运不表示激活。']){const p=document.createElement('p');p.textContent=text;notes.append(p);}
  const option=document.createElement('label');option.className='relation-label-option';const check=document.createElement('input');check.type='checkbox';check.id='relation-labels';
  check.onchange=()=>editor.scene&&editor.applyOperations([{op:'style',changes:{relation_labels:check.checked}}],'显示连线类型文字');
  option.append(check,document.createTextNode('在图中为无自定义文字的连线显示类型名称（随导出保留）'));
  const legend=document.createElement('button');legend.type='button';legend.className='button';legend.textContent='将当前连线图例放入图中';
  legend.onclick=()=>{if(!editor.scene)return;dialog.close();editor.host.dispatchEvent(new CustomEvent('editor-request-legend'));};
  dialog.append(header,intro,relationChoices(editor),notes,option,legend);document.body.append(dialog);
  picker.onclick=()=>{const rs=editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];intro.textContent=rs.length?`选中了 ${rs.length} 条连线，点选类型即可修改。`:'点选类型后，从对象的蓝色连接点拖到另一对象。';check.checked=!!editor.scene?.style.relation_labels;check.disabled=!editor.scene;legend.disabled=!editor.scene;dialog.showModal();};
  function refresh(){
    const rs=editor.scene?.relations.filter(r=>editor.selectedIds.includes(r.id))||[];
    const type=rs.length===1?rs[0].type:editor.relationType||'associates',def=RELATION_DEFINITIONS.find(x=>x.id===type);
    picker.replaceChildren(relationPreview(type),document.createTextNode(def.title+' ▾'));picker.setAttribute('aria-label','连线含义：'+def.title);
    select.value=editor.relationType||'associates';
    for(const b of dialog.querySelectorAll('[data-relation-choice]'))b.setAttribute('aria-pressed',String(b.dataset.relationChoice===type));
  }
  editor.host.addEventListener('editor-relation-change',refresh);refresh();return{refresh};
}
