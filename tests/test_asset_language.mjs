import assert from 'node:assert/strict';
import {assetDisplayName} from '../ui/asset-search.js';
assert.equal(assetDisplayName({label:'线粒体',label_en:'Mitochondrion'},'zh'),'线粒体');
assert.equal(assetDisplayName({label:'线粒体',label_en:'Mitochondrion'},'en'),'Mitochondrion');
assert.equal(assetDisplayName({asset_id:'physics_phys_qubit',label:'量子比特'},'en'),'Qubit');
console.log('Bilingual asset labels and locale switching passed');
