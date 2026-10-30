/** Relevance and presentation never change scientific identity or provenance. */
const synonyms=[['受体','receptor','gpcr','rtk'],['细胞核','nucleus','nuclear'],['线粒体','mitochondria','mitochondrion'],['囊泡','vesicle'],['配体','ligand','cytokine','细胞因子'],['激酶','kinase'],['蛋白','protein'],['抗体','antibody'],['质膜','plasma membrane','细胞膜'],['核孔','nuclear pore'],['内质网','endoplasmic reticulum'],['高尔基体','golgi'],['巨噬细胞','macrophage'],['转录因子','transcription factor'],['核糖体','ribosome'],['内吞','endocytosis'],['胞吐','exocytosis']];
const normalized=s=>String(s||'').toLowerCase().replace(/[_-]+/g,' ').replace(/\s+/g,' ').trim();
export const assetKey=a=>a.asset_id||a.type;
export function assetStyle(a){return !a.asset_id?'native':/servier/i.test((a.author||'')+' '+(a.source_url||''))?'detailed':'flat';}
export function assetDisplayName(a){
  let label=String(a.label||a.type).replace(/_/g,' ').replace(/\s+/g,' ').trim();
  const translations={'ions':'离子','pink transporter':'转运蛋白 · 粉色','simple receptor':'受体示意','cell membrane semi circle':'细胞膜截面','t cell receptor':'T 细胞受体'};
  for(const[from,to]of Object.entries(translations))if(normalized(label).startsWith(from))label=to+label.slice(from.length);
  label=label.replace(/^受体\s*·\s*simple receptor\s*(\d*)$/i,(_,n)=>'受体示意'+(n?' · '+n:''))
    .replace(/^细胞 受体\s*·\s*t cell receptor$/i,'T 细胞受体');
  if(label.startsWith('离子'))for(const[from,to]of Object.entries({blue:'蓝色',darkmagenta:'深洋红',gray:'灰色',green:'绿色',white:'白色'}))label=label.replace(new RegExp('\\b'+from+'\\b','gi'),to);
  return label;
}
export function rankAssets(assets,{domain='biology',category='',query='',style='',favorites=[],recent=[],view='all'}={}){
  const q=normalized(query),aliases=new Set([q]);
  for(const group of synonyms)if(group.some(t=>normalized(t)===q))group.forEach(t=>aliases.add(normalized(t)));
  const favorite=new Set(favorites),recency=new Map(recent.map((id,i)=>[id,recent.length-i]));
  return assets.map((a,index)=>{
    const key=assetKey(a),label=normalized(a.label),display=normalized(assetDisplayName(a)),keywords=normalized(Array.isArray(a.keywords)?a.keywords.join(' '):a.keywords),type=normalized(a.type),categoryName=normalized(a.category);
    const kit=view==='signaling'?['ligand','receptor','receptor_dimer','gpcr','kinase','protein','lipid','tf','dna','mrna','membrane','nucleus','nuclear_pore']:view==='trafficking'?['cell','membrane','nucleus','vesicle','mvb','vesicle_fusion','mitochondrion','golgi','er']:null;
    if((a.domain||'biology')!==domain||(category&&a.category!==category)||(style&&assetStyle(a)!==style)||(view==='favorites'&&!favorite.has(key))||(view==='recent'&&!recency.has(key))||(kit&&(a.asset_id||!kit.includes(a.type))))return null;
    let score=q?-1:0;
    if(q)for(const term of aliases){
      const exact=term===q;
      if(label===term||display===term)score=Math.max(score,exact?120:105);
      else if(label.startsWith(term)||display.startsWith(term))score=Math.max(score,exact?100:90);
      else if(label.includes(term)||display.includes(term))score=Math.max(score,exact?85:75);
      if(type===term)score=Math.max(score,65);
      if(keywords.includes(term))score=Math.max(score,55);
      if(categoryName.includes(term))score=Math.max(score,5);
    }
    if(score<0)return null;
    return {a,index,score:score*10000+(view==='recent'?(recency.get(key)||0)*100:0)+(!a.asset_id?100:0)+(favorite.has(key)?10:0)};
  }).filter(Boolean).sort((a,b)=>b.score-a.score||a.index-b.index).map(x=>x.a);
}
