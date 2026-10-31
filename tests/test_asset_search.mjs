import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {rankAssets,assetMatch,editDistance} from '../ui/asset-search.js';

const assets=[
 {asset_id:'m1',type:'mitochondrion',label:'线粒体剖面',category:'细胞器',keywords:'mitochondrion mitochondria organelle'},
 {asset_id:'m2',type:'process',label:'线粒体染色',category:'实验器材',keywords:['mitochondrial','staining']},
 {asset_id:'r1',type:'receptor',label:'单体膜受体',category:'膜结构与受体',keywords:'receptor'},
 {asset_id:'scope',type:'process',label:'显微镜',category:'实验器材',keywords:'microscope'},
 {asset_id:'liver',type:'process',label:'小鼠肝脏',keywords:'mouse liver'},
 {asset_id:'human',type:'process',label:'人肝脏',keywords:'human liver'},
 {asset_id:'cd4',type:'protein',label:'CD4 receptor'},
 {asset_id:'cd45',type:'protein',label:'CD45 receptor'},
 {asset_id:'il6',type:'protein',label:'IL-6'},
 {asset_id:'il8',type:'protein',label:'IL-8'},
 {asset_id:'chem',type:'process',label:'受体化合物',domain:'chemistry',keywords:'receptor'},
];
const ids=(query,options={})=>rankAssets(assets,{query,...options}).map(a=>a.asset_id);
assert.equal(ids('线粒体')[0],'m1');assert.equal(ids('mitochondria')[0],'m1');
assert.equal(ids('xianliti')[0],'m1');assert.equal(ids('xlt')[0],'m1');
assert.ok(ids('线粒题').includes('m1'),'A one-character Chinese typo finds the intended object');
assert.equal(assetMatch(assets[0],'线粒题').kind,'fuzzy');
assert.equal(ids('microsocpe')[0],'scope','Adjacent typing transpositions match');
assert.equal(ids('recpetor')[0],'r1');
assert.equal(editDistance('receptor','recpetor'),1);
assert.deepEqual(ids('mouse liver'),['liver'],'Multiple terms require all concepts');
assert.deepEqual(ids('mouse kidney'),[]);
assert.deepEqual(ids('线粒体 剖面'),['m1']);
assert.deepEqual(ids('CD4'),['cd4'],'CD4 cannot silently become CD45');
assert.deepEqual(ids('IL6'),['il6']);assert.deepEqual(ids('IL-6'),['il6']);
assert.deepEqual(ids('CD5'),[],'Short numbered scientific names are never typo corrected');
assert.deepEqual(ids('线粒题',{fuzzy:false}),[]);
assert.deepEqual(ids('microsocpe',{category:'细胞器'}),[],'Fuzzy search respects category limits');
assert.ok(!ids('受体').includes('chem'));assert.deepEqual(ids('受体',{domain:'chemistry'}),['chem']);
assert.ok(ids('受体',{domain:'all'}).includes('chem'),'Searching all disciplines is an explicit choice');
assert.deepEqual(ids('受体',{view:'favorites',favorites:['r1']}),['r1']);
assert.deepEqual(ids('受体',{view:'recent',recent:['cd45']}),['cd45']);
assert.deepEqual(ids('totally nonexistent nonsense'),[]);
assert.deepEqual(ids('   '),ids(''));
const original=structuredClone(assets);ids('线粒题');assert.deepEqual(assets,original,'Search never modifies scientific labels or identities');
const mutable={type:'process',label:'旧名称'};assetMatch(mutable,'旧名称');mutable.label='新名称';assert.ok(assetMatch(mutable,'新名称').score>0);

// Use the actual offline corpus, including non-Latin metadata and string keywords.
const corpus=JSON.parse(await readFile(new URL('../assets/bioicons/manifest.json',import.meta.url),'utf8'));
for(const q of ['线粒题','recpetor','microsocpe','mouse liver','xlt']){
 const started=performance.now();const found=rankAssets(corpus,{query:q});
 assert.ok(performance.now()-started<2000,`Search must remain interactive for ${corpus.length} real entries`);
 assert.ok(found.every(a=>(a.domain||'biology')==='biology'));
}
console.log('Fuzzy asset search: Chinese/English/pinyin, transpositions, AND terms, protected markers, filters and real-corpus responsiveness passed');
