import assert from 'node:assert/strict';
import {normalizeWorkspaceMode,defaultModeLayout,responsiveModeLayout,modeRequestQueue} from '../ui/workspace-modes.js';

assert.equal(normalizeWorkspaceMode(null),'simple');
assert.equal(normalizeWorkspaceMode('unknown'),'simple');
assert.equal(normalizeWorkspaceMode('professional'),'professional');
assert.deepEqual(defaultModeLayout('simple'),{tab:'assets',inspector:'properties',leftCollapsed:true,propertiesHidden:false});
assert.equal(defaultModeLayout('professional',1280).leftCollapsed,false);
assert.equal(defaultModeLayout('professional',1000).leftCollapsed,true);
const remembered={tab:'references',inspector:'review',leftCollapsed:false,propertiesHidden:false};
assert.equal(responsiveModeLayout(remembered,1000).leftCollapsed,true);
assert.equal(remembered.leftCollapsed,false,'Narrow windows never erase a remembered wide-screen layout');
assert.equal(responsiveModeLayout({...remembered,propertiesHidden:true},1000).leftCollapsed,false);

// Rapid clicks while a transition is pending must follow the final requested mode.
const calls=[],pending=[];
const queue=modeRequestQueue('simple',async(next,previous)=>{
  calls.push([previous,next]);await new Promise(resolve=>pending.push(resolve));
});
assert.equal(await queue.request('simple'),'simple','Clicking the active segment must not lock the queue');
const first=queue.request('professional');
const last=queue.request('simple');assert.equal(first,last);
pending.shift()();await new Promise(resolve=>setTimeout(resolve,0));
assert.deepEqual(calls,[['simple','professional'],['professional','simple']]);
pending.shift()();assert.equal(await last,'simple');assert.equal(queue.current,'simple');
const again=queue.request('professional');pending.shift()();assert.equal(await again,'professional');
const noAnimations=modeRequestQueue('simple',()=>{});
assert.equal(await noAnimations.request('professional'),'professional');
assert.equal(await noAnimations.request('simple'),'simple','Reduced-motion synchronous changes remain reusable');
console.log('Workspace modes preserve narrow layouts and settle rapid/repeated requests on the last choice.');
