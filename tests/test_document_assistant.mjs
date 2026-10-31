import assert from 'node:assert/strict';
import {canAnalyzeDocuments,selectedDocumentIds,canReuseFigure,activeDocumentTask,documentReady} from '../ui/document-assistant.js';

const docs=[
  {id:'ready',status:'ready'},
  {id:'waiting',status:'converting'},
  {id:'failed',status:'failed'},
  {id:'archived',status:'ready',archived:true}
];

// Document ready checks
assert.equal(documentReady(docs[0]), true);
assert.equal(documentReady(docs[1]), false);
assert.equal(documentReady(docs[2]), false);
assert.equal(documentReady(docs[3]), false);

// Selection rules
assert.equal(canAnalyzeDocuments(docs,new Set()),false);
assert.equal(canAnalyzeDocuments(docs,new Set(['ready'])),true);
assert.equal(canAnalyzeDocuments(docs,new Set(['ready','waiting'])),false);
assert.equal(canAnalyzeDocuments(docs,new Set(['ready','failed'])),false);
assert.equal(canAnalyzeDocuments(docs,new Set(['archived'])),false);
assert.deepEqual(selectedDocumentIds(docs,new Set(['ready','archived'])),['ready']);

// Max 8 documents limit
const manyDocs = Array.from({length:10},(_,i)=>({id:`doc_${i}`,status:'ready'}));
assert.equal(canAnalyzeDocuments(manyDocs,new Set(['doc_0','doc_1','doc_2','doc_3','doc_4','doc_5','doc_6','doc_7'])), true);
assert.equal(canAnalyzeDocuments(manyDocs,new Set(['doc_0','doc_1','doc_2','doc_3','doc_4','doc_5','doc_6','doc_7','doc_8'])), false);

// Suggestion reuse rules
assert.equal(canReuseFigure({kind:'mechanism',prompt:'draw pathway',evidence:[{quote:'valid quote'}]}), true);
assert.equal(canReuseFigure({kind:'workflow',prompt:'draw flow',evidence:[{quote:'valid quote'}]}), true);
// Data charts must not be directly reused in drawing composer because they require quantitative numerical data
assert.equal(canReuseFigure({kind:'data_chart',prompt:'draw bar chart',evidence:[{quote:'valid quote'}]}), false);
// Reusable figures require at least one verified evidence quote
assert.equal(canReuseFigure({kind:'mechanism',prompt:'draw pathway',evidence:[]}), false);
assert.equal(canReuseFigure({kind:'mechanism',prompt:'',evidence:[{quote:'valid quote'}]}), false);
assert.equal(canReuseFigure(null), false);

// Task activity tracking
assert.equal(activeDocumentTask({status:'queued'}), true);
assert.equal(activeDocumentTask({status:'converting'}), true);
assert.equal(activeDocumentTask({status:'running'}), true);
assert.equal(activeDocumentTask({status:'ready'}), false);
assert.equal(activeDocumentTask({status:'completed'}), false);
assert.equal(activeDocumentTask({status:'failed'}), false);
assert.equal(activeDocumentTask({status:'cancelled'}), false);

console.log('Document assistant JS assertions passed: document ready, bounds, reuse rules and task status.');
