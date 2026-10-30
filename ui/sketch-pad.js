/** A small persistent drawing surface; exports the actual user's pixels. */
export function pointOnPaper(event,rect,width,height){return {x:(event.clientX-rect.left)*width/rect.width,y:(event.clientY-rect.top)*height/rect.height};}
export function setupSketchPad({onUse,toast}){
 const $=id=>document.getElementById(id),canvas=$('sketch-pad'),ctx=canvas.getContext('2d');
 let tool='pen',start=null,previous=null,before=null,ink=false,undo=[];
 function clear(){ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height);}
 clear();
 const point=e=>pointOnPaper(e,canvas.getBoundingClientRect(),canvas.width,canvas.height);
 const save=()=>{undo.push({image:ctx.getImageData(0,0,canvas.width,canvas.height),ink});if(undo.length>30)undo.shift();};
 function style(){ctx.strokeStyle='#344a41';ctx.fillStyle='#344a41';ctx.lineWidth=3;ctx.lineCap='round';ctx.lineJoin='round';ctx.font='23px Arial,Microsoft YaHei,sans-serif';}
 document.querySelectorAll('[data-sketch-tool]').forEach(b=>b.onclick=()=>{tool=b.dataset.sketchTool;document.querySelectorAll('[data-sketch-tool]').forEach(x=>x.setAttribute('aria-pressed',String(x===b)));if(tool==='text')$('sketch-pad-label').focus();});
 canvas.addEventListener('pointerdown',e=>{if(e.button!==0)return;e.preventDefault();canvas.setPointerCapture(e.pointerId);save();start=point(e);previous=start;before=ctx.getImageData(0,0,canvas.width,canvas.height);style();
  if(tool==='text'){const label=$('sketch-pad-label').value.trim();if(!label){undo.pop();start=null;return toast('先输入名称，再点击纸面放置');}ctx.fillText(label,start.x,start.y);ink=true;start=null;}
 });
 canvas.addEventListener('pointermove',e=>{if(!start)return;const p=point(e);style();
  if(tool==='pen'){ctx.beginPath();ctx.moveTo(previous.x,previous.y);ctx.lineTo(p.x,p.y);ctx.stroke();previous=p;}
  else{ctx.putImageData(before,0,0);style();ctx.beginPath();if(tool==='rect')ctx.rect(start.x,start.y,p.x-start.x,p.y-start.y);
   else if(tool==='ellipse')ctx.ellipse((start.x+p.x)/2,(start.y+p.y)/2,Math.abs(p.x-start.x)/2,Math.abs(p.y-start.y)/2,0,0,Math.PI*2);
   else if(tool==='arrow'){ctx.moveTo(start.x,start.y);ctx.lineTo(p.x,p.y);const a=Math.atan2(p.y-start.y,p.x-start.x);ctx.moveTo(p.x-14*Math.cos(a-.45),p.y-14*Math.sin(a-.45));ctx.lineTo(p.x,p.y);ctx.lineTo(p.x-14*Math.cos(a+.45),p.y-14*Math.sin(a+.45));}ctx.stroke();}
  ink=true;
 });
 const finish=()=>{start=null;before=null;};canvas.addEventListener('pointerup',finish);canvas.addEventListener('lostpointercapture',finish);
 canvas.addEventListener('pointercancel',()=>{if(before)ctx.putImageData(before,0,0);undo.pop();finish();});
 $('sketch-pad-undo').onclick=()=>{const last=undo.pop();if(last){ctx.putImageData(last.image,0,0);ink=last.ink;}};
 $('sketch-pad-clear').onclick=()=>{if(!ink)return;save();clear();ink=false;};
 $('use-drawn-sketch').onclick=async()=>{if(!ink)return toast('先画出轮廓，并为对象写上名称');const button=$('use-drawn-sketch');button.disabled=true;try{await onUse(canvas.toDataURL('image/png'));$('sketch-pad-dialog').close();}catch(e){toast(e.message,true);}finally{button.disabled=false;}};
 return {open(){ $('sketch-pad-dialog').showModal();}};
}
