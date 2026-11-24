import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const src = fs.readFileSync(new URL('../ui/dock.js', import.meta.url), 'utf8');
const body = src.slice(src.indexOf('export function plainMessage'), src.indexOf('function titleOf'));
const plainMessage = new Function(body.replace('export function plainMessage', 'return function') )();

test('raw exception class names never reach the status line', () => {
  assert.equal(plainMessage('SceneError: 请配置视觉模型或文本模型后识别参考图'), '请配置视觉模型或文本模型后识别参考图');
  assert.equal(plainMessage('原图已保留；SceneError: 请重试'), '原图已保留；请重试');
  assert.match(plainMessage('Failed to fetch'), /连接不上本机服务/);
  const missing = plainMessage("ModuleNotFoundError: No module named 'fitz'");
  assert.match(missing, /重新安装/);
  assert.doesNotMatch(missing, /Error|No module|fitz/);
  assert.equal(plainMessage('已保存到本机'), '已保存到本机');
});

test('work tools dock beside the canvas; decisions stay modal', () => {
  for (const id of ['export-menu','asset-library-dialog','gallery-dialog','ai-dialog','audit-dialog','models-dialog','history-dialog']) assert.ok(src.includes("'" + id + "'"), id + ' docks');
  for (const id of ['sketch-pad-dialog','creation-dialog','command-dialog']) assert.ok(!src.includes("'" + id + "'"), id + ' stays modal');
  assert.ok(src.includes('if(d.hidden)return;'), 'hidden panels never dock');
});

test('the page loads the dock before feature modules', () => {
  const app = fs.readFileSync(new URL('../ui/canvas-app.js', import.meta.url), 'utf8');
  assert.ok(app.startsWith("import {plainMessage} from './dock.js';"));
});

test('minimized panels give the canvas back and return to the front', () => {
  assert.ok(src.includes("filter(d=>!d.classList.contains('is-minimized'))"));
  assert.ok(src.includes('else front(d)'));
  const css = fs.readFileSync(new URL('../ui/styles/calm.css', import.meta.url), 'utf8');
  assert.ok(!/\.floating-minimize\)\{display:none/.test(css), 'minimize button stays available');
});

test('dock fit fixes keep the toolbar, footer and mode switch inside their space', () => {
  const css = fs.readFileSync(new URL('../ui/styles/calm.css', import.meta.url), 'utf8');
  assert.ok(css.includes('/* calm: dock fit fixes */'));
  assert.ok(css.includes('.dock-tabs[hidden]{display:none!important}'));
  assert.ok(/@container workspace \(max-width:700px\)/.test(css), 'narrow workspace wraps the toolbar');
  assert.ok(css.includes('body.dock-open #workspace>.toolbar{flex-wrap:wrap'), 'wrap beats the dock nowrap rule');
  assert.ok(css.includes('.asset-library-footer button{white-space:nowrap'));
  assert.ok(css.includes('.workspace-mode-thumb{box-shadow:none'), 'scaled thumb has no stretched shadow');
});
