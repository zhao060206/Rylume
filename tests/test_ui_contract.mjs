import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {auditUiContract} from '../ui/ui-contract.js';

// A tiny DOM adapter keeps this check dependency-free and makes the contract
// usable in the desktop WebView as well as in CI.
const html=await readFile(new URL('../ui/canvas-studio.html',import.meta.url),'utf8');
const ids=new Set([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]));
const attr=(name)=>[...html.matchAll(new RegExp(`${name}="([^"]+)"`,'g'))].map(m=>m[1]);
const commands=attr('data-command'),panels=attr('data-panel-command'),closes=attr('data-close'),controls=attr('aria-controls');
assert.ok(commands.every(value=>ids.has(value)),`a data-command target is missing: ${commands.filter(value=>!ids.has(value))}`);
assert.ok(closes.every(value=>ids.has(value)),`a data-close target is missing: ${closes.filter(value=>!ids.has(value))}`);
assert.ok(controls.every(value=>ids.has(value)),`an aria-controls target is missing: ${controls.filter(value=>!ids.has(value))}`);
assert.ok(panels.every(value=>html.includes(`data-tab="${value}"`)),'each compact-menu panel command has a tab');

const elements=[];
for(const value of commands)elements.push({dataset:{command:value}});
for(const value of panels)elements.push({dataset:{panelCommand:value}});
const fake={
  documentElement:{setAttribute(){}},
  getElementById(value){return ids.has(value)?{}:null;},
  querySelector(selector){if(selector.startsWith('[data-tab=')){const value=selector.match(/"([^"]+)"/)?.[1];return panels.includes(value)||value==='assets'?{}:null;}return {};},
  querySelectorAll(selector){if(selector==='[data-command]')return elements.filter(e=>e.dataset.command);if(selector==='[data-panel-command]')return elements.filter(e=>e.dataset.panelCommand);if(selector==='[data-close]'||selector==='[aria-controls]'||selector==='[data-tab]')return [];return [];}
};
assert.equal(auditUiContract(fake).ok,true);
console.log('UI command, panel, close and accessibility targets are internally consistent.');
