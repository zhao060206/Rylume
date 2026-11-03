/** Recognize only independent closed rectangular refinement regions. */
export function rectangleFragments(d){
 const chunks=(d||'').match(/M[^M]+/gi)||[];if(chunks.length<2)return null;
 const result=[];for(const text of chunks){const n=text.match(/^M\s*([-\d.]+)[ ,]+([-\d.]+)\s*h\s*([-\d.]+)\s*v\s*([-\d.]+)\s*h\s*([-\d.]+)\s*Z\s*$/i);if(n){const[x,y,w,h,back]=n.slice(1).map(Number);if(![x,y,w,h,back].every(Number.isFinite)||Math.abs(w+back)>.001)return null;result.push({text,box:{x,y,w,h}});continue;}
  const a=text.match(/[a-z]|[-+]?(?:\d*\.)?\d+(?:e[-+]?\d+)?/gi)||[];if(a.length!==13||a[0]!=='M'||a[12].toUpperCase()!=='Z'||!['l','L'].includes(a[3])||!['l','L'].includes(a[6])||!['l','L'].includes(a[9]))return null;
  let x=Number(a[1]),y=Number(a[2]);const points=[[x,y]];for(const i of [3,6,9]){const dx=Number(a[i+1]),dy=Number(a[i+2]);x=a[i]==='l'?x+dx:dx;y=a[i]==='l'?y+dy:dy;points.push([x,y]);}const xs=[...new Set(points.map(p=>p[0]))],ys=[...new Set(points.map(p=>p[1]))];if(xs.length!==2||ys.length!==2)return null;result.push({text,box:{x:Math.min(...xs),y:Math.min(...ys),w:Math.abs(xs[1]-xs[0]),h:Math.abs(ys[1]-ys[0])}});
 }return result;
}
