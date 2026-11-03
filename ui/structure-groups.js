import {rectangleFragments} from './path-rectangles.js';
import {matrixBounds,intersects} from './traced-surface.js';
const SHAPES='path,rect,circle,ellipse,line,polyline,polygon';
export const containsBounds=(a,b,pad=.15)=>b.x>=a.x-pad&&b.y>=a.y-pad&&b.x+b.w<=a.x+a.w+pad&&b.y+b.h<=a.y+a.h+pad;
export function inferStructureRegion(hit,items,canvas,inside){
 const seed=hit.box,center={x:seed.x+seed.w/2,y:seed.y+seed.h/2},max=canvas.width_mm*canvas.height_mm*.16;
 const anchors=items.filter(p=>p.fill!=='none'&&p.box.w*p.box.h>=.8&&p.box.w*p.box.h<=max&&Math.max(p.box.w,p.box.h)/Math.max(.01,Math.min(p.box.w,p.box.h))<18&&containsBounds(p.box,seed,.5)&&inside(p,center));
 anchors.sort((a,b)=>b.box.w*b.box.h-a.box.w*a.box.h);return anchors[0]?.box||(seed.w*seed.h<=max?seed:null);
}
/** Refinement rectangles may share one colour path across distant structures.
 * Split only these independent closed rectangles, never a contour with holes.
 */
export {rectangleFragments} from './path-rectangles.js';
export function makeStructure(scene,entries,region,label='独立结构'){
 const owners=new Map(),lookup=new Map(entries.map(p=>[p.owner+':'+p.index,p]));
 for(const p of entries)if(intersects(p.box,region)){
  if(!owners.has(p.owner)){const object=scene.objects.find(o=>o.id===p.owner),root=new DOMParser().parseFromString(object.asset_snapshot.svg,'image/svg+xml').documentElement;owners.set(p.owner,{object,root,original:[...root.querySelectorAll(SHAPES)],selected:new Set(),mapping:new Map()});}
 }
 const parts=[],updates=[];
 for(const [owner,data]of owners){let changed=false;for(let i=0;i<data.original.length;i++){const n=data.original[i],p=lookup.get(owner+':'+i);if(!p)continue;if(containsBounds(region,p.box)){data.selected.add(n);continue;}
   const pieces=n.localName==='path'&&intersects(region,p.box)?rectangleFragments(n.getAttribute('d')):null;if(!pieces)continue;
   const yes=[],no=[];for(const piece of pieces)(containsBounds(region,matrixBounds(piece.box,p.matrix),.08)?yes:no).push(piece.text);
   if(!yes.length)continue;if(!no.length){data.selected.add(n);continue;}
   n.setAttribute('d',no.join(''));const fragment=n.cloneNode(true);fragment.setAttribute('d',yes.join(''));n.after(fragment);data.selected.add(fragment);changed=true;
  }
  const nodes=[...data.root.querySelectorAll(SHAPES)],indices=[];nodes.forEach((n,i)=>{if(data.selected.has(n))indices.push(i);});data.original.forEach((n,i)=>data.mapping.set(i,nodes.indexOf(n)));
  if(!indices.length)continue;parts.push({owner,indices});
  if(changed)updates.push({op:'update',id:owner,changes:{asset_snapshot:{...data.object.asset_snapshot,svg:new XMLSerializer().serializeToString(data.root)}}});
 }
 if(!parts.length)return null;
 const occupied=new Set(parts.flatMap(p=>p.indices.map(i=>p.owner+':'+i))),structures=[];
 for(const g of scene.structures||[]){const members=[];for(const p of g.parts){const map=owners.get(p.owner)?.mapping;const indices=p.indices.map(i=>map?.get(i)??i).filter(i=>!occupied.has(p.owner+':'+i));if(indices.length)members.push({owner:p.owner,indices});}if(members.length)structures.push({...g,parts:members,foreground:(g.foreground||[]).map(p=>({...p,indices:p.indices.map(i=>owners.get(p.owner)?.mapping.get(i)??i)}))});}
 const foreground=[];for(const p of entries){const b=p.baseBox||p.box,index=owners.get(p.owner)?.mapping.get(p.index)??p.index;if(occupied.has(p.owner+':'+index))continue;
  const dark=(p.fill?.startsWith('#')&&[1,3,5].map(i=>parseInt(p.fill.slice(i,i+2),16)).every(n=>n<145))||p.fill==='none'&&p.stroke!=='none';
  if(dark&&intersects(b,region)&&Math.max(b.w,b.h)>2&&Math.max(b.w,b.h)/Math.max(.01,Math.min(b.w,b.h))>2&&b.w*b.h<scene.canvas.width_mm*scene.canvas.height_mm*.16){let part=foreground.find(v=>v.owner===p.owner);if(!part){part={owner:p.owner,indices:[]};foreground.push(part);}part.indices.push(index);}
 }
 const group={id:'structure_'+crypto.randomUUID().replaceAll('-','').slice(0,16),label,parts,foreground};structures.push(group);updates.push({op:'set_structures',structures});return {group,operations:updates};
}
