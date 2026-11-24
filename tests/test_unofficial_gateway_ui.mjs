import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {modelPatch,providerChange,unofficialAcknowledged,UNOFFICIAL_ACK_VERSION}=await import('../ui/workspace-ui.js');

// Without a service type the patch is exactly what it was before this feature.
assert.deepEqual(modelPatch({text:{base_url:' https://a ',model:' m ',api_key:''}}),{text:{base_url:'https://a',model:'m'}});
// The settings UI always sends a type, so switching back to custom overwrites a stored gateway.
assert.equal(modelPatch({text:{base_url:'x',model:'m',api_key:'',provider:'unofficial'}}).text.provider,'unofficial');
assert.equal(modelPatch({text:{base_url:'x',model:'m',api_key:'',provider:'custom'}}).text.provider,'custom');
assert.equal(modelPatch({text:{base_url:'x',model:'m',api_key:'',provider:'anything-else'}}).text.provider,'custom','Unknown types never become unofficial');
console.log('modelPatch keeps its old shape and carries the service type');

// Choosing the unofficial gateway asks first, unless the notice was already accepted.
assert.equal(providerChange('unofficial',false),'confirm');
assert.equal(providerChange('unofficial',true),'apply');
assert.equal(providerChange('custom',false),'apply','Leaving the gateway never asks');
assert.equal(unofficialAcknowledged({}),false);
assert.equal(unofficialAcknowledged({unofficial_ack:{version:UNOFFICIAL_ACK_VERSION,at:1}}),true);
assert.equal(unofficialAcknowledged({unofficial_ack:{version:UNOFFICIAL_ACK_VERSION+1}}),false,'A newer notice must be accepted again');
assert.equal(unofficialAcknowledged({},true),true,'Accepted in this session but not yet saved');
console.log('Risk confirmation is required exactly when the unofficial gateway is chosen without consent');

// The page ships the confirmation dialog; confirm starts disabled behind the checkbox.
const html=await readFile(new URL('../ui/canvas-studio.html',import.meta.url),'utf8');
const dialog=html.slice(html.indexOf('id="unofficial-gateway-dialog"'));
assert.ok(html.includes('id="unofficial-gateway-dialog"'));
assert.ok(dialog.includes('id="unofficial-gateway-agree"')&&dialog.includes('type="checkbox"'));
assert.match(dialog,/disabled="" id="unofficial-gateway-confirm"/);
assert.ok(dialog.includes('data-unofficial-cancel'));
for(const phrase of ['不是服务商提供的官方接口','封禁','不读取、不保存'])assert.ok(dialog.includes(phrase),'Risk notice must mention: '+phrase);
const css=await readFile(new URL('../ui/workbench-ui.css',import.meta.url),'utf8');
assert.ok(css.includes('.unofficial-badge'));
console.log('Unofficial gateway dialog and badge are present');
