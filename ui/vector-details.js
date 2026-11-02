/** Path editing keeps the imported figure's painter order and has a local undo stack. */
import {sanitizedSvg,usesTextAppearance} from './canvas-editor.js';
const NS='http://www.w3.org/2000/svg';
const clone=x=>Array.isArray(x)?x.map(clone):x&&typeof x==='object'?Object.fromEntries(Object.entries(x).map(([k,v])=>[k,clone(v)])):x;
const node=(tag,attrs={})=>{const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);return n;};
export function vectorEditOperations(objects,updated){
 const result=[];
 for(const o of objects){const svg=updated.get(o.id);if(svg&&svg!==o.asset_snapshot?.svg)result.push({op:'update',id:o.id,changes:{asset_snapshot:{...clone(o.asset_snapshot),svg}}});}
 return result;
}
export function pathTranslation(before,dx,dy){
 if(!Number.isFinite(dx)||!Number.isFinite(dy))throw Error('路径位置必须为有效数值');
 return `translate(${dx} ${dy})${before?' '+before:''}`;
}
export function setupVectorDetails({state,editor,flush,toast}){
 const openButton=document.createElement('button');openButton.type='button';openButton.className='tool text-tool';openButton.id='edit-vector-details';openButton.textContent='矢量细节';openButton.hidden=true;
 document.getElementById('open-annotations').before(openButton);
 const dialog=document.createElement('dialog');dialog.className='vector-detail-dialog';dialog.setAttribute('aria-labelledby','vector-detail-title');
 dialog.innerHTML=`<header class="dialog-heading"><div><h2 id="vector-detail-title">编辑矢量细节</h2><p>点选路径，拖动或改色。按住 Shift 多选；滚轮缩放，空格或中键平移。</p></div><button type="button" class="icon-button" data-vector-close aria-label="关闭矢量细节">×</button></header>
 <div class="vector-detail-tools"><button type="button" data-vector-undo>撤销</button><button type="button" data-vector-redo>重做</button><button type="button" data-vector-fit>适合窗口</button><label>快速选择路径<input type="search" placeholder="输入路径编号" data-vector-search></label><span data-vector-count></span></div>
 <div class="vector-detail-layout"><div class="vector-detail-viewport" tabindex="0" aria-label="矢量细节画布"></div><aside><h3>所选路径</h3><p data-vector-selection>在图中点击一个轮廓或颜色区域。</p><div class="vector-detail-fields"><label>填充颜色<input type="color" data-vector-fill disabled></label><label>轮廓颜色<input type="color" data-vector-stroke disabled></label><label>水平移动 · mm<input type="number" step="0.1" value="0" data-vector-dx disabled></label><label>垂直移动 · mm<input type="number" step="0.1" value="0" data-vector-dy disabled></label></div><button type="button" data-vector-delete disabled>删除所选路径</button><p class="muted small">这里修改插画和原图箭头的路径。文字在主画布中直接点选修改；箭头的原始轮廓会保留。</p><p role="status" data-vector-status></p></aside></div>
 <div class="vector-detail-discard" hidden>有尚未应用的细节修改。<button type="button" data-vector-discard>放弃并关闭</button><button type="button" data-vector-continue>继续编辑</button></div>
 <footer class="dialog-actions"><span data-vector-save-status>修改仅在应用后写入图版，可在主画布撤销。</span><button type="button" class="button" data-vector-close>取消</button><button type="button" class="button primary" data-vector-apply disabled>应用并保存</button></footer>`;
 document.body.append(dialog);
 const $=s=>dialog.querySelector(s),viewport=$('.vector-detail-viewport'),selected=new Set();
 let source=[],roots=new Map(),serialized=new Map(),paths=[],svg=null,overlay=null,undo=[],redo=[],gesture=null,space=false,baseJob=null,baseRevision=0,baseSnapshots=new Map(),initial=new Map(),zoom=1,view=null,dirty=false,loading=false,loadEpoch=0;
 const paint=()=>new Promise(resolve=>requestAnimationFrame(resolve));
 const serialize=()=>new Map([...roots].map(([id,root])=>{if(!serialized.has(id))serialized.set(id,new XMLSerializer().serializeToString(root));return [id,serialized.get(id)];}));
 const changed=()=>vectorEditOperations(source,serialize()).length>0;
 const frame=()=>{view={x:0,y:0,w:editor.scene.canvas.width_mm,h:editor.scene.canvas.height_mm};svg.setAttribute('viewBox',`0 0 ${view.w} ${view.h}`);zoom=1;};
 function refresh(){
  dirty=changed();$('[data-vector-apply]').disabled=!dirty;$('[data-vector-undo]').disabled=!undo.length;$('[data-vector-redo]').disabled=!redo.length;
  $('[data-vector-save-status]').textContent=dirty?'有尚未应用的修改；应用后可在主画布撤销。':'修改仅在应用后写入图版，可在主画布撤销。';
  const entries=[...selected],one=entries.length===1?entries[0]:null;
  $('[data-vector-selection]').textContent=entries.length?`已选 ${entries.length} 条路径${one?' · #'+(paths.indexOf(one)+1):''}`:'在图中点击一个轮廓或颜色区域。';
  for(const key of ['fill','stroke','dx','dy'])$('[data-vector-'+key+']').disabled=!entries.length;
  for(const key of ['fill','stroke']){const color=one?.element.getAttribute(key);$('[data-vector-'+key+']').value=/^#[\da-f]{6}$/i.test(color||'')?color:'#326c82';}
  $('[data-vector-delete]').disabled=!entries.length;
  dialog.querySelectorAll('[data-vector-action],[data-vector-move]').forEach(b=>b.disabled=!entries.length);
  drawSelection();
 }
 function drawSelection(){
  overlay?.replaceChildren();
  for(const item of selected){if(!item.display.isConnected)continue;const box=item.display.getBBox(),m=svg.getScreenCTM().inverse().multiply(item.display.getScreenCTM());
   const p=[new DOMPoint(box.x,box.y),new DOMPoint(box.x+box.width,box.y),new DOMPoint(box.x+box.width,box.y+box.height),new DOMPoint(box.x,box.y+box.height)].map(p=>p.matrixTransform(m));
   overlay.append(node('polygon',{points:p.map(p=>`${p.x},${p.y}`).join(' '),fill:'none',stroke:'#1e83bc','stroke-width':1.5,'vector-effect':'non-scaling-stroke','pointer-events':'none'}));
  }
 }
 async function draw(progressive=false){
  svg=node('svg',{viewBox:`${view.x} ${view.y} ${view.w} ${view.h}`,role:'img','aria-label':'原图矢量路径'});paths=[];svg.append(node('rect',{x:0,y:0,width:editor.scene.canvas.width_mm,height:editor.scene.canvas.height_mm,fill:'#fff'}));
  let drawn=0;const epoch=loadEpoch;
  if(progressive)viewport.replaceChildren(svg);
  for(const object of source){if(!object.visible)continue;const root=roots.get(object.id),box=root.getAttribute('viewBox').split(/[ ,]+/).map(Number);
   const g=node('g',{transform:`rotate(${object.rotation||0} ${object.x+object.w/2} ${object.y+object.h/2}) translate(${object.x} ${object.y}) scale(${object.w/box[2]} ${object.h/box[3]}) translate(${-box[0]} ${-box[1]})`});
   const copyRoot=root.cloneNode(true);for(const child of [...copyRoot.children])g.append(child);svg.append(g);
   const original=[...root.querySelectorAll('path,rect,circle,ellipse,line,polyline,polygon')],display=[...g.querySelectorAll('path,rect,circle,ellipse,line,polyline,polygon')];
   original.forEach((element,i)=>{const item={owner:object.id,element,display:display[i],index:paths.length};item.display.dataset.vectorIndex=String(paths.length);item.display.style.cursor='move';paths.push(item);});
   if(progressive&&++drawn%16===0){$('[data-vector-status]').textContent=`正在准备 ${drawn} / ${source.length} 个矢量组…`;await paint();if(epoch!==loadEpoch||!dialog.open)return;}
  }
  const current=editor.host.querySelector('svg');for(const label of current?.querySelectorAll('[data-label-for]')||[]){const c=label.cloneNode(true);c.style.pointerEvents='none';svg.append(c);}
  overlay=node('g',{'pointer-events':'none'});svg.append(overlay);viewport.replaceChildren(svg);$('[data-vector-count]').textContent=`${paths.length} 条独立矢量路径`;
 }
 function snapshot(){return serialize();}
 function commit(before){const after=serialize();if([...before].every(([id,text])=>text===after.get(id)))return;undo.push(before);if(undo.length>30)undo.shift();redo=[];refresh();}
 function restore(map){roots=new Map([...map].map(([id,text])=>[id,sanitizedSvg(text)]));serialized=new Map(map);selected.clear();draw();refresh();}
 function edit(change){if(!selected.size)return;const before=snapshot();for(const item of selected){change(item);serialized.delete(item.owner);for(const[k,v]of Object.entries(Object.fromEntries([...item.element.attributes].map(a=>[a.name,a.value]))))item.display.setAttribute(k,v);}commit(before);}
 function moveSelected(dx,dy,origins){
  for(const item of selected){const object=source.find(o=>o.id===item.owner),box=roots.get(item.owner).getAttribute('viewBox').split(/[ ,]+/).map(Number),a=-(object.rotation||0)*Math.PI/180;
   const x=(dx*Math.cos(a)-dy*Math.sin(a))*box[2]/object.w,y=(dx*Math.sin(a)+dy*Math.cos(a))*box[3]/object.h;
   const value=pathTranslation(origins.get(item.index)||'',x,y);item.element.setAttribute('transform',value);item.display.setAttribute('transform',value);serialized.delete(item.owner);
  }drawSelection();
 }
 async function open(){
  if(loading||!editor.scene)return;openButton.disabled=true;
  try{
   if(!await flush())return;source=clone(editor.scene.objects.filter(o=>o.asset_snapshot?.svg&&(!o.text_appearance||usesTextAppearance(o))));if(!source.length)return;
   loading=true;dirty=false;const epoch=++loadEpoch;selected.clear();undo=[];redo=[];baseJob=state.id;baseRevision=state.revision;
   baseSnapshots=new Map(source.map(o=>[o.id,o.asset_snapshot.svg]));roots.clear();serialized.clear();
   view={x:0,y:0,w:editor.scene.canvas.width_mm,h:editor.scene.canvas.height_mm};viewport.replaceChildren(document.createTextNode('正在准备矢量细节…'));
   $('.vector-detail-discard').hidden=true;$('[data-vector-status]').textContent='正在读取矢量组，原图版保持不变。';
   dialog.querySelectorAll('button,input').forEach(b=>{if(!b.hasAttribute('data-vector-close'))b.disabled=true;});dialog.showModal();await paint();
   let count=0;for(const o of source){const root=sanitizedSvg(o.asset_snapshot.svg);roots.set(o.id,root);serialized.set(o.id,new XMLSerializer().serializeToString(root));
    if(++count%16===0){await paint();if(epoch!==loadEpoch||!dialog.open)return;}}
   initial=serialize();source=source.map(o=>({...o,asset_snapshot:{...o.asset_snapshot,svg:initial.get(o.id)}}));
   await draw(true);if(epoch!==loadEpoch||!dialog.open)return;
   loading=false;dialog.querySelectorAll('button,input').forEach(b=>b.disabled=false);refresh();$('[data-vector-status]').textContent='';viewport.focus();
  }finally{openButton.disabled=false;loading=false;}
 }
 openButton.onclick=()=>open().catch(e=>toast(e.message,true));
 function close(){if(dirty){$('.vector-detail-discard').hidden=false;return;}dialog.close();}
 dialog.querySelectorAll('[data-vector-close]').forEach(b=>b.onclick=close);dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
 $('[data-vector-discard]').onclick=()=>dialog.close();$('[data-vector-continue]').onclick=()=>{$('.vector-detail-discard').hidden=true;viewport.focus();};
 $('[data-vector-undo]').onclick=()=>{if(undo.length){redo.push(snapshot());restore(undo.pop());}};
 $('[data-vector-redo]').onclick=()=>{if(redo.length){undo.push(snapshot());restore(redo.pop());}};
 $('[data-vector-fit]').onclick=()=>{frame();drawSelection();};
 for(const field of ['fill','stroke']){
  const input=$('[data-vector-'+field+']'),apply=document.createElement('button');apply.type='button';apply.textContent=field==='fill'?'应用填充':'应用轮廓';apply.dataset.vectorAction=field;input.after(apply);
  apply.onclick=()=>edit(item=>item.element.setAttribute(field,input.value));
 }
 const move=document.createElement('button');move.type='button';move.textContent='移动所选路径';move.dataset.vectorMove='';$('.vector-detail-fields').after(move);
 move.onclick=()=>{if(!selected.size)return;const dx=Number($('[data-vector-dx]').value),dy=Number($('[data-vector-dy]').value);if(!Number.isFinite(dx)||!Number.isFinite(dy))return;
  const before=snapshot(),origins=new Map([...selected].map(item=>[item.index,item.element.getAttribute('transform')||'']));moveSelected(dx,dy,origins);$('[data-vector-dx]').value='0';$('[data-vector-dy]').value='0';commit(before);
 };
 $('[data-vector-delete]').onclick=()=>{if(!selected.size)return;const before=snapshot();for(const item of selected){item.element.remove();item.display.remove();serialized.delete(item.owner);}selected.clear();draw();commit(before);};
 const search=$('[data-vector-search]'),choose=document.createElement('button');choose.type='button';choose.textContent='选择路径';search.closest('label').after(choose);
 function choosePath(){const index=Number(search.value.replace('#',''))-1;if(Number.isInteger(index)&&paths[index]){selected.clear();selected.add(paths[index]);refresh();$('[data-vector-status]').textContent='';}else $('[data-vector-status]').textContent=`请输入 1–${paths.length} 之间的路径编号。`;}
 choose.onclick=choosePath;search.addEventListener('keydown',e=>{if(e.key==='Enter'){e.preventDefault();choosePath();}});
 viewport.onpointerdown=e=>{
  if(loading)return;
  if(e.button!==0&&e.button!==1)return;e.preventDefault();viewport.focus();viewport.setPointerCapture(e.pointerId);
  const point=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
  if(space||e.button===1){gesture={pan:true,point,view:{...view}};return;}
  const index=e.target.closest('[data-vector-index]')?.dataset.vectorIndex,item=index!=null?paths[Number(index)]:null;
  if(!item){selected.clear();refresh();return;}if(e.shiftKey){if(selected.has(item))selected.delete(item);else selected.add(item);}else if(!selected.has(item)){selected.clear();selected.add(item);}
  gesture={point,before:snapshot(),origins:new Map([...selected].map(item=>[item.index,item.element.getAttribute('transform')||'']))};refresh();
 };
 viewport.onpointermove=e=>{if(!gesture)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
  if(gesture.pan){view.x+=gesture.point.x-p.x;view.y+=gesture.point.y-p.y;svg.setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);return;}
  moveSelected(p.x-gesture.point.x,p.y-gesture.point.y,gesture.origins);
 };
 viewport.onpointerup=()=>{if(gesture&&!gesture.pan)commit(gesture.before);gesture=null;};
 viewport.onpointercancel=()=>{if(gesture&&!gesture.pan)restore(gesture.before);gesture=null;};
 viewport.addEventListener('wheel',e=>{e.preventDefault();if(loading)return;const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse()),factor=Math.exp(Math.max(-100,Math.min(100,e.deltaY))*.002);if(zoom/factor<.25||zoom/factor>20)return;zoom/=factor;view={x:p.x-(p.x-view.x)*factor,y:p.y-(p.y-view.y)*factor,w:view.w*factor,h:view.h*factor};svg.setAttribute('viewBox',`${view.x} ${view.y} ${view.w} ${view.h}`);drawSelection();},{passive:false});
 dialog.addEventListener('keydown',e=>{if(e.target.closest('input,textarea'))return;if(e.code==='Space'){e.preventDefault();space=true;}if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();$('[data-vector-delete]').click();}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();(e.shiftKey?$('[data-vector-redo]'):$('[data-vector-undo]')).click();}if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();$('[data-vector-redo]').click();}e.stopPropagation();});
 dialog.addEventListener('keyup',e=>{if(e.code==='Space')space=false;});window.addEventListener('blur',()=>{space=false;});dialog.addEventListener('close',()=>{loadEpoch++;gesture=null;space=false;roots.clear();serialized.clear();source=[];undo=[];redo=[];baseSnapshots.clear();initial.clear();paths=[];selected.clear();viewport.replaceChildren();svg=null;overlay=null;});
 $('[data-vector-apply]').onclick=async()=>{
  const button=$('[data-vector-apply]');button.disabled=true;
  try{if(state.id!==baseJob||state.revision!==baseRevision)throw Error('图版已更新，请取消此窗口后重新打开矢量细节。');
   for(const o of editor.scene.objects)if(baseSnapshots.has(o.id)&&baseSnapshots.get(o.id)!==o.asset_snapshot?.svg)throw Error('矢量内容已变化，请重新打开细节窗口。');
   const ops=vectorEditOperations(source,serialize());if(!ops.length)return;editor.applyOperations(ops,'编辑矢量细节');
   const saved=await flush();dialog.close();toast(saved?'矢量细节已保存；Ctrl+Z 可撤销。':'细节已放入画布，保存尚未完成，请点击顶部“保存”。',!saved);
  }catch(e){$('[data-vector-status]').textContent=e.message;button.disabled=false;}
 };
 function refreshAvailable(){openButton.hidden=!editor.scene?.objects.some(o=>o.asset_snapshot?.svg&&/^import_/.test(o.asset_id||''));}
 editor.host.addEventListener('editor-document-loaded',refreshAvailable);
 new MutationObserver(refreshAvailable).observe(document.getElementById('document-title')||editor.host,{subtree:true,childList:true});
 return {refresh:refreshAvailable,open};
}
