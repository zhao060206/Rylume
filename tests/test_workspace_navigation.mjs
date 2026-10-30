import assert from 'node:assert/strict';
import {recentSections,recentStatus} from '../ui/workspace-navigation.js';

const now=new Date(2026,9,30,12),created=(day,hour=10)=>new Date(2026,9,day,hour).getTime()/1000;
const jobs=[
 {id:'old',title:'旧版流程',created:created(25),status:'completed'},
 {id:'failed',title:'通路生成未完成',created:created(30,11),status:'failed'},
 {id:'running',title:'最新通路',created:created(30,12),status:'processing'},
 {id:'archived',title:'已归档',created:created(30,13),status:'completed',archived:true},
 {id:'yesterday',title:'实验图',collection:'实验流程',created:created(29),status:'completed'},
];
assert.deepEqual(recentSections(jobs,'',now).map(g=>[g.label,g.jobs.map(j=>j.id)]),[
 ['今天',['running','failed']],['昨天',['yesterday']],['更早',['old']]
]);
assert.deepEqual(recentSections(jobs,'实验流程',now)[0].jobs.map(j=>j.id),['yesterday']);
assert.equal(recentSections(jobs,'不存在',now).length,0);
assert.equal(recentStatus(jobs[1]).kind,'failed');
assert.equal(recentStatus(jobs[2]).label,'生成中');
assert.equal(recentStatus({status:'completed',illustration_result:{state:'partial'}}).label,'草稿');
assert.equal(recentStatus({status:'cancelled'}).label,'已取消');
assert.equal(jobs[0].id,'old','Sorting recent documents must not mutate the job store');
console.log('Recent documents sort by date, retain in-flight and failed work, filter archives and search titles or collections.');
