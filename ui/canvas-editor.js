/** Native SVG object editor. Coordinates are millimetres; exports use no overlays. */
const NS = 'http://www.w3.org/2000/svg', PXMM = 96 / 25.4;
const copy = x => JSON.parse(JSON.stringify(x));
const node = (tag, attrs = {}, text) => {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text != null) n.textContent = text;
  return n;
};
const isInput = e => e.target.closest('input,textarea,select,[contenteditable=true],dialog');
const uid = prefix => prefix + '_' + crypto.randomUUID().replaceAll('-', '').slice(0, 12);
export const RELATION_DEFINITIONS = [{"id": "activates", "title": "激活", "english": "Activation", "symbol": "open-arrow", "description": "起点促进终点的活性或作用。", "example": "激酶 A 促进 B 的活性"}, {"id": "inhibits", "title": "抑制", "english": "Inhibition", "symbol": "bar", "description": "横杠所在的一端受到抑制。", "example": "抑制剂 A 阻断 B"}, {"id": "binds", "title": "结合", "english": "Binding", "symbol": "paired-circles", "description": "两端圆点表示结合，不表示作用方向。", "example": "配体与受体结合"}, {"id": "converts", "title": "转换", "english": "Conversion", "symbol": "filled-arrow", "description": "起点转变为终点；实心箭头指向产物。", "example": "底物 A 转变为产物 B"}, {"id": "transports", "title": "转运", "english": "Transport", "symbol": "double-chevron", "description": "双箭头表示对象在位置或区室间移动。", "example": "蛋白从胞质进入细胞核"}, {"id": "sequence", "title": "流程顺序", "english": "Next step", "symbol": "step-arrow", "description": "箭头仅表示步骤的先后，不代表生物学激活。", "example": "提取样本后进行测量"}, {"id": "associates", "title": "普通关联", "english": "Association", "symbol": "plain-line", "description": "无箭头连线，仅表示相关或流程衔接。", "example": "未明确机制时使用，需核对含义"}];
export function relationLabel(scene,r){return r.label||(scene.style?.relation_labels?RELATION_DEFINITIONS.find(x=>x.id===r.type)?.english||'':'');}
export function relationParts(kind,start,end,control,color,strokePt=1.05,indirect=false,anchored={}){
  let x1=start.x,y1=start.y,x2=end.x,y2=end.y;const cx=control.x,cy=control.y;
  let vx=cx-x1,vy=cy-y1,len=Math.hypot(vx,vy)||1,gap=anchored.start?0:1.2;x1+=vx/len*gap;y1+=vy/len*gap;
  vx=x2-cx;vy=y2-cy;len=Math.hypot(vx,vy)||1;const ux=vx/len,uy=vy/len;gap=anchored.end?0:1.2;x2-=ux*gap;y2-=uy*gap;
  const sw=strokePt*25.4/72,common={fill:'none',stroke:color,'stroke-width':sw,'stroke-linecap':'round','stroke-linejoin':'round'};
  let path=`M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
  if(indirect){const points=Array.from({length:121},(_,i)=>{const t=i/120,u=1-t;return{x:u*u*x1+2*u*t*cx+t*t*x2,y:u*u*y1+2*u*t*cy+t*t*y2};});let distance=0;const segments=[];
    for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];if(distance%2.5<1.5)segments.push(`M ${a.x} ${a.y} L ${b.x} ${b.y}`);distance+=Math.hypot(a.x-b.x,a.y-b.y);}path=segments.join(' ');}
  const parts=[['path',{...common,d:path,'data-line-body':'true','data-indirect':String(!!indirect)}]];
  const at=(back,side=0)=>`${x2-ux*back-uy*side} ${y2-uy*back+ux*side}`;
  const attrs={...common,'data-endpoint':RELATION_DEFINITIONS.find(x=>x.id===kind)?.symbol};
  if(kind==='inhibits')parts.push(['path',{...attrs,d:`M ${at(0,2.8)} L ${at(0,-2.8)}`,'stroke-width':Math.max(sw,.58)}]);
  else if(kind==='activates')parts.push(['path',{...attrs,d:`M ${at(3.0,1.45)} L ${at(0)} L ${at(3.0,-1.45)}`}]);
  else if(kind==='sequence')parts.push(['path',{...attrs,d:`M ${at(2.2,1.1)} L ${at(0)} L ${at(2.2,-1.1)} Z`,fill:color}]);
  else if(kind==='converts')parts.push(['path',{...attrs,d:`M ${at(3.2,1.5)} L ${at(0)} L ${at(3.2,-1.5)} Z`,fill:color}]);
  else if(kind==='transports')parts.push(['path',{...attrs,d:[0,2.5].map(b=>`M ${at(b+2.4,1.25)} L ${at(b)} L ${at(b+2.4,-1.25)}`).join(' ')}]);
  else if(kind==='binds')for(const [x,y] of [[x1,y1],[x2,y2]])parts.push(['circle',{...attrs,cx:x,cy:y,r:1.15,fill:'#FFFFFF'}]);
  return parts;
}
export function relationPreview(type){
  const svg=node('svg',{viewBox:'0 0 36 10',width:90,height:26,'aria-hidden':'true'});
  for(const[tag,attrs]of relationParts(type,{x:2,y:5},{x:34,y:5},{x:18,y:5},'#334A58'))svg.append(node(tag,attrs));return svg;
}
export function legendOperations(scene,idFactory=()=>uid('legend'),{expand=false}={}){
  const definitions=RELATION_DEFINITIONS.filter(t=>scene.relations.some(r=>r.type===t.id)&&!scene.objects.some(o=>o.state==='legend_'+t.id));
  if(!definitions.length)return [];
  let cols=Math.max(1,Math.min(definitions.length,Math.floor((scene.canvas.width_mm-12)/38))),rows=Math.ceil(definitions.length/cols),x=6;
  const bottom=Math.max(0,...scene.objects.filter(o=>o.visible).map(o=>o.y+o.h+((o.state||'').startsWith('flow_')?0:7)));
  const requiredY=Math.max(8,bottom+6);let y=expand?requiredY:Math.max(6,Math.min(requiredY,scene.canvas.height_mm-rows*10-6));
  if(!expand){
    const occupied=scene.objects.filter(o=>o.visible),placements=[];
    for(let columns=1;columns<=cols;columns++){const lines=Math.ceil(definitions.length/columns),w=columns*38,h=lines*10;
      for(let py=6;py+h<=scene.canvas.height_mm-4;py+=4)for(let px=6;px+w<=scene.canvas.width_mm-4;px+=4){
        const overlap=occupied.reduce((sum,o)=>sum+Math.max(0,Math.min(px+w,o.x+o.w+3)-Math.max(px,o.x-3))*Math.max(0,Math.min(py+h,o.y+o.h+9)-Math.max(py,o.y-3)),0);
        placements.push({x:px,y:py,cols:columns,rows:lines,score:overlap*10000+(scene.canvas.height_mm-py-h)*2+(scene.canvas.width_mm-px-w)+lines*2});
      }
    }
    placements.sort((a,b)=>a.score-b.score);if(placements[0])({x,y,cols,rows}=placements[0]);
  }
  const height=expand?Math.max(scene.canvas.height_mm,y+rows*10+6):scene.canvas.height_mm;
  const group=idFactory(),ops=[];
  if(height>scene.canvas.height_mm)ops.push({op:'canvas',width_mm:scene.canvas.width_mm,height_mm:height,reflow:false});
  definitions.forEach((t,i)=>{const id=idFactory();ops.push({op:'add',object:{id,entity_id:id,type:'process',state:'legend_'+t.id,role:'annotation',group_id:group,label:t.english,x:x+(i%cols)*38,y:y+Math.floor(i/cols)*10,w:34,h:7,font_size_pt:7,visible:true,locked:false,evidence:'Legend of the studio notation; not a scientific entity.'}});});
  return ops;
}

export function wheelIntent(e){return e.ctrlKey||e.metaKey?'zoom':e.shiftKey?'horizontal':'pan';}
export function clampView(offset,paper,viewport){
  const axis=(value,size,limit)=>{if(!limit)return value;const gap=limit-size,margin=Math.min(24,limit/4);if(gap>=0)return gap<margin*2?gap/2:Math.max(margin,Math.min(gap-margin,value));return Math.max(gap-margin,Math.min(margin,value));};
  return {x:axis(offset.x,paper.width,viewport.width),y:axis(offset.y,paper.height,viewport.height)};
}

export function resizedObject(old,handle,dx,dy,proportional=false){
  const angle=(old.rotation||0)*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle);
  const lx=c*dx+s*dy,ly=-s*dx+c*dy;
  const hasX=handle.includes('w')||handle.includes('e'),hasY=handle.includes('n')||handle.includes('s');
  const ax=handle.includes('w')?1:0,ay=handle.includes('n')?1:0;
  let w=hasX?Math.max(2,old.w+(ax?-lx:lx)):old.w,h=hasY?Math.max(2,old.h+(ay?-ly:ly)):old.h;
  if(proportional&&hasX&&hasY){const rx=w/old.w,ry=h/old.h;const ratio=Math.max(Math.abs(rx-1)>Math.abs(ry-1)?rx:ry,2/old.w,2/old.h);w=old.w*ratio;h=old.h*ratio;}
  const anchorX=old.x+old.w/2+c*((hasX?ax:.5)-.5)*old.w-s*((hasY?ay:.5)-.5)*old.h;
  const anchorY=old.y+old.h/2+s*((hasX?ax:.5)-.5)*old.w+c*((hasY?ay:.5)-.5)*old.h;
  return {x:anchorX+c*(.5-(hasX?ax:.5))*w-s*(.5-(hasY?ay:.5))*h-w/2,y:anchorY+s*(.5-(hasX?ax:.5))*w+c*(.5-(hasY?ay:.5))*h-h/2,w,h};
}

export function hitObjects(scene,point,includeContext=false){
  return [...scene.objects].reverse().filter(o=>{
    if(!o.visible||(!includeContext&&(o.locked||o.role==='context')))return false;
    const angle=-(o.rotation||0)*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle),dx=point.x-o.x-o.w/2,dy=point.y-o.y-o.h/2;
    return Math.abs(c*dx-s*dy)<=o.w/2&&Math.abs(s*dx+c*dy)<=o.h/2;
  });
}
// Edge positions are proportional to the unrotated bounds, so they survive
// moving, resizing and rotation without depending on pixels or view zoom.
export function boundaryPoint(o,anchor){
  const {side,t}=anchor,cx=o.x+o.w/2,cy=o.y+o.h/2;
  const x=side==='e'?o.x+o.w:side==='w'?o.x:o.x+o.w*t;
  const y=side==='s'?o.y+o.h:side==='n'?o.y:o.y+o.h*t;
  const a=(o.rotation||0)*Math.PI/180;
  return {x:cx+(x-cx)*Math.cos(a)-(y-cy)*Math.sin(a),y:cy+(x-cx)*Math.sin(a)+(y-cy)*Math.cos(a)};
}
export function nearestBoundary(o,point){
  const a=-(o.rotation||0)*Math.PI/180,dx=point.x-o.x-o.w/2,dy=point.y-o.y-o.h/2;
  const x=Math.cos(a)*dx-Math.sin(a)*dy+o.w/2,y=Math.sin(a)*dx+Math.cos(a)*dy+o.h/2;
  const tx=Math.max(0,Math.min(1,x/o.w)),ty=Math.max(0,Math.min(1,y/o.h));
  const choices=[{side:'n',t:tx},{side:'e',t:ty},{side:'s',t:tx},{side:'w',t:ty}];
  choices.sort((a,b)=>{const p=boundaryPoint(o,a),q=boundaryPoint(o,b);return Math.hypot(p.x-point.x,p.y-point.y)-Math.hypot(q.x-point.x,q.y-point.y);});
  return choices[0];
}
// Screen-pixel tolerance gives the same feel at every view scale. Anchors stay
// proportional in the document; helper points exist only in the editor overlay.
export function connectionKeypoints(o){
  const anchors=['n','e','s','w'].map(side=>({side,t:.5,kind:'midpoint'}));
  if(o.type==='process'&&!['flow_decision','flow_terminator','flow_data','flow_document'].includes(o.state)||o.type==='image')
    anchors.push({side:'n',t:0,kind:'corner'},{side:'n',t:1,kind:'corner'},{side:'s',t:1,kind:'corner'},{side:'s',t:0,kind:'corner'});
  return anchors.map(({kind,...anchor})=>({anchor,kind,point:boundaryPoint(o,anchor)}));
}
export function connectionAnchor(o,point,zoom=1,free=false){
  if(!free){
    const tolerance=10/(PXMM*Math.max(.01,zoom));
    const near=connectionKeypoints(o).map(k=>({...k,distance:Math.hypot(k.point.x-point.x,k.point.y-point.y)})).filter(k=>k.distance<=tolerance).sort((a,b)=>a.distance-b.distance)[0];
    if(near)return {anchor:near.anchor,keypoint:near.kind};
  }
  return {anchor:nearestBoundary(o,point)};
}
export function connectionTarget(scene,point,zoom=1,exclude=null,free=false){
  const eligible=o=>o.id!==exclude&&o.visible!==false&&!o.locked&&o.role!=='context';
  const inside=hitObjects(scene,point).find(eligible);
  if(inside)return {object:inside,...connectionAnchor(inside,point,zoom,free)};
  const tolerance=10/(PXMM*zoom);
  const candidates=[...scene.objects].reverse().filter(eligible).map(object=>{
    const picked=connectionAnchor(object,point,zoom,free),p=boundaryPoint(object,picked.anchor);
    return {object,...picked,distance:Math.hypot(p.x-point.x,p.y-point.y)};
  }).filter(c=>c.distance<=tolerance).sort((a,b)=>a.distance-b.distance);
  return candidates[0]||null;
}
let measureContext;
function measureMM(text,fs){
  try{measureContext ||= document.createElement('canvas').getContext('2d');
    measureContext.font=[...text].some(c=>c.charCodeAt(0)>255)?'1000px "Microsoft YaHei"':'1000px Arial';
    return measureContext.measureText(text).width/1000*fs;
  }catch{return [...text].reduce((sum,c)=>sum+(c.charCodeAt(0)>255?1:.53),0)*fs;}
}

export function sanitizedSvg(source) {
  const doc = new DOMParser().parseFromString(source, 'image/svg+xml');
  if (doc.querySelector('parsererror') || doc.documentElement.localName !== 'svg') {
    throw Error('无法解析图版');
  }
  doc.querySelectorAll('script,foreignObject,iframe,style,filter').forEach(n => n.remove());
  for (const n of doc.querySelectorAll('*')) {
    for (const a of [...n.attributes]) {
      if (/^on/i.test(a.name) || ((a.name === 'href' || a.name === 'xlink:href') && !a.value.startsWith('#') && !a.value.startsWith('data:image/'))) {
        n.removeAttribute(a.name);
      }
    }
  }
  return document.importNode(doc.documentElement, true);
}

export function edgeGeometry(scene, r, preview=null) {
  r={...r,label:relationLabel(scene,r)};
  const a = scene.objects.find(o => o.id === r.source), b = scene.objects.find(o => o.id === r.target);
  if (!a || !b) return null;
  const dx = (b.x + b.w / 2) - (a.x + a.w / 2), dy = (b.y + b.h / 2) - (a.y + a.h / 2);
  let sp = r.source_port || 'auto', tp = r.target_port || 'auto';
  if (a.type === 'ligand' && ['receptor', 'receptor_dimer', 'gpcr'].includes(b.type) && dy > 0) {
    if (sp === 'auto') sp = 's';
    if (tp === 'auto') tp = 'n';
  }
  if (sp === 'auto' && tp === 'auto') {
    if (Math.abs(dy) > Math.abs(dx) * 1.15) {
      sp = dy > 0 ? 's' : 'n';
      tp = dy > 0 ? 'n' : 's';
    } else {
      sp = dx >= 0 ? 'e' : 'w';
      tp = dx >= 0 ? 'w' : 'e';
    }
  } else if (sp === 'auto') {
    sp = (Math.abs(dy) > Math.abs(dx) * 1.15) ? (dy > 0 ? 's' : 'n') : (dx >= 0 ? 'e' : 'w');
  } else if (tp === 'auto') {
    tp = (Math.abs(dy) > Math.abs(dx) * 1.15) ? (dy > 0 ? 'n' : 's') : (dx >= 0 ? 'w' : 'e');
  }
  const point = (o, p) => {
    let x = o.x + o.w / 2, y = o.y + o.h / 2;
    if (p === 'e') x = o.x + o.w;
    if (p === 'w') x = o.x;
    if (p === 'n') y = o.y;
    if (p === 's') y = o.y + o.h;
    const angle = (o.rotation || 0) * Math.PI / 180, cx = o.x + o.w / 2, cy = o.y + o.h / 2;
    return {
      x: cx + (x - cx) * Math.cos(angle) - (y - cy) * Math.sin(angle),
      y: cy + (x - cx) * Math.sin(angle) + (y - cy) * Math.cos(angle)
    };
  };
  const start = preview?.start || (r.source_anchor?boundaryPoint(a,r.source_anchor):point(a, sp)), end = preview?.end || (r.target_anchor?boundaryPoint(b,r.target_anchor):point(b, tp));
  let control = r.control || { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
  if (!r.control && !r.source_anchor && !r.target_anchor && sp === tp) control = { x: Math.max(start.x, end.x) + 12, y: (start.y + end.y) / 2 };
  if(!r.control){
    const obstacles=scene.objects.filter(o=>o.visible&&o.role!=='context'&&o.id!==a.id&&o.id!==b.id);
    const cost=c=>{let hit=0;for(let i=1;i<30;i++){const t=i/30,u=1-t,x=u*u*start.x+2*u*t*c.x+t*t*end.x,y=u*u*start.y+2*u*t*c.y+t*t*end.y;
      hit+=obstacles.filter(o=>o.x-1<x&&x<o.x+o.w+1&&o.y-1<y&&y<o.y+o.h+1).length;
      if(x<1||y<1||x>scene.canvas.width_mm-1||y>scene.canvas.height_mm-1)hit+=4;}return hit;};
    if(cost(control)){const mx=(start.x+end.x)/2,my=(start.y+end.y)/2,candidates=[control,...[[0,-18],[0,18],[0,-36],[0,36],[-24,0],[24,0],[0,-60],[0,60]].map(([dx,dy])=>({x:mx+dx,y:my+dy}))];
      candidates.sort((a,b)=>cost(a)-cost(b)||Math.hypot(a.x-mx,a.y-my)-Math.hypot(b.x-mx,b.y-my));control=candidates[0];}
  }
  const path = `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`;
  const vx = end.x - control.x, vy = end.y - control.y, len = Math.hypot(vx, vy) || 1;
  const label={x:.25*start.x+.5*control.x+.25*end.x,y:.25*start.y+.5*control.y+.25*end.y-1.7};
  if(r.label_position)Object.assign(label,r.label_position);
  else if(r.label){const width=measureMM(r.label,7*25.4/72),height=7*25.4/72,boxes=scene.objects.filter(o=>o.visible&&o.role!=='context').map(o=>({x:o.x,y:o.y,w:o.w,h:o.h}));
    for(const o of scene.objects.filter(o=>o.visible&&o.label)){const{lines,fs}=labelLines(o),w=Math.max(...lines.map(t=>measureMM(t,fs)));boxes.push({x:o.x+o.w/2+(o.label_dx||0)-w/2,y:labelBaseline(o,lines,fs)-fs*.8,w,h:fs*(1.23*(lines.length-1)+1)});}
    const cost=([dx,dy])=>{const x=label.x+dx-width/2,y=label.y+dy-height*.8;if(x<.5||y<.5||x+width>scene.canvas.width_mm-.5||y+height>scene.canvas.height_mm-.5)return 10000;
      return boxes.reduce((sum,b)=>sum+Math.max(0,Math.min(x+width,b.x+b.w)-Math.max(x,b.x))*Math.max(0,Math.min(y+height,b.y+b.h)-Math.max(y,b.y)),0);};
    const offsets=[[0,0],[0,-4],[0,4],[0,-8],[0,8],[-8,0],[8,0],[0,-12],[0,12],[-12,0],[12,0],[-18,0],[18,0],[-24,0],[24,0],[-18,4],[18,4]];
    offsets.sort((a,b)=>cost(a)-cost(b)||Math.hypot(...a)-Math.hypot(...b));label.x+=offsets[0][0];label.y+=offsets[0][1];
  }
  return {
    start, end, control, path,
    ux: vx / len, uy: vy / len,
    label
  };
}

function labelBaseline(o,lines,fs){
  if((o.state||'').startsWith('legend_'))return o.y+o.h/2+fs*.3+(o.label_dy||0);
  if(o.state==='flow_lane')return o.y+3.5+(o.label_dy||0);
  if((o.state||'').startsWith('flow_'))return o.y+o.h/2+fs*.3-(lines.length-1)*fs*1.23/2+(o.label_dy||0);
  return o.y+o.h+fs*1.05+(o.label_dy||0);
}
function labelLines(o) {
  const text = o.label || '', fs = Math.max(7, o.font_size_pt || 8) * 25.4 / 72;
  const limit = (o.state||'').startsWith('flow_')?Math.max(5,o.w-(o.state==='flow_decision'?10:5)):Math.max(24, Math.min(42, (o.w || 18) + 12));
  const hasSpace = text.includes(' ');
  const words = hasSpace ? text.split(' ') : [...text];
  const spacer = hasSpace ? ' ' : '';
  const lines = []; let current = '';
  const measure = str => measureMM(str,fs);
  for (const word of words) {
    const cand = current ? current + spacer + word : word;
    if (current && measure(cand) > limit) { lines.push(current); current = word; }
    else current = cand;
  }
  if (current) lines.push(current);
  return { lines: lines.length ? lines : [''], fs };
}

export class SceneEditor {
  constructor({ host, onChange = () => {}, onSelection = () => {}, onZoom = () => {}, onStatus = () => {} }) {
    this.host = host;
    this.onChange = onChange;
    this.onSelection = onSelection;
    this.onZoom = onZoom;
    this.onStatus = onStatus;
    this.doc = null;
    this.base = null;
    this.baseSvg = null;
    this.selected = new Set();
    this.undoStack = [];
    this.redoStack = [];
    this.tool = 'select';
    this.zoom = 1;
    this.offset = { x: 30, y: 30 };
    this.fitMode = true;
    this.clipboard = null;
    this.space = false;
    this.gesture = null;
    this.artwork = new Map();
    this.snap = true;
    this.guides = [];
    this.relationType='associates';

    host.addEventListener('pointerdown', e => this.down(e));
    host.addEventListener('pointermove', e => this.move(e));
    host.addEventListener('pointerup', e => this.up(e));
    host.addEventListener('pointercancel', () => this.cancelGesture());
    host.addEventListener('dblclick', e => this.editLabel(e));
    host.addEventListener('wheel', e => {
      if (!this.doc) return;
      e.preventDefault();
      if(wheelIntent(e)==='zoom')this.zoomAt(Math.exp(-Math.max(-120,Math.min(120,e.deltaY))*.002),e.clientX,e.clientY);
      else{this.offset.x-=e.shiftKey?e.deltaY:(e.deltaX||0);this.offset.y-=e.shiftKey?0:e.deltaY;this.fitMode=false;this.constrainView();this.position();}
    }, { passive: false });
    host.addEventListener('contextmenu', e => this.openContextMenu(e));
    document.addEventListener('keydown', e => this.key(e));
    document.addEventListener('keyup', e => { if (e.code === 'Space') this.space = false; });
    window.addEventListener('blur', () => { this.space = false; this.cancelGesture(); });
    new ResizeObserver(() => { if (this.fitMode) this.fit(); }).observe(host);
  }

  get scene() { return this.doc; }
  get selectedIds() { return [...this.selected]; }
  get hasUndo() { return this.undoStack.length > 0; }
  get hasRedo() { return this.redoStack.length > 0; }

  setDocument(scene, svg) {
    this.activeLabel=null;
    this.relationType=scene.provenance?.method==='original-editable-workflow'?'sequence':'associates';
    this.doc = copy(scene);
    this.base = copy(scene);
    this.baseSvg = sanitizedSvg(svg);
    this.undoStack = [];
    this.redoStack = [];
    this.selected.clear();
    this.draw();
    this.fit();
    this.onSelection([]);
  }

  updateDocument(scene, svg) {
    this.doc = copy(scene);
    this.base = copy(scene);
    this.baseSvg = sanitizedSvg(svg);
    const ids = new Set([...scene.objects, ...scene.relations].map(o => o.id));
    this.selected = new Set([...this.selected].filter(id => ids.has(id)));
    this.draw();
    this.onSelection(this.selectedIds);
  }

  clear() {
    this.doc = null;
    this.base = null;
    this.baseSvg = null;
    this.selected.clear();
    this.host.replaceChildren();
  }

  setSelection(ids) {
    if(ids.length!==1||ids[0]!==this.activeLabel?.id)this.activeLabel=null;
    this.selected = new Set(ids);
    this.drawOverlay();
    this.onSelection(this.selectedIds);
  }

  setTool(tool) {
    this.tool = tool;
    this.connectStart = null;
    this.connectAnchor = null;
    this.connectPreview = null;
    this.connectHover = null;
    this.connectionFree = false;
    if(tool==='connect'&&this.selected.size===1&&this.doc?.objects.some(o=>this.selected.has(o.id)&&!o.locked))this.connectStart=this.selectedIds[0];
    this.host.style.cursor = tool === 'pan' ? 'grab' : ['connect','text'].includes(tool) ? 'crosshair' : 'default';
    document.querySelectorAll('[data-tool]').forEach(b=>b.classList.toggle('active',b.dataset.tool===tool));
    document.getElementById('add-text')?.classList.toggle('active',tool==='text');
    this.drawOverlay();
    this.host.dispatchEvent?.(new Event('editor-tool-change'));
  }

  finishConnection(source,target,sourcePort='auto',targetAnchor=null,sourceAnchor=null){
    if(source===target||!this.doc?.objects.some(o=>o.id===target))return false;
    const id=uid('r');
    this.applyOperations([{op:'add_relation',relation:{id,source,target,type:this.relationType||'associates',source_port:sourcePort,target_port:'auto',...(sourceAnchor?{source_anchor:sourceAnchor}:{}),...(targetAnchor?{target_anchor:targetAnchor}:{}),label:'',indirect:false,uncertain:(this.relationType||'associates')==='associates'}}],'添加连线');
    this.setTool('select');this.setSelection?.([id]);
    this.onStatus('已连好。上方可以确认连线含义，拖动图形时连线会跟随。');return true;
  }

  world(e) {
    const svg = this.host.querySelector('svg');
    if (svg?.getScreenCTM()) {
      const point = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
      return { x: point.x, y: point.y };
    }
    const r = this.host.getBoundingClientRect();
    return {
      x: (e.clientX - r.left - this.offset.x) / (PXMM * this.zoom),
      y: (e.clientY - r.top - this.offset.y) / (PXMM * this.zoom)
    };
  }

  geometry(r){
    const g=this.gesture,preview=g?.kind==='edge'&&g.id===r.id&&g.handle!=='control'&&g.preview?{[g.handle]:g.preview}:null;
    return edgeGeometry(this.doc,r,preview);
  }

  fit() {
    if (!this.doc) return;
    const w = this.doc.canvas.width_mm, h = this.doc.canvas.height_mm;
    this.zoom = Math.max(.12, Math.min((this.host.clientWidth - 80) / (w * PXMM), (this.host.clientHeight - 70) / (h * PXMM), 2));
    this.offset = {
      x: (this.host.clientWidth - w * PXMM * this.zoom) / 2,
      y: (this.host.clientHeight - h * PXMM * this.zoom) / 2
    };
    this.fitMode = true;
    this.position();
  }

  setZoom(value) {
    if (!this.doc) return;
    const old = this.zoom;
    this.zoom = Math.max(.1, Math.min(8, value));
    const cx = this.host.clientWidth / 2, cy = this.host.clientHeight / 2;
    this.offset = {
      x: cx - (cx - this.offset.x) * this.zoom / old,
      y: cy - (cy - this.offset.y) * this.zoom / old
    };
    this.fitMode = false;
    this.position();
  }

  zoomBy(factor) { this.setZoom(this.zoom * factor); }

  constrainView(){if(this.doc)this.offset=clampView(this.offset,{width:this.doc.canvas.width_mm*PXMM*this.zoom,height:this.doc.canvas.height_mm*PXMM*this.zoom},{width:this.host.clientWidth,height:this.host.clientHeight});}

  zoomAt(factor, x, y) {
    const r = this.host.getBoundingClientRect(), cx = x - r.left, cy = y - r.top, old = this.zoom;
    this.zoom = Math.max(.1, Math.min(8, this.zoom * factor));
    this.offset = {
      x: cx - (cx - this.offset.x) * this.zoom / old,
      y: cy - (cy - this.offset.y) * this.zoom / old
    };
    this.fitMode = false;
    this.constrainView();
    this.position();
  }

  position() {
    const svg = this.host.querySelector('svg');
    if (!svg || !this.doc) return;
    svg.style.position = 'absolute';
    svg.style.width = this.doc.canvas.width_mm * PXMM * this.zoom + 'px';
    svg.style.height = this.doc.canvas.height_mm * PXMM * this.zoom + 'px';
    svg.style.left = this.offset.x + 'px';
    svg.style.top = this.offset.y + 'px';
    this.onZoom(this.zoom);
    this.drawOverlay();
  }

  fitSelection(){
    const objects=this.doc?.objects.filter(o=>this.selected.has(o.id));
    if(!objects?.length)return this.fit();
    const bounds=objects.map(o=>{const a=(o.rotation||0)*Math.PI/180,w=Math.abs(Math.cos(a))*o.w+Math.abs(Math.sin(a))*o.h,h=Math.abs(Math.sin(a))*o.w+Math.abs(Math.cos(a))*o.h;return {x:o.x+o.w/2-w/2,y:o.y+o.h/2-h/2,w,h};});
    const x=Math.min(...bounds.map(o=>o.x)),y=Math.min(...bounds.map(o=>o.y));
    const w=Math.max(...bounds.map(o=>o.x+o.w))-x,h=Math.max(...bounds.map(o=>o.y+o.h))-y;
    this.zoom=Math.max(.1,Math.min(8,(this.host.clientWidth-100)/((w+12)*PXMM),(this.host.clientHeight-100)/((h+12)*PXMM)));
    this.offset={x:this.host.clientWidth/2-(x+w/2)*PXMM*this.zoom,y:this.host.clientHeight/2-(y+h/2)*PXMM*this.zoom};
    this.fitMode=false;this.position();
  }

  revealSelection(){
    if(!this.doc)return;
    const ids=new Set(this.selectedIds);for(const r of this.doc.relations)if(ids.has(r.id)){ids.add(r.source);ids.add(r.target);}
    const objects=this.doc.objects.filter(o=>ids.has(o.id));if(!objects.length)return;
    const x=Math.min(...objects.map(o=>o.x)),y=Math.min(...objects.map(o=>o.y)),w=Math.max(...objects.map(o=>o.x+o.w))-x,h=Math.max(...objects.map(o=>o.y+o.h))-y;
    this.zoom=Math.max(.1,Math.min(this.zoom,(this.host.clientWidth-70)/((w+20)*PXMM),(this.host.clientHeight-70)/((h+20)*PXMM)));
    this.offset={x:this.host.clientWidth/2-(x+w/2)*PXMM*this.zoom,y:this.host.clientHeight/2-(y+h/2)*PXMM*this.zoom};this.fitMode=false;this.position();
  }

  /** Newly inserted items stay visible, without centering the paper after every click. */
  ensureSelectionVisible(){
    if(!this.doc)return;
    const objects=this.doc.objects.filter(o=>this.selected.has(o.id)&&o.visible!==false);
    if(!objects.length)return;
    const x=Math.min(...objects.map(o=>o.x))-2,y=Math.min(...objects.map(o=>o.y))-2;
    const w=Math.max(...objects.map(o=>o.x+o.w))-x+2,h=Math.max(...objects.map(o=>o.y+o.h))-y+8;
    const width=this.host.clientWidth,height=this.host.clientHeight;
    const zoom=Math.max(.1,Math.min(this.zoom,(width-80)/(w*PXMM),(height-120)/(h*PXMM)));
    let ox=this.offset.x,oy=this.offset.y;
    const left=x*PXMM*zoom+ox,top=y*PXMM*zoom+oy;
    if(left<39.99)ox+=40-left;else if(left+w*PXMM*zoom>width-39.99)ox+=width-40-left-w*PXMM*zoom;
    if(top<79.99)oy+=80-top;else if(top+h*PXMM*zoom>height-39.99)oy+=height-40-top-h*PXMM*zoom;
    if(zoom===this.zoom&&ox===this.offset.x&&oy===this.offset.y)return;
    this.zoom=zoom;this.offset={x:ox,y:oy};this.fitMode=false;this.position();
  }

  insertTextAtCenter(){
    if(!this.doc)return;
    const r=this.host.getBoundingClientRect(),point=this.world({clientX:r.left+this.host.clientWidth/2,clientY:r.top+this.host.clientHeight/2});
    this.setTool('select');this.insertObject('text','输入文字',{},point);this.ensureSelectionVisible();
    requestAnimationFrame(()=>this.editSelectedLabel());
  }

  draw() {
    if (!this.baseSvg || !this.doc) return;
    const svg = this.baseSvg.cloneNode(true);
    svg.setAttribute('viewBox', `0 0 ${this.doc.canvas.width_mm} ${this.doc.canvas.height_mm}`);
    svg.setAttribute('data-revision', this.doc.revision);

    let objects = svg.querySelector('#layer-objects');
    if (!objects) {
      objects = node('g', { id: 'layer-objects' });
      svg.append(objects);
    }
    const original = new Map([...svg.querySelectorAll('[data-object-id]')].map(n => [n.getAttribute('data-object-id'), n.cloneNode(true)]));
    objects.replaceChildren();
    let contexts=svg.querySelector('#layer-context');
    if(!contexts){contexts=node('g',{id:'layer-context'});svg.insertBefore(contexts,objects);}
    contexts.replaceChildren();

    for (const o of this.doc.objects) {
      if (!o.visible) continue;
      const group = node('g', {
        'data-object-id': o.id,
        'data-type': o.type,
        tabindex: '0',
        role: 'button',
        'aria-label': o.label || o.id
      });
      group.style.pointerEvents=o.locked||o.role==='context'?'none':'bounding-box';
      const old = this.base.objects.find(x => x.id === o.id);
      const source = original.get(o.id);
      let body = node('g');

      if (source && old && old.type === o.type && old.state === o.state && old.asset_id === o.asset_id && old.illustration?.sha256 === o.illustration?.sha256) {
        for (const child of [...source.children]) {
          if (child.hasAttribute('data-label-for')) continue;
          const c = child.cloneNode(true);
          if (c.hasAttribute('data-glyph')) {
            c.removeAttribute('transform');
          }
          body.append(c);
        }
        const ox = old.x + old.w / 2, oy = old.y + old.h / 2;
        body.setAttribute('transform', `translate(${o.x + o.w / 2} ${o.y + o.h / 2}) rotate(${o.rotation || 0}) scale(${o.w / old.w} ${o.h / old.h}) translate(${-ox} ${-oy})`);
        if (o.fill !== old.fill) {
          body.querySelectorAll('[fill]').forEach(n => {
            if (!['none', '#FFFFFF', '#ffffff', '#fff'].includes(n.getAttribute('fill'))) {
              n.setAttribute('fill', o.fill || '#dce9ed');
            }
          });
        }
        if (o.stroke !== old.stroke && o.stroke) {
          body.querySelectorAll('[stroke]').forEach(n => n.setAttribute('stroke', o.stroke));
        }
        const ratio=(o.stroke_pt??this.doc.style.stroke_pt)/(old.stroke_pt??this.base.style.stroke_pt);
        if(ratio!==1)body.querySelectorAll('[stroke-width]').forEach(n=>n.setAttribute('stroke-width',Number(n.getAttribute('stroke-width'))*ratio));
      } else {
        const attrs = {
          x: o.x, y: o.y, width: o.w, height: o.h, rx: Math.min(o.w, o.h) / 3,
          fill: o.fill || '#deebef', stroke: o.stroke || '#527f92', 'stroke-width': .28
        };
        if(o.illustration?.data){
          body.append(node('image',{href:o.illustration.data,x:o.x,y:o.y,width:o.w,height:o.h,preserveAspectRatio:'xMidYMid meet'}));
        } else if(this.artwork?.has(o.asset_id || o.type)){
          const art=this.artwork.get(o.asset_id || o.type).cloneNode(true),box=art.getAttribute('viewBox').split(/[ ,]+/).map(Number);
          const g=node('g',{transform:`translate(${o.x} ${o.y}) scale(${o.w/box[2]} ${o.h/box[3]}) translate(${-box[0]} ${-box[1]})`});
          g.append(...art.children);body.append(g);
        } else if (['vesicle', 'mvb', 'ligand', 'immune_cell'].includes(o.type)) {
          body.append(node('ellipse', { cx: o.x + o.w / 2, cy: o.y + o.h / 2, rx: o.w / 2, ry: o.h / 2, fill: attrs.fill, stroke: attrs.stroke, 'stroke-width': .28 }));
        } else if (o.type !== 'text') {
          body.append(node('rect', attrs));
        }
      }
      group.append(body);

      const canonicalLabels=source?[...source.querySelectorAll('[data-label-for]')]:[];
      const preserveLabels=old&&canonicalLabels.length&&old.label===o.label&&old.w===o.w&&old.h===o.h&&old.font_size_pt===o.font_size_pt;
      if(preserveLabels){for(const original of canonicalLabels){const label=original.cloneNode(true);
        label.setAttribute('x',Number(label.getAttribute('x'))+o.x+o.w/2-old.x-old.w/2+(o.label_dx||0)-(old.label_dx||0));
        label.setAttribute('y',Number(label.getAttribute('y'))+o.y+o.h-old.y-old.h+(o.label_dy||0)-(old.label_dy||0));group.append(label);}}
      else {const { lines, fs } = labelLines(o);
      lines.forEach((lineText, i) => {
        const label = node('text', {
          'data-label-for': o.id,
          x: o.x + o.w / 2 + ((o.state||'').startsWith('legend_')?5:0) + (o.label_dx || 0),
          y: labelBaseline(o,lines,fs) + i * fs * 1.23,
          'text-anchor': 'middle',
          'font-family': 'Arial, Microsoft YaHei, sans-serif',
          'font-size': fs,
          fill: '#253844'
        }, lineText);
        group.append(label);
      });
      }

      group.querySelectorAll('[data-label-for]').forEach(n=>{n.setAttribute('cursor',o.type==='text'?'move':'grab');n.setAttribute('pointer-events','all');});
      (o.role==='context'?contexts:objects).append(group);
    }

    let edges = svg.querySelector('#layer-relations');
    if (!edges) {
      edges = node('g', { id: 'layer-relations' });
      svg.insertBefore(edges, objects);
    }
    edges.replaceChildren();

    for (const r of this.doc.relations) {
      const a = this.doc.objects.find(o => o.id === r.source), b = this.doc.objects.find(o => o.id === r.target);
      if (!a?.visible || !b?.visible) continue;
      const g = this.geometry(r);
      if (!g) continue;
      const color = r.stroke || (r.type === 'inhibits' ? '#AD6460' : this.doc.style.palette.primary);
      const group = node('g', {
        'data-relation-id': r.id,
        role: 'button',
        tabindex: '0',
        'aria-label': `${r.type}: ${a.label} -> ${b.label}`
      });
      group.setAttribute('data-relation-type',r.type);
      group.setAttribute('aria-label',`${RELATION_DEFINITIONS.find(t=>t.id===r.type)?.title}: ${a.label} → ${b.label}${r.indirect?' · 间接':''}${r.uncertain?' · 含义待核对':''}`);
      group.append(node('path',{d:g.path,fill:'none',stroke:'transparent','stroke-width':10,'vector-effect':'non-scaling-stroke','data-relation-hit':r.id}));
      for(const[tag,attrs]of relationParts(r.type,g.start,g.end,g.control,color,r.stroke_pt||1.05,r.indirect,{start:!!r.source_anchor,end:!!r.target_anchor}))group.append(node(tag,attrs));
      const label=relationLabel(this.doc,r);
      if(label){
        const width=measureMM(label,7*25.4/72)+1.2;
        group.append(node('rect',{x:g.label.x-width/2,y:g.label.y-2,width,height:2.7,fill:'#FFFFFF',rx:.3,'data-relation-label-for':r.id,cursor:'grab'}));
        group.append(node('text',{x:g.label.x,y:g.label.y,'text-anchor':'middle','font-size':7*25.4/72,'font-family':'Arial, Microsoft YaHei, sans-serif',fill:color,'data-relation-label-for':r.id,cursor:'grab'},label));
      }
      edges.append(group);
    }

    this.host.querySelector('svg')?.remove();
    this.host.prepend(svg);
    this.position();
    this.drawOverlay();
  }

  drawOverlay() {
    const svg = this.host.querySelector('svg');
    if (!svg || !this.doc) return;
    svg.querySelector('#editor-overlay')?.remove();
    const overlay = node('g', { id: 'editor-overlay', 'data-editor-overlay': 'true' });
    const unit=1/(PXMM*this.zoom),handleSize=8*unit,lineWidth=unit;
    if(this.connectStart&&this.connectPreview){
      const a=this.doc.objects.find(o=>o.id===this.connectStart);
      const target=connectionTarget(this.doc,this.connectPreview,this.zoom,this.connectStart,this.connectionFree),end=target?boundaryPoint(target.object,target.anchor):this.connectPreview;
      const start=a?boundaryPoint(a,this.connectAnchor||nearestBoundary(a,end)):null;
      if(start)overlay.append(node('path',{d:`M ${start.x} ${start.y} L ${end.x} ${end.y}`,stroke:'#3d71c7','stroke-width':unit,'stroke-dasharray':`${4*unit} ${3*unit}`,fill:'none','pointer-events':'none'}));
    }
    for(const guide of this.guides || [])overlay.append(node('line',{
      x1:guide.axis==='x'?guide.value:0,y1:guide.axis==='y'?guide.value:0,
      x2:guide.axis==='x'?guide.value:this.doc.canvas.width_mm,
      y2:guide.axis==='y'?guide.value:this.doc.canvas.height_mm,
      stroke:'#C48565','stroke-width':.22,'stroke-dasharray':'1 .8','pointer-events':'none'
    }));
    for (const id of this.selected) {
      const o = this.doc.objects.find(x => x.id === id);
      if (o) {
        const selection=node('g',{transform:`rotate(${o.rotation||0} ${o.x+o.w/2} ${o.y+o.h/2})`});overlay.append(selection);
        selection.append(node('rect', {
          x: o.x - .8, y: o.y - .8, width: o.w + 1.6, height: o.h + 1.6,
          fill: 'none', stroke: '#3d71c7', 'stroke-width':lineWidth, 'pointer-events': 'none'
        }));
        if (this.selected.size === 1 && !o.locked) {
          const handles=[
            ['nw',o.x,o.y,'nwse-resize'],
            ['n',o.x+o.w/2,o.y,'ns-resize'],
            ['ne',o.x+o.w,o.y,'nesw-resize'],
            ['e',o.x+o.w,o.y+o.h/2,'ew-resize'],
            ['se',o.x+o.w,o.y+o.h,'nwse-resize'],
            ['s',o.x+o.w/2,o.y+o.h,'ns-resize'],
            ['sw',o.x,o.y+o.h,'nesw-resize'],
            ['w',o.x,o.y+o.h/2,'ew-resize']
          ];
          for (const [corner, x, y, cur] of handles) {
            selection.append(node('rect', {
              x: x-handleSize/2, y: y-handleSize/2, width:handleSize, height:handleSize,
              fill:'white',stroke:'#3d71c7','stroke-width':lineWidth,'data-handle':corner,'data-owner':o.id,
              cursor:cur
            }));
          }
          selection.append(node('line', { x1:o.x+o.w/2,y1:o.y,x2:o.x+o.w/2,y2:o.y-22*unit,stroke:'#3d71c7','stroke-width':lineWidth }));
          selection.append(node('circle', { cx:o.x+o.w/2,cy:o.y-22*unit,r:handleSize/2,fill:'white',stroke:'#3d71c7','stroke-width':lineWidth,'data-handle':'rotate','data-owner':o.id,cursor:'grab' }));
          // Keep connection controls outside the object: controls appearing on
          // its body between two clicks would steal the second click.
          for(const [port,x,y] of [['e',o.x+o.w+12*unit,o.y+o.h/2],['w',o.x-12*unit,o.y+o.h/2]]){
            const p=node('circle',{cx:x,cy:y,r:5*unit,fill:'#345fc4',stroke:'white','stroke-width':1.5*unit,'data-connect-port':port,'data-owner':o.id,cursor:'crosshair'});p.append(node('title',{},'从这里拖到另一个对象，建立连线'));selection.append(p);
          }
          if(this.tool==='connect')selection.append(node('rect',{x:o.x,y:o.y,width:o.w,height:o.h,fill:'none',stroke:'transparent','stroke-width':10*unit,'data-connect-boundary':o.id,cursor:'crosshair'}));
        }
      }
      const r = this.doc.relations.find(x => x.id === id);
      if (r) {
        const g = this.geometry(r);
        if (g) {
          for (const [k, p] of [['start', g.start], ['end', g.end], ['control', g.control]]) {
            overlay.append(node('circle', {
              cx:p.x,cy:p.y,r:handleSize/2,fill:k==='control'?'#dae6fc':'#fff',
              stroke:'#3d71c7','stroke-width':lineWidth,'data-edge-handle':k,'data-owner':r.id,cursor:'move'
            }));
          }
        }
      }
    }
    const candidate=this.gesture?.candidate||(this.connectStart&&this.connectPreview?connectionTarget(this.doc,this.connectPreview,this.zoom,this.connectStart,this.connectionFree):this.tool==='connect'&&this.connectHover?connectionTarget(this.doc,this.connectHover,this.zoom,null,this.connectionFree):null);
    if(candidate){const o=candidate.object,p=boundaryPoint(o,candidate.anchor);
      overlay.append(node('rect',{x:o.x,y:o.y,width:o.w,height:o.h,transform:`rotate(${o.rotation||0} ${o.x+o.w/2} ${o.y+o.h/2})`,fill:'none',stroke:'#287b68','stroke-width':2*unit,'stroke-dasharray':`${5*unit} ${3*unit}`,'data-snap-boundary':o.id,'pointer-events':'none'}));
      if(!this.connectionFree)for(const k of connectionKeypoints(o))overlay.append(node('rect',{x:k.point.x-3*unit,y:k.point.y-3*unit,width:6*unit,height:6*unit,fill:'white',stroke:'#287b68','stroke-width':unit,'data-connection-keypoint':k.kind,'pointer-events':'none'}));
      overlay.append(node('circle',{cx:p.x,cy:p.y,r:5*unit,fill:'#287b68',stroke:'white','stroke-width':1.5*unit,'data-snap-point':o.id,'pointer-events':'none'}));
      if(candidate.keypoint)overlay.append(node('text',{x:p.x+9*unit,y:p.y-9*unit,fill:'#216551','font-size':11*unit,'font-family':'Arial, Microsoft YaHei, sans-serif','paint-order':'stroke',stroke:'white','stroke-width':3*unit,'stroke-linejoin':'round','pointer-events':'none'},candidate.keypoint==='corner'?'端点 · Alt 自由连接':'中点 · Alt 自由连接'));
    }
    if(this.activeLabel&&this.selected.size===1&&this.selected.has(this.activeLabel.id)){
      const selector=this.activeLabel.kind==='relation'?'[data-relation-label-for]':'[data-label-for]';
      const labels=[...svg.querySelectorAll(selector)].filter(n=>(n.dataset.labelFor||n.dataset.relationLabelFor)===this.activeLabel.id&&n.tagName==='text');
      for(const n of labels){const b=n.getBBox();overlay.append(node('rect',{x:b.x-.7,y:b.y-.5,width:b.width+1.4,height:b.height+1,fill:'none',stroke:'#287b68','stroke-width':unit,'stroke-dasharray':`${3*unit} ${2*unit}`,'data-label-selection':this.activeLabel.id,'pointer-events':'none'}));}
    }
    svg.append(overlay);
    this.onAnnotationRender?.();
  }

  down(e) {
    if (!this.doc || e.target.closest('input,.editor-inline-actions')) return;
    if (e.button !== 0 && e.button !== 1) return;
    e.preventDefault();
    this.host.focus({ preventScroll: true });
    this.host.setPointerCapture(e.pointerId);
    const point = this.world(e);
    this.connectionFree=!!e.altKey;
    const before = copy(this.doc);

    if (e.button === 1 || this.space || this.tool === 'pan') {
      this.gesture = { kind: 'pan', px: e.clientX, py: e.clientY, offset: { ...this.offset } };
      return;
    }
    if(this.tool==='text'){
      this.insertObject('text','文本',{},point);this.setTool('select');requestAnimationFrame(()=>this.editSelectedLabel());return;
    }
    const port=e.target.closest('[data-connect-port]');
    const boundary=e.target.closest('[data-connect-boundary]');
    if(port||boundary){
      const id=port?.dataset.owner||boundary.dataset.connectBoundary,o=this.doc.objects.find(o=>o.id===id);
      const anchor=port?{side:port.dataset.connectPort,t:.5}:connectionAnchor(o,point,this.zoom,e.altKey).anchor;
      this.connectStart=id;this.connectAnchor=anchor;this.connectPreview=point;this.gesture={kind:'connect',source:id,port:anchor.side,anchor,start:point};this.drawOverlay();return;
    }
    if(this.tool==='connect'){
      const candidate=connectionTarget(this.doc,point,this.zoom,null,e.altKey);
      if(candidate){
        const id=candidate.object.id,anchor=candidate.anchor;
        if(this.connectStart&&this.connectStart!==id)this.finishConnection(this.connectStart,id,'auto',anchor,this.connectAnchor);
        else{this.connectStart=id;this.connectAnchor=anchor;this.connectPreview=point;this.gesture={kind:'connect',source:id,port:anchor.side,anchor,start:point};this.drawOverlay();}
        return;
      }
    }
    if(e.altKey&&this.tool!=='connect'&&!e.target.closest('[data-handle],[data-edge-handle]')){
      const hits=hitObjects(this.doc,point,true),current=hits.findIndex(o=>this.selected.has(o.id));
      if(hits.length){
        const picked=hits[Math.max(0,current)];this.setSelection([picked.id]);
        this.gesture={kind:'move',start:point,before,px:e.clientX,py:e.clientY,ids:picked.locked||picked.role==='context'?[]:[picked.id],cycleId:hits[(current+1)%hits.length].id};return;
      }
    }
    const handle = e.target.closest('[data-handle]'), edgeHandle = e.target.closest('[data-edge-handle]');
    if (handle) {
      this.gesture = { kind: 'transform', handle: handle.dataset.handle, id: handle.dataset.owner, start: point, before };
      return;
    }
    if (edgeHandle) {
      this.activeLabel=null;
      this.gesture = { kind: 'edge', handle: edgeHandle.dataset.edgeHandle, id: edgeHandle.dataset.owner, start: point, before };
      return;
    }
    const label=e.target.closest('[data-label-for],[data-relation-label-for]');
    if(label&&this.tool==='select'&&!e.altKey){
      const kind=label.dataset.relationLabelFor?'relation':'object',id=label.dataset.relationLabelFor||label.dataset.labelFor;
      const item=(kind==='relation'?this.doc.relations:this.doc.objects).find(o=>o.id===id);
      if(item&&!item.locked&&item.type!=='text'){
        this.activeLabel={kind,id};this.setSelection([id]);
        this.gesture={kind:'label',labelKind:kind,id,start:point,before,px:e.clientX,py:e.clientY,origin:kind==='relation'?edgeGeometry(before,item).label:null};
        return;
      }
    }
    const object = e.target.closest('[data-object-id]'), edge = e.target.closest('[data-relation-id]');
    const picked=object?this.doc.objects.find(x=>x.id===object.dataset.objectId):(!edge?hitObjects(this.doc,point)[0]:null);
    if (picked) {
      const o=picked,id=o.id;
      if (!o) return;
      if (this.tool === 'connect') {
        if (this.connectStart && this.connectStart !== id) {
          this.finishConnection(this.connectStart,id,'auto',connectionAnchor(o,point,this.zoom,e.altKey).anchor,this.connectAnchor);
        } else {
          this.connectStart = id;
          this.connectAnchor=connectionAnchor(o,point,this.zoom,e.altKey).anchor;
          this.setSelection([id]);
          this.onStatus('请点击要连接的目标图元');
        }
        return;
      }
      this.activeLabel=null;
      if (e.shiftKey) {
        if (this.selected.has(id)) this.selected.delete(id);
        else this.selected.add(id);
      } else if (e.ctrlKey||e.metaKey||!this.selected.has(id)) {
        this.selected = new Set([id]);
      }
      if (o.group_id && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
        this.doc.objects.filter(x => x.visible&&!x.locked&&x.group_id === o.group_id).forEach(x => this.selected.add(x.id));
      }
      this.onSelection(this.selectedIds);
      this.drawOverlay();
      if (!o.locked) {
        this.gesture = {kind:'move',start:point,before,px:e.clientX,py:e.clientY,ids:this.selectedIds.filter(id=>this.doc.objects.some(x=>x.id===id&&!x.locked))};
      }
      return;
    }
    if (edge) {
      this.activeLabel=null;
      this.setSelection([edge.dataset.relationId]);
      return;
    }
    if (!e.shiftKey) this.setSelection([]);
    this.gesture = { kind: 'marquee', start: point, before, baseSelection: this.selectedIds };
  }

  move(e) {
    if(!this.doc)return;
    this.connectionFree=!!e.altKey;
    if(!this.gesture){if(this.tool==='connect'){this.connectHover=this.world(e);if(this.connectStart)this.connectPreview=this.connectHover;this.drawOverlay();}return;}
    const g = this.gesture;
    if (g.kind === 'pan') {
      this.offset = { x: g.offset.x + e.clientX - g.px, y: g.offset.y + e.clientY - g.py };
      this.fitMode = false;
      this.constrainView();
      this.position();
      return;
    }
    if(g.kind==='connect'){this.connectPreview=this.world(e);this.drawOverlay();return;}
    const point = this.world(e);let dx=point.x-g.start.x,dy=point.y-g.start.y;
    if(g.kind==='label'){
      if(!g.moved&&Math.hypot(e.clientX-g.px,e.clientY-g.py)<3)return;
      g.moved=true;if(e.shiftKey){if(Math.abs(dx)>Math.abs(dy))dy=0;else dx=0;}
      if(g.labelKind==='relation'){
        const r=this.doc.relations.find(r=>r.id===g.id);if(r)r.label_position={x:g.origin.x+dx,y:g.origin.y+dy};
      }else{
        const old=g.before.objects.find(o=>o.id===g.id),o=this.doc.objects.find(o=>o.id===g.id);
        if(o&&old){o.label_dx=(old.label_dx||0)+dx;o.label_dy=(old.label_dy||0)+dy;}
      }
      this.draw();
    }else if (g.kind === 'move') {
      if(!g.moved&&Math.hypot(e.clientX-g.px,e.clientY-g.py)<3)return;
      g.moved=true;
      if(e.shiftKey){if(Math.abs(dx)>Math.abs(dy))dy=0;else dx=0;}
      let sx=0,sy=0;this.guides=[];
      if(this.snap && !e.altKey){
        const moving=g.before.objects.filter(o=>g.ids.includes(o.id)),targets=this.doc.objects.filter(o=>o.visible&&o.role!=='context'&&!g.ids.includes(o.id));
        const threshold=1.4/Math.max(.4,this.zoom);
        for(const axis of ['x','y']){
          const dim=axis==='x'?'w':'h',delta=axis==='x'?dx:dy;
          let best=threshold,shift=0,value=null;
          for(const a of moving)for(const b of targets)for(const k of [0,.5,1])for(const j of [0,.5,1]){
            const target=b[axis]+b[dim]*j,d=target-(a[axis]+a[dim]*k+delta);
            if(Math.abs(d)<best){best=Math.abs(d);shift=d;value=target;}
          }
          if(value!==null&&(!e.shiftKey||(axis==='x'?dx!==0:dy!==0))){if(axis==='x')sx=shift;else sy=shift;this.guides.push({axis,value});}
        }
      }
      for (const id of g.ids) {
        const old = g.before.objects.find(o => o.id === id), o = this.doc.objects.find(o => o.id === id);
        if (!old || !o) continue;
        o.x = Math.round((old.x + dx + sx) * 10) / 10;
        o.y = Math.round((old.y + dy + sy) * 10) / 10;
      }
      this.draw();
    } else if (g.kind === 'transform') {
      const old = g.before.objects.find(o => o.id === g.id), o = this.doc.objects.find(o => o.id === g.id);
      if (!old || !o) return;
      if (g.handle === 'rotate') {
        o.rotation = (Math.atan2(point.y - (old.y + old.h / 2), point.x - (old.x + old.w / 2)) * 180 / Math.PI + 90 + 360) % 360;
        if(e.shiftKey)o.rotation=Math.round(o.rotation/15)*15;
      } else {
        Object.assign(o,resizedObject(old,g.handle,dx,dy,e.shiftKey||(!!old.asset_id&&!e.altKey)));
      }
      this.draw();
    } else if (g.kind === 'edge') {
      const r = this.doc.relations.find(r => r.id === g.id);
      if (r && g.handle === 'control') r.control = { x: point.x, y: point.y };
      else if(r){g.candidate=connectionTarget(this.doc,point,this.zoom,r[g.handle==='start'?'target':'source'],e.altKey);g.preview=g.candidate?boundaryPoint(g.candidate.object,g.candidate.anchor):point;}
      this.draw();
    } else if (g.kind === 'marquee') {
      this.host.querySelector('#editor-marquee')?.remove();
      this.host.querySelector('svg')?.append(node('rect', {
        id: 'editor-marquee',
        x: Math.min(g.start.x, point.x), y: Math.min(g.start.y, point.y),
        width: Math.abs(dx), height: Math.abs(dy),
        fill: '#d9eaf04d', stroke: '#4e91b0', 'stroke-width': .2
      }));
      g.end = point;
    }
  }

  up(e) {
    if(this.host.hasPointerCapture?.(e.pointerId))this.host.releasePointerCapture(e.pointerId);
    const g = this.gesture;
    if (!g) return;
    this.gesture = null;
    this.guides = [];
    if(g.kind==='connect'){
      const target=connectionTarget(this.doc,this.world(e),this.zoom,g.source,e.altKey);
      if(target)this.finishConnection(g.source,target.object.id,g.port,target.anchor,g.anchor);
      else{this.setTool('connect');this.connectStart=g.source;this.connectAnchor=g.anchor;this.connectPreview=null;this.onStatus('点击另一个对象的边缘完成连线，或点“取消连线”。');this.host.dispatchEvent?.(new Event('editor-tool-change'));}
      return;
    }
    if(g.kind==='move'&&g.cycleId&&!g.moved){this.setSelection([g.cycleId]);return;}
    if (g.kind === 'marquee') {
      this.host.querySelector('#editor-marquee')?.remove();
      if (g.end) {
        const x = Math.min(g.start.x, g.end.x), y = Math.min(g.start.y, g.end.y),
              w = Math.abs(g.end.x - g.start.x), h = Math.abs(g.end.y - g.start.y);
        this.setSelection([...g.baseSelection, ...this.doc.objects.filter(o => o.visible&&!o.locked&&o.role!=='context'&&o.x < x + w && o.x + o.w > x && o.y < y + h && o.y + o.h > y).map(o => o.id)]);
      }
      return;
    }
    if (g.kind === 'edge' && g.handle !== 'control') {
      const point = this.world(e);
      const relation=this.doc.relations.find(r=>r.id===g.id);
      const target=connectionTarget(this.doc,point,this.zoom,relation?.[g.handle==='start'?'target':'source'],e.altKey);
      if (target) {
        const r = this.doc.relations.find(r => r.id === g.id);
        if (r) {
          const opposite=r[g.handle==='start'?'target':'source'];
          if(target.object.id!==opposite){const end=g.handle==='start'?'source':'target';r[end]=target.object.id;r[end+'_port']='auto';r[end+'_anchor']=target.anchor;}
        }
      } else {
        this.onStatus('请把端点拖到对象边缘，靠近时会显示吸附点；本次保留原连接。');
      }
    }
    if (g.kind !== 'pan') this.commit(g.before,g.kind==='label'?'移动文字':g.kind==='edge'?'调整连线':'编辑图元');
    if(g.kind==='edge')this.draw();else this.drawOverlay();
  }

  cancelGesture() {
    this.guides=[];
    this.host.querySelector('#editor-marquee')?.remove();
    const before=this.gesture?.before;
    this.gesture=null;
    if (before) {
      this.doc = before;
      this.draw();
    }
    this.connectStart=null;this.connectPreview=null;
    this.connectAnchor=null;
    this.drawOverlay();
  }

  commit(before, label = '编辑图元') {
    if (JSON.stringify(before) === JSON.stringify(this.doc)) return;
    this.undoStack.push(copy(before));
    if (this.undoStack.length > 100) this.undoStack.shift();
    this.redoStack = [];
    this.onChange([{ op: 'replace', scene: copy(this.doc) }], copy(this.doc), label);
    this.draw();
    this.onSelection(this.selectedIds);
  }

  applyOperations(operations, label = '编辑图元') {
    if (!this.doc) return;
    const before = copy(this.doc);
    for (const op of operations) {
      if (op.op === 'replace') this.doc = copy(op.scene);
      else if (op.op === 'update' || op.op === 'update_relation') {
        const list = op.op === 'update' ? this.doc.objects : this.doc.relations;
        const item = list.find(x => x.id === op.id);
        if (item) Object.assign(item, copy(op.changes));
      } else if (op.op === 'add') this.doc.objects.push(copy(op.object));
      else if (op.op === 'add_relation') this.doc.relations.push(copy(op.relation));
      else if (op.op === 'remove') {
        this.doc.objects = this.doc.objects.filter(o => o.id !== op.id);
        this.doc.relations = this.doc.relations.filter(r => r.source !== op.id && r.target !== op.id);
        this.selected.delete(op.id);
      } else if (op.op === 'remove_relation') {
        this.doc.relations = this.doc.relations.filter(r => r.id !== op.id);
        this.selected.delete(op.id);
      } else if(op.op==='canvas')this.doc.canvas={width_mm:op.width_mm??this.doc.canvas.width_mm,height_mm:op.height_mm??this.doc.canvas.height_mm};
      else if(op.op==='style')this.doc.style={...this.doc.style,...copy(op.changes),palette:{...this.doc.style.palette,...op.changes.palette}};
      else if(op.op==='reorder'){const items=new Map(this.doc.objects.map(o=>[o.id,o]));this.doc.objects=op.ids.map(id=>items.get(id));}
    }
    this.commit(before, label);
  }

  undo() {
    if (!this.undoStack.length) return;
    const previous = this.undoStack.pop();
    this.redoStack.push(copy(this.doc));
    this.doc = previous;
    this.onChange([{ op: 'replace', scene: copy(this.doc) }], copy(this.doc), '撤销');
    this.draw();
    this.onSelection(this.selectedIds);
  }

  redo() {
    if (!this.redoStack.length) return;
    const next = this.redoStack.pop();
    this.undoStack.push(copy(this.doc));
    this.doc = next;
    this.onChange([{ op: 'replace', scene: copy(this.doc) }], copy(this.doc), '重做');
    this.draw();
    this.onSelection(this.selectedIds);
  }

  changeSelection(changes) {
    if (!this.doc) return;
    const relOps = this.doc.relations.filter(r => this.selected.has(r.id)).map(r => ({ op: 'update_relation', id: r.id, changes }));
    const ops = this.doc.objects.filter(o => this.selected.has(o.id) && !o.locked).map(o => ({ op: 'update', id: o.id, changes }));
    if (ops.length||relOps.length) this.applyOperations([...relOps,...ops]);
  }

  insertObject(type, label, asset={}, position=null) {
    if (!this.doc) return;
    const id = uid('o'), [w,h] = asset.default_dim || (type==='text'?[30,3]:[18,13]);
    const c = this.doc.compartments.find(c => c.id === 'cytoplasm');
    const object = {
      id, entity_id: id, type, label, compartment: '',
      x: (c ? c.x + c.w / 2 : this.doc.canvas.width_mm / 2) - w / 2,
      y: (c ? c.y + c.h / 2 : this.doc.canvas.height_mm / 2) - h / 2,
      w, h, rotation: 0, font_size_pt: this.doc.style.font_size_pt||8, state: asset.state||'', group_id: '', visible: true, locked: false, label_dx: 0, label_dy: 0
    };
    if(asset.asset_id)object.asset_id=asset.asset_id;
    if(!position){
      const occupied=this.doc.objects.filter(o=>o.visible),candidates=[];
      for(let y=8;y+h+7<this.doc.canvas.height_mm;y+=6)for(let x=8;x+w+5<this.doc.canvas.width_mm;x+=6){
        const overlap=occupied.reduce((sum,o)=>sum+Math.max(0,Math.min(x+w+2,o.x+o.w+2)-Math.max(x-2,o.x-2))*Math.max(0,Math.min(y+h+6,o.y+o.h+6)-Math.max(y-2,o.y-2)),0);
        candidates.push({x,y,score:overlap*1000+Math.hypot(x-object.x,y-object.y)});
      }
      candidates.sort((a,b)=>a.score-b.score);if(candidates.length){object.x=candidates[0].x;object.y=candidates[0].y;}
    }
    if(position){object.x=Math.max(0,Math.min(this.doc.canvas.width_mm-w,position.x-w/2));object.y=Math.max(0,Math.min(this.doc.canvas.height_mm-h-5,position.y-h/2));}
    this.applyOperations([{ op: 'add', object }], '添加图元');
    this.setSelection([id]);
  }

  deleteSelection() {
    if (!this.doc) return;
    const ops=[...this.selected].filter(id=>!this.doc.objects.find(o=>o.id===id)?.locked).map(id=>({op:this.doc.objects.some(o=>o.id===id)?'remove':'remove_relation',id}));
    if(!ops.length)return this.onStatus('所选对象已锁定，请先在图层中解锁');
    this.applyOperations(ops, '删除');
    this.setSelection([]);
  }

  connectSelection(type='associates'){
    const objects=this.doc?.objects.filter(o=>this.selected.has(o.id));
    if(objects?.length!==2)return this.onStatus('请按 Shift 依次选择起点和终点');
    const [source,target]=this.selectedIds.filter(id=>objects.some(o=>o.id===id)),id=uid('r');
    this.applyOperations([{op:'add_relation',relation:{id,source,target,type,label:'',source_port:'auto',target_port:'auto',indirect:false,uncertain:type==='associates'}}],'连接所选对象');
    this.setSelection([id]);
  }

  distributeSelection(axis='x'){
    const dim=axis==='x'?'w':'h',objects=this.doc.objects.filter(o=>this.selected.has(o.id)&&!o.locked).sort((a,b)=>a[axis]-b[axis]);
    if(objects.length<3)return this.onStatus('等距分布需要至少三个对象');
    const span=objects.at(-1)[axis]+objects.at(-1)[dim]-objects[0][axis],gap=(span-objects.reduce((s,o)=>s+o[dim],0))/(objects.length-1);
    let at=objects[0][axis];const ops=objects.map(o=>{const op={op:'update',id:o.id,changes:{[axis]:at}};at+=o[dim]+gap;return op;});this.applyOperations(ops,'等距分布');
  }

  duplicateSelection() {
    if (!this.doc) return;
    const selected = this.doc.objects.filter(o => this.selected.has(o.id));
    if (!selected.length) return;
    const ids = new Map(selected.map(o => [o.id, uid('o')]));
    const groupMap = new Map();
    const ops = selected.map(o => {
      if (o.group_id && !groupMap.has(o.group_id)) groupMap.set(o.group_id, uid('g'));
      return { op: 'add', object: { ...copy(o), id: ids.get(o.id), x: o.x + 4, y: o.y + 4, group_id: groupMap.get(o.group_id) || '' } };
    });
    for (const r of this.doc.relations) {
      if (ids.has(r.source) && ids.has(r.target)) {
        ops.push({ op: 'add_relation', relation: { ...copy(r), id: uid('r'), source: ids.get(r.source), target: ids.get(r.target),...(r.control?{control:{x:r.control.x+4,y:r.control.y+4}}:{}),...(r.label_position?{label_position:{x:r.label_position.x+4,y:r.label_position.y+4}}:{}) } });
      }
    }
    this.applyOperations(ops, '复制');
    this.setSelection([...ids.values()]);
  }

  groupSelection() {
    if (this.selected.size < 2) return;
    this.changeSelection({ group_id: uid('g') });
  }

  ungroupSelection() {
    this.changeSelection({ group_id: '' });
  }

  alignSelection(direction) {
    const objects = this.doc.objects.filter(o => this.selected.has(o.id) && !o.locked);
    if (objects.length < 2) return;
    const left = Math.min(...objects.map(o => o.x)), right = Math.max(...objects.map(o => o.x + o.w)),
          top = Math.min(...objects.map(o => o.y)), bottom = Math.max(...objects.map(o => o.y + o.h));
    this.applyOperations(objects.map(o => ({
      op: 'update', id: o.id,
      changes: direction === 'left' ? { x: left } :
               direction === 'right' ? { x: right - o.w } :
               direction === 'center' ? { x: (left + right - o.w) / 2 } :
               direction === 'top' ? { y: top } :
               direction === 'bottom' ? { y: bottom - o.h } :
               { y: (top + bottom - o.h) / 2 }
    })), '对齐');
  }

  setCanvasSize(width, height) {
    if (!this.doc) return;
    const before = copy(this.doc);
    this.doc.canvas = { width_mm: width, height_mm: height };
    this.undoStack.push(before);
    this.redoStack = [];
    this.onChange([{ op: 'canvas', width_mm: width, height_mm: height, reflow: true }], copy(this.doc), '画布重排');
    this.fit();
  }

  editLabel(e) {
    if(!this.doc)return;
    let label = e.target.closest('[data-label-for],[data-relation-label-for]');
    if(!label&&Number.isFinite(e.clientX))label=[...this.host.querySelectorAll('[data-label-for],[data-relation-label-for]')].reverse().find(n=>{const r=n.getBoundingClientRect();return e.clientX>=r.left&&e.clientX<=r.right&&e.clientY>=r.top&&e.clientY<=r.bottom;});
    if(!label){const id=e.target.closest('[data-object-id]')?.dataset.objectId||(Number.isFinite(e.clientX)?hitObjects(this.doc,this.world(e))[0]?.id:null);label=id?[...this.host.querySelectorAll('[data-label-for]')].find(n=>n.dataset.labelFor===id):null;}
    if (!label || !this.doc) return;
    const relation=!!label.dataset.relationLabelFor;
    const o = (relation?this.doc.relations:this.doc.objects).find(o => o.id === (label.dataset.relationLabelFor||label.dataset.labelFor));
    if (!o || o.locked) return;
    e.preventDefault();
    this.host.querySelector('input')?.remove();
    this.host.querySelector('.editor-inline-actions')?.remove();
    const rect = label.getBoundingClientRect(), host = this.host.getBoundingClientRect();
    const input = document.createElement('input');
    const actions=document.createElement('div'),save=document.createElement('button'),cancel=document.createElement('button');
    actions.className='editor-inline-actions';save.type=cancel.type='button';save.textContent='完成';cancel.textContent='取消';actions.append(save,cancel);
    input.className = 'editor-inline-input';
    input.setAttribute('aria-label', '原位编辑标签');
    const originalText=relation?relationLabel(this.doc,o):o.label;
    input.value = originalText;
    const width=Math.min(Math.max(130,rect.width+20),Math.max(130,this.host.clientWidth-20));
    const left=Math.max(0,Math.min(rect.left-host.left-5,this.host.clientWidth-width-10)),top=Math.max(0,rect.top-host.top-5);
    Object.assign(input.style, {
      left: left + 'px',
      top: top + 'px',
      width: width + 'px',
      fontSize: Math.max(12, rect.height) + 'px'
    });
    Object.assign(actions.style,{left:left+'px',top:(top+Math.max(34,rect.height+16)+5)+'px'});
    this.host.append(input,actions);
    const actionTop=top+(input.offsetHeight||Math.max(34,rect.height+16))+6;
    actions.style.top=(actionTop+42>this.host.clientHeight?Math.max(0,top-42):actionTop)+'px';
    input.focus();
    input.select();
    let done = false;
    const finish = save => {
      if (done) return;
      done = true;
      const value = input.value;
      input.remove();
      actions.remove();
      if (save && value !== originalText) this.applyOperations([{ op: relation?'update_relation':'update', id: o.id, changes: { label: value } }], '编辑标签');
      else {
        this.drawOverlay();
        this.onSelection(this.selectedIds);
      }
      this.host.focus({preventScroll:true});
    };
    actions.onpointerdown=actions.onmousedown=e=>e.stopPropagation();
    save.onpointerdown=cancel.onpointerdown=e=>{e.preventDefault();e.stopPropagation();};
    save.onmousedown=cancel.onmousedown=e=>{e.preventDefault();e.stopPropagation();};
    save.onclick=e=>{e.stopPropagation();finish(true);};
    cancel.onclick=e=>{e.stopPropagation();finish(false);};
    input.onblur = e => {if(!actions.contains(e?.relatedTarget))finish(true);};
    actions.onfocusout=e=>{if(e.relatedTarget!==input&&!actions.contains(e.relatedTarget))finish(true);};
    input.onkeydown = e => {
      e.stopPropagation();
      if (e.key === 'Enter') { e.preventDefault(); finish(true); }
      if (e.key === 'Escape') { e.preventDefault(); finish(false); }
    };
  }

  editSelectedLabel(){
    const id=this.selectedIds[0];
    const label=[...this.host.querySelectorAll('[data-label-for],[data-relation-label-for]')].find(n=>(n.getAttribute('data-label-for')||n.getAttribute('data-relation-label-for'))===id);
    if(label)this.editLabel({target:label,preventDefault(){}});
  }

  bringToFront() {
    if (!this.doc || !this.selected.size) return;
    const nonSel = this.doc.objects.filter(o => !this.selected.has(o.id)).map(o => o.id);
    const sel = this.doc.objects.filter(o => this.selected.has(o.id)).map(o => o.id);
    this.applyOperations([{ op: 'reorder', ids: [...nonSel, ...sel] }], '置于顶层');
  }

  sendToBack() {
    if (!this.doc || !this.selected.size) return;
    const nonSel = this.doc.objects.filter(o => !this.selected.has(o.id)).map(o => o.id);
    const sel = this.doc.objects.filter(o => this.selected.has(o.id)).map(o => o.id);
    this.applyOperations([{ op: 'reorder', ids: [...sel, ...nonSel] }], '置于底层');
  }

  initContextMenu() {
    const menu = document.getElementById('canvas-context-menu');
    if (!menu || menu._inited) return;
    menu._inited = true;
    menu.addEventListener('keydown',e=>{if(!['ArrowDown','ArrowUp','Home','End','Escape'].includes(e.key))return;e.preventDefault();e.stopPropagation();if(e.key==='Escape'){menu.hidden=true;this.host.focus({preventScroll:true});return;}const items=[...menu.querySelectorAll('button')].filter(n=>!n.hidden&&!n.disabled);if(!items.length)return;const current=items.indexOf(document.activeElement),index=e.key==='Home'?0:e.key==='End'?items.length-1:(current+(e.key==='ArrowUp'?-1:1)+items.length)%items.length;items[index].focus();});
    document.getElementById('ctx-edit-label')?.addEventListener('click', () => { menu.hidden = true; this.editSelectedLabel(); });
    document.getElementById('ctx-duplicate')?.addEventListener('click', () => { menu.hidden = true; this.duplicateSelection(); });
    document.getElementById('ctx-bring-front')?.addEventListener('click', () => { menu.hidden = true; this.bringToFront(); });
    document.getElementById('ctx-send-back')?.addEventListener('click', () => { menu.hidden = true; this.sendToBack(); });
    document.getElementById('ctx-connect-to')?.addEventListener('click', () => { menu.hidden = true; this.setTool('connect'); });
    document.getElementById('ctx-insert-legend')?.addEventListener('click', () => { menu.hidden = true; document.getElementById('insert-legend')?.click(); });
    document.getElementById('ctx-delete')?.addEventListener('click', () => { menu.hidden = true; this.deleteSelection(); });
  }

  openContextMenu(e) {
    if (!this.doc) return;
    e.preventDefault();
    this.initContextMenu();
    const menu = document.getElementById('canvas-context-menu');
    if (!menu) return;

    const point = this.world(e);
    const relation=e.target.closest?.('[data-relation-id]')?.dataset.relationId;
    if(relation&&!this.selected.has(relation))this.setSelection([relation]);
    const direct=e.target.closest?.('[data-object-id]')?.dataset.objectId;
    const hits = relation?[]:hitObjects(this.doc, point);
    const hitObj = this.doc.objects.find(o=>o.id===direct)||hits[0];
    if (hitObj && !this.selected.has(hitObj.id)) {
      this.setSelection([hitObj.id]);
    }
    if(!hitObj&&!relation)this.setSelection([]);

    const hasSelection = this.selected.size > 0;
    const isObject = this.selected.size === 1 && this.doc.objects.some(o => this.selected.has(o.id));

    const editLabelItem = document.getElementById('ctx-edit-label');
    const duplicateItem = document.getElementById('ctx-duplicate');
    const bringFrontItem = document.getElementById('ctx-bring-front');
    const sendBackItem = document.getElementById('ctx-send-back');
    const connectToItem = document.getElementById('ctx-connect-to');
    const deleteItem = document.getElementById('ctx-delete');

    if (editLabelItem) editLabelItem.hidden = !isObject;
    const hasObjects=this.doc.objects.some(o=>this.selected.has(o.id)&&!o.locked);
    if (duplicateItem) duplicateItem.hidden = !hasObjects;
    if (bringFrontItem) bringFrontItem.hidden = !hasObjects;
    if (sendBackItem) sendBackItem.hidden = !hasObjects;
    if (connectToItem) connectToItem.hidden = !isObject;
    if (deleteItem) deleteItem.hidden = !hasSelection;

    menu.style.left = `${Math.min(window.innerWidth - 180, e.clientX)}px`;
    menu.style.top = `${Math.min(window.innerHeight - 240, e.clientY)}px`;
    menu.hidden = false;
    menu.querySelector('button:not([hidden]):not(:disabled)')?.focus({preventScroll:true});

    const closeMenu = (evt) => {
      if (!menu.contains(evt.target)) {
        menu.hidden = true;
        document.removeEventListener('pointerdown', closeMenu);
      }
    };
    setTimeout(() => document.addEventListener('pointerdown', closeMenu), 10);
  }

  key(e) {
    if (!this.doc || e.defaultPrevented || isInput(e)) return;
    const mod = e.ctrlKey || e.metaKey, key = e.key.toLowerCase();
    if(!mod&&e.target.closest('button,summary'))return;
    if(this.gesture&&mod&&['z','y'].includes(key)){e.preventDefault();this.cancelGesture();return;}
    if(e.shiftKey&&!mod&&e.code==='Digit1'){e.preventDefault();this.fit();return;}
    if(e.shiftKey&&!mod&&e.code==='Digit2'){e.preventDefault();this.fitSelection();return;}
    if (e.code === 'Space') {
      e.preventDefault();
      this.space = true;
      return;
    }
    if (mod && key === 'z') {
      e.preventDefault();
      e.shiftKey ? this.redo() : this.undo();
    } else if (mod && key === 'y') {
      e.preventDefault();
      this.redo();
    } else if (mod && key === 'a') {
      e.preventDefault();this.setSelection(this.doc.objects.filter(o=>o.visible&&!o.locked&&o.role!=='context').map(o=>o.id));
    } else if (mod && key === 'd') {
      e.preventDefault();
      this.duplicateSelection();
    } else if (mod && key === 'c') {
      e.preventDefault();this.clipboard=copy({objects:this.doc.objects.filter(o=>this.selected.has(o.id)),relations:this.doc.relations.filter(r=>this.selected.has(r.source)&&this.selected.has(r.target))});
    } else if (mod && key === 'v' && this.clipboard?.objects.length) {
      e.preventDefault();
      const ids=new Map(this.clipboard.objects.map(o=>[o.id,uid('o')])),groups=new Map();
      const ops=this.clipboard.objects.map(o=>{if(o.group_id&&!groups.has(o.group_id))groups.set(o.group_id,uid('group'));return {op:'add',object:{...copy(o),id:ids.get(o.id),x:o.x+5,y:o.y+5,group_id:groups.get(o.group_id)||''}};});
      for(const r of this.clipboard.relations)ops.push({op:'add_relation',relation:{...copy(r),id:uid('r'),source:ids.get(r.source),target:ids.get(r.target),...(r.control?{control:{x:r.control.x+5,y:r.control.y+5}}:{}),...(r.label_position?{label_position:{x:r.label_position.x+5,y:r.label_position.y+5}}:{})}});
      this.applyOperations(ops, '粘贴');
      this.setSelection([...ids.values()]);
    } else if (['Delete', 'Backspace'].includes(e.key)) {
      e.preventDefault();
      this.deleteSelection();
    } else if (!mod && key === 'v') {
      this.setTool('select');
    } else if (!mod && key === 'h') {
      this.setTool('pan');
    } else if (!mod && key === 'c') {
      this.setTool('connect');
    } else if (e.key === 'F2') {
      e.preventDefault();this.editSelectedLabel();
    } else if (e.key === 'Escape') {
      if(this.gesture){this.cancelGesture();return;}
      if(this.tool!=='select'){this.setTool('select');return;}
      this.setSelection([]);
    } else if (e.key.startsWith('Arrow') && this.selected.size) {
      e.preventDefault();
      const delta = e.shiftKey ? 2 : .5;
      const dx=e.key==='ArrowRight'?delta:e.key==='ArrowLeft'?-delta:0,dy=e.key==='ArrowDown'?delta:e.key==='ArrowUp'?-delta:0;
      if(this.activeLabel&&this.selected.size===1&&this.selected.has(this.activeLabel.id)){
        const {kind,id}=this.activeLabel;
        if(kind==='relation'){const r=this.doc.relations.find(r=>r.id===id),p=edgeGeometry(this.doc,r).label;this.applyOperations([{op:'update_relation',id,changes:{label_position:{x:p.x+dx,y:p.y+dy}}}],'微调文字');}
        else{const o=this.doc.objects.find(o=>o.id===id);if(o&&!o.locked)this.applyOperations([{op:'update',id,changes:{label_dx:(o.label_dx||0)+dx,label_dy:(o.label_dy||0)+dy}}],'微调文字');}
        return;
      }
      this.applyOperations(this.doc.objects.filter(o => this.selected.has(o.id) && !o.locked).map(o => ({
        op: 'update', id: o.id,
        changes: {
          x: o.x + (e.key === 'ArrowRight' ? delta : e.key === 'ArrowLeft' ? -delta : 0),
          y: o.y + (e.key === 'ArrowDown' ? delta : e.key === 'ArrowUp' ? -delta : 0)
        }
      })), '微调位置');
    }
  }
}
