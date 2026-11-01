/** Relevance and presentation never change scientific identity or provenance. */
const synonyms=[['受体','receptor','receptors'],['G蛋白偶联受体','gpcr','七次跨膜受体'],['受体酪氨酸激酶','rtk'],
 ['细胞核','nucleus','nuclear','xibaohe','xbh'],['线粒体','mitochondria','mitochondrion','xianliti','xlt'],
 ['囊泡','vesicle','vesicles'],['配体','ligand'],['细胞因子','cytokine'],['激酶','kinase'],['蛋白','protein'],
 ['抗体','antibody','antibodies','kangti'],['质膜','plasma membrane','细胞膜','xibaomo'],['核孔','nuclear pore'],
 ['内质网','endoplasmic reticulum','endoplasmatic reticulum','neizhiwang','nzw'],['高尔基体','golgi','gaoerjiti','gejt'],
 ['巨噬细胞','macrophage','jushixibao','jsxb'],['转录因子','transcription factor'],['核糖体','ribosome','hetangti'],
 ['内吞','endocytosis'],['胞吐','exocytosis'],['吞噬','phagocytosis'],['细胞凋亡','apoptosis','凋亡'],
 ['自噬','autophagy'],['溶酶体','lysosome'],['外泌体','exosome','胞外囊泡'],['叶绿体','chloroplast'],
 ['干细胞','stem cell'],['造血干细胞','hematopoietic stem cell','hsc'],['神经元','neuron','neurons','shenjingyuan'],
 ['星形胶质细胞','astrocyte'],['小胶质细胞','microglia'],['突触','synapse'],['轴突','axon'],
 ['T细胞','T 细胞','t cell','t lymphocyte','T淋巴细胞'],['B细胞','B 细胞','b cell','b lymphocyte','B淋巴细胞'],
 ['树突状细胞','dendritic cell'],['中性粒细胞','neutrophil'],['红细胞','erythrocyte','red blood cell','rbc'],
 ['血小板','platelet','thrombocyte'],['成纤维细胞','fibroblast'],['内皮细胞','endothelial cell'],
 ['心脏','heart','xinzang'],['肺','lung','lungs'],['肝脏','liver'],['肾脏','kidney','kidneys'],['脑','brain'],
 ['肿瘤','tumor','tumour'],['癌细胞','cancer cell'],['血管新生','angiogenesis'],['胶原','collagen'],
 ['小鼠','mouse','mice','xiaoshu'],['大鼠','rat','rats'],['斑马鱼','zebrafish'],['果蝇','drosophila','fruit fly'],
 ['拟南芥','arabidopsis'],['酵母','yeast'],['细菌','bacteria','bacterium'],['病毒','virus','viruses'],['噬菌体','phage','bacteriophage'],
 ['显微镜','microscope','xianweijing','xwj'],['共聚焦','confocal'],['离心机','centrifuge','lixinji','lxj'],
 ['移液器','pipette','micropipette','yiyeqi','yyq'],['培养皿','petri dish'],['烧瓶','flask'],['烧杯','beaker'],
 ['离心管','eppendorf','microcentrifuge tube'],['培养箱','incubator'],['电泳','electrophoresis'],
 ['测序','sequencing'],['转录','transcription','transkription'],['翻译','translation'],['质粒','plasmid'],
 ['染色体','chromosome'],['染色质','chromatin'],['核小体','nucleosome'],['组蛋白','histone'],
 ['信使RNA','mrna','信使 RNA'],['转运RNA','trna','转运 RNA'],['微小RNA','microrna','miRNA'],
 ['氨基酸','amino acid'],['甘氨酸','glycine'],['丙氨酸','alanine'],['赖氨酸','lysine'],['丝氨酸','serine'],
 ['纳米颗粒','nanoparticle','nanoparticles'],['神经网络','neural network'],['数据库','database'],['数据集','dataset']];
const normalized=s=>String(s||'').normalize('NFKC').replace(/([a-z])([A-Z])/g,'$1 $2').toLowerCase()
 .normalize('NFD').replace(/\p{M}/gu,'').replace(/\b([a-z]+)[\s_-]+(\d+)\b/g,'$1$2')
 .replace(/[^\p{L}\p{N}]+/gu,' ').replace(/\s+/g,' ').trim();
const aliases=new Map();for(const group of synonyms){const terms=group.map(normalized);for(const term of terms)aliases.set(term,terms);}
const indexes=new WeakMap();

function searchIndex(asset){
 const signature=[asset.label,asset.label_zh,asset.label_en,asset.type,asset.category,JSON.stringify(asset.keywords),JSON.stringify(asset.aliases)].join('|');
 const old=indexes.get(asset);if(old?.signature===signature)return old;
 const name=normalized(asset.label),display=normalized(assetDisplayName(asset));
 const keywords=normalized([asset.label_en,Array.isArray(asset.keywords)?asset.keywords.join(' '):asset.keywords,Array.isArray(asset.aliases)?asset.aliases.join(' '):asset.aliases].filter(Boolean).join(' '));
 const category=normalized(asset.category),type=normalized(asset.type);
 const words=[...new Set([name,display,keywords,type].flatMap(v=>v.split(' ')))].filter(v=>v&&v.length<=64);
 const value={signature,name,display,keywords,category,type,words};indexes.set(asset,value);return value;
}

/** Bounded edit distance, including adjacent transpositions such as recpetor. */
export function editDistance(a,b,limit=2){
 if(a===b)return 0;if(Math.abs(a.length-b.length)>limit)return limit+1;
 let prior=Array.from({length:b.length+1},(_,i)=>i),before=null;
 for(let i=1;i<=a.length;i++){
  const row=[i];let minimum=i;
  for(let j=1;j<=b.length;j++){
   let n=Math.min(row[j-1]+1,prior[j]+1,prior[j-1]+(a[i-1]===b[j-1]?0:1));
   if(before&&i>1&&j>1&&a[i-1]===b[j-2]&&a[i-2]===b[j-1])n=Math.min(n,before[j-2]+1);
   row.push(n);minimum=Math.min(minimum,n);
  }
  if(minimum>limit)return limit+1;before=prior;prior=row;
 }return prior[b.length];
}

function contains(value,term){
 // CD4/CD45 and IL6/IL8 are distinct identities, including in search results.
 return /\d/.test(term)?value.split(' ').includes(term):value.includes(term);
}
function strictScore(index,term){
 if(index.name===term||index.display===term)return 120;
 if(contains(index.name,term)||contains(index.display,term))return index.name.startsWith(term)||index.display.startsWith(term)?100:85;
 if(index.type===term)return 65;
 if(contains(index.keywords,term))return 55;
 if(contains(index.category,term))return 5;return -1;
}
function approximate(index,term){
 const chinese=/\p{Script=Han}/u.test(term);
 // Short scientific abbreviations and numbered markers never receive typo substitutions.
 if(/\d/.test(term)||term.length<(chinese?3:5))return -1;
 const limit=chinese?1:term.length>=8?2:1;let best=limit+1;
 for(const word of index.words){
  if(chinese!==/\p{Script=Han}/u.test(word)||/\d/.test(word))continue;
  if(chinese&&word.length>term.length+1){
   for(let i=0;i<=word.length-term.length;i++)best=Math.min(best,editDistance(term,word.slice(i,i+term.length),limit));
  }else{
   best=Math.min(best,editDistance(term,word,limit));
   if(!chinese&&word.length>term.length+limit)best=Math.min(best,editDistance(term,word.slice(0,term.length),limit));
  }
  if(best===0)break;
 }return best<=limit?38-best*7:-1;
}
function termMatch(index,term,fuzzy){
 let score=strictScore(index,term),kind='exact';
 for(const alias of aliases.get(term)||[]){const n=strictScore(index,alias)-15;if(n>score){score=n;kind='alias';}}
 if(score<0&&fuzzy){score=approximate(index,term);kind='fuzzy';}
 return {score,kind};
}
export function assetMatch(asset,query,{fuzzy=true}={}){
 const q=normalized(query);if(!q)return {score:0,kind:'exact'};
 const index=searchIndex(asset),whole=termMatch(index,q,false);
 if(whole.score>=0)return whole;
 const parts=q.split(' ').map(t=>termMatch(index,t,fuzzy));
 if(parts.some(p=>p.score<0))return {score:-1,kind:'none'};
 const kind=parts.some(p=>p.kind==='fuzzy')?'fuzzy':parts.some(p=>p.kind==='alias')?'alias':'exact';
 return {score:Math.min(...parts.map(p=>p.score)),kind};
}
export const assetKey=a=>a.asset_id||a.type;
export function assetStyle(a){return !a.asset_id?'native':/servier/i.test((a.author||'')+' '+(a.source_url||''))?'detailed':'flat';}
export function assetDisplayName(a,locale='zh'){
  if(locale==='en'){
    const explicit=String(a.label_en||'').trim();
    if(explicit)return explicit;
    const raw=String(a.asset_id||a.type||'').replace(/^(bio|chemistry|physics|materials|engineering|earth_environment|computing_math|medicine)_/i,'').replace(/^(chem|phys|mat|eng|earth|math|med)_/i,'').replace(/[_-]+/g,' ');
    return raw.replace(/\b\w/g,c=>c.toUpperCase());
  }
  let label=String(a.label_zh||a.label||a.type).replace(/_/g,' ').replace(/\s+/g,' ').trim();
  const translations={'ions':'离子','pink transporter':'转运蛋白 · 粉色','simple receptor':'受体示意','cell membrane semi circle':'细胞膜截面','t cell receptor':'T 细胞受体'};
  for(const[from,to]of Object.entries(translations))if(normalized(label).startsWith(from))label=to+label.slice(from.length);
  label=label.replace(/^受体\s*·\s*simple receptor\s*(\d*)$/i,(_,n)=>'受体示意'+(n?' · '+n:''))
    .replace(/^细胞 受体\s*·\s*t cell receptor$/i,'T 细胞受体');
  if(label.startsWith('离子'))for(const[from,to]of Object.entries({blue:'蓝色',darkmagenta:'深洋红',gray:'灰色',green:'绿色',white:'白色'}))label=label.replace(new RegExp('\\b'+from+'\\b','gi'),to);
  return label;
}
export function rankAssets(assets,{domain='biology',category='',query='',style='',favorites=[],recent=[],view='all',fuzzy=true}={}){
  const favorite=new Set(favorites),recency=new Map(recent.map((id,i)=>[id,recent.length-i]));
  return assets.map((a,index)=>{
    if(a.catalog_status==='quarantined')return null;
    const key=assetKey(a);
    const kit=view==='signaling'?['ligand','receptor','receptor_dimer','gpcr','kinase','protein','lipid','tf','dna','mrna','membrane','nucleus','nuclear_pore']:view==='trafficking'?['cell','membrane','nucleus','vesicle','mvb','vesicle_fusion','mitochondrion','golgi','er']:null;
    if((domain!=='all'&&(a.domain||'biology')!==domain)||(category&&a.category!==category)||(style&&assetStyle(a)!==style)||(view==='favorites'&&!favorite.has(key))||(view==='recent'&&!recency.has(key))||(kit&&(a.asset_id||!kit.includes(a.type))))return null;
    const {score}=assetMatch(a,query,{fuzzy});
    if(score<0)return null;
    return {a,index,score:score*10000+(view==='recent'?(recency.get(key)||0)*100:0)+(!a.asset_id?100:0)+(favorite.has(key)?10:0)};
  }).filter(Boolean).sort((a,b)=>b.score-a.score||a.index-b.index).map(x=>x.a);
}
