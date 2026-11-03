/** Cached display layers for complete structures; source/export stays vector. */
const intersects=(a,b)=>a.x<=b.x+b.w&&a.x+a.w>=b.x&&a.y<=b.y+b.h&&a.y+a.h>=b.y;
function unionBounds(a,b){if(!a)return {...b};const x=Math.min(a.x,b.x),y=Math.min(a.y,b.y);return{x,y,w:Math.max(a.x+a.w,b.x+b.w)-x,h:Math.max(a.y+a.h,b.y+b.h)-y};}
export function patchColor(colors,u,v){const rgb=colors.map(c=>[1,3,5].map(i=>parseInt(c.slice(i,i+2),16)));const value=[0,1,2].map(i=>Math.round(rgb[0][i]*(1-u)*(1-v)+rgb[1][i]*u*(1-v)+rgb[2][i]*(1-u)*v+rgb[3][i]*u*v));return '#'+value.map(n=>n.toString(16).padStart(2,'0')).join('');}
export function patchRects(background){const {x,y,w,h,colors}=background,result=[];for(let j=0;j<8;j++)for(let i=0;i<8;i++)result.push({x:x+i*w/8,y:y+j*h/8,w:w/8+.002,h:h/8+.002,fill:patchColor(colors,(i+.5)/8,(j+.5)/8)});return result;}
const canvas=(w,h)=>{const c=document.createElement('canvas');c.width=w;c.height=h;return c;};
function draw(ctx,items,s,ox=0,oy=0){for(const p of items){const m=p.baseMatrix||p.matrix;ctx.setTransform(s*m.a,s*m.b,s*m.c,s*m.d,s*m.e-ox,s*m.f-oy);if(p.fill!=='none'){ctx.globalAlpha=p.alpha*p.fillAlpha;ctx.fillStyle=p.fill;ctx.fill(p.path,p.rule);}if(p.stroke!=='none'&&p.lineWidth>0){ctx.globalAlpha=p.alpha*p.strokeAlpha;ctx.strokeStyle=p.stroke;ctx.lineWidth=p.lineWidth;ctx.lineCap=p.lineCap;ctx.lineJoin=p.lineJoin;ctx.stroke(p.path);}}ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;}
export function backgroundPatch(surface,box){
 const s=surface.scale,ctx=surface.ctx,pad=.35,region={x:box.x-pad,y:box.y-pad,w:box.w+pad*2,h:box.h+pad*2};
 const sample=(u,v)=>{const x=Math.max(0,Math.min(surface.canvas.width-7,Math.round((region.x+region.w*u)*s)-3)),y=Math.max(0,Math.min(surface.canvas.height-7,Math.round((region.y+region.h*v)*s)-3)),pixels=ctx.getImageData(x,y,7,7).data,values=[];for(let i=0;i<pixels.length;i+=4)if(pixels[i+3]>200&&Math.min(pixels[i],pixels[i+1],pixels[i+2])>175)values.push([pixels[i],pixels[i+1],pixels[i+2]]);return values;};
 const ring=[];for(let i=0;i<=12;i++){const t=i/12;ring.push(...sample(t,0),...sample(t,1),...sample(0,t),...sample(1,t));}
 // Estimate the surrounding background, rejecting nearby blue label boxes or
 // other foreground colours at a corner instead of painting their colour over
 // the old structure. Hidden image content cannot be recovered exactly.
 const buckets=new Map();for(const c of ring){const key=c.map(v=>Math.round(v/16)).join(':');if(!buckets.has(key))buckets.set(key,[]);buckets.get(key).push(c);}
 const values=[...buckets.values()].sort((a,b)=>b.length-a.length)[0]||[[250,250,246]],median=list=>[0,1,2].map(k=>list.map(c=>c[k]).sort((a,b)=>a-b)[Math.floor(list.length/2)]),dominant=median(values),colors=[];
 for(const[u,v]of[[0,0],[1,0],[0,1],[1,1]]){const candidates=sample(u,v).filter(c=>Math.hypot(...c.map((n,k)=>n-dominant[k]))<24&&Math.abs((c[0]-c[2])-(dominant[0]-dominant[2]))<22),color=candidates.length?median(candidates):dominant;colors.push('#'+color.map(v=>v.toString(16).padStart(2,'0')).join(''));}
 return{...region,colors};
}
export class StructureCompositor{
 constructor(surface){this.surface=surface;this.signature=null;this.original=null;}
 invalidate(preserve=false){this.signature=null;if(!preserve)this.original=null;this.mountedSignature=null;}
 build(groups){const signature=JSON.stringify(groups.map(g=>[g.id,g.parts,g.background,g.visible]));if(signature===this.signature)return;this.signature=signature;const surface=this.surface,s=surface.scale,w=surface.canvas.width,h=surface.canvas.height,index=surface.index,members=new Set(),layers=[];for(const p of surface.items)p.structureId=null;
  for(const g of groups){let box=null;const items=[];for(const part of g.parts)for(const i of part.indices){const p=index.get(part.owner+':'+i);if(!p)continue;members.add(p);items.push(p);p.structureId=g.id;box=unionBounds(box,p.baseBox);}if(!box||g.visible===false)continue;items.sort((a,b)=>a.order-b.order);box={x:Math.floor(box.x*s)/s-.1,y:Math.floor(box.y*s)/s-.1,w:Math.ceil(box.w*s)/s+.2,h:Math.ceil(box.h*s)/s+.2};const texture=canvas(Math.ceil(box.w*s),Math.ceil(box.h*s));draw(texture.getContext('2d'),items,s,box.x*s,box.y*s);layers.push({id:g.id,box,canvas:texture});}
  this.base=canvas(w,h);const ctx=this.base.getContext('2d');if(this.original&&groups.every(g=>g.background))ctx.drawImage(this.original,0,0);else draw(ctx,surface.items.filter(p=>!members.has(p)),s);ctx.setTransform(s,0,0,s,0,0);for(const g of groups)if(g.background)for(const r of patchRects(g.background)){ctx.fillStyle=r.fill;ctx.fillRect(r.x,r.y,r.w,r.h);}ctx.setTransform(1,0,0,1,0,0);
  this.foreground=canvas(w,h);const foregroundKeys=new Set(groups.flatMap(g=>(g.foreground||[]).flatMap(part=>part.indices.map(i=>part.owner+':'+i))));const foreground=surface.items.filter(p=>!members.has(p)&&foregroundKeys.has(p.owner+':'+p.index));
  this.foregroundKeys=new Set(foreground.map(p=>p.owner+':'+p.index));draw(this.foreground.getContext('2d'),foreground,s);this.layers=layers;
 }
 frame(groups,preview=null){const result=canvas(this.surface.canvas.width,this.surface.canvas.height),ctx=result.getContext('2d'),s=this.surface.scale;ctx.drawImage(this.surface.canvas,0,0);if(this.mountedSignature){const lookup=new Map(groups.map(g=>[g.id,g]));for(const layer of this.layers){const g=lookup.get(layer.id),d=preview?.get(layer.id);if(g)ctx.drawImage(layer.canvas,(layer.box.x+(g.dx||0)+(d?.dx||0))*s,(layer.box.y+(g.dy||0)+(d?.dy||0))*s);}ctx.drawImage(this.foreground,0,0);}return result;}
 paint(groups,preview=null){const surface=this.surface,ctx=surface.ctx,s=surface.scale;
  if(!this.original){this.original=canvas(surface.canvas.width,surface.canvas.height);draw(this.original.getContext('2d'),surface.items,s);}
  const active=groups.filter(g=>{const p=preview?.get(g.id);return g.visible===false||Math.abs((g.dx||0)+(p?.dx||0))>1e-7||Math.abs((g.dy||0)+(p?.dy||0))>1e-7;});
  if(!active.length){if(this.mountedSignature!==false){this.root?.remove();ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,surface.canvas.width,surface.canvas.height);ctx.drawImage(this.original,0,0);this.mountedSignature=false;}return;}
  this.build(active);
  if(this.mountedSignature!==this.signature||!this.root?.isConnected){this.root?.remove();this.root=document.createElementNS('http://www.w3.org/2000/svg','g');this.root.setAttribute('data-structure-display','true');this.root.setAttribute('pointer-events','none');
   const foreign=(texture,box)=>{const n=document.createElementNS('http://www.w3.org/2000/svg','foreignObject');for(const[k,v]of Object.entries({x:box.x,y:box.y,width:texture.width/s,height:texture.height/s}))n.setAttribute(k,v);texture.style.cssText='width:100%;height:100%;display:block;pointer-events:none';n.append(texture);this.root.append(n);return n;};
   for(const layer of this.layers)layer.foreign=foreign(layer.canvas,layer.box);foreign(this.foreground,{x:0,y:0});surface.foreign.after(this.root);ctx.setTransform(1,0,0,1,0,0);ctx.clearRect(0,0,surface.canvas.width,surface.canvas.height);ctx.drawImage(this.base,0,0);this.mountedSignature=this.signature;
  }
  const lookup=new Map(active.map(g=>[g.id,g]));for(const layer of this.layers){const g=lookup.get(layer.id),d=preview?.get(layer.id);layer.foreign.setAttribute('transform',`translate(${(g.dx||0)+(d?.dx||0)} ${(g.dy||0)+(d?.dy||0)})`);}
 }
}
