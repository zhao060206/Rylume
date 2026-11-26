// 2026-11-26 front-end redesign: dialog focus, Esc on side panels, text selection box.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {setupDialogFocus} from '../ui/dialog-focus.js';

// A dialog that opens with focus on its close button moves focus to itself.
{
  const listeners={};
  const close={matches:sel=>sel.includes('[data-close]')};
  const dialog={tagName:'DIALOG',contains:n=>n===close,hasAttribute:()=>false,tabIndex:0,focused:false,focus(){this.focused=true;}};
  const doc={activeElement:close,addEventListener:(type,fn)=>{listeners[type]=fn;}};
  setupDialogFocus(doc);
  listeners.toggle({target:dialog,newState:'open'});
  assert.equal(dialog.focused,true,'focus leaves the close button');
  assert.equal(dialog.tabIndex,-1,'the dialog becomes focusable without entering the tab order');
}
// A dialog that opens with focus in a field keeps it there, so typing can start at once.
{
  const listeners={};
  const field={matches:()=>false};
  const dialog={tagName:'DIALOG',contains:n=>n===field,hasAttribute:()=>false,focused:false,focus(){this.focused=true;}};
  setupDialogFocus({activeElement:field,addEventListener:(t,fn)=>{listeners[t]=fn;}});
  listeners.toggle({target:dialog,newState:'open'});
  assert.equal(dialog.focused,false,'a focused field is left alone');
  listeners.toggle({target:{tagName:'DIV'},newState:'open'});
}

const src=name=>readFile(new URL('../ui/'+name,import.meta.url),'utf8');
// Esc closes the side panels, but never while typing or while a dialog is on top.
for(const [file,needle] of [['annotation-ui.js','dismiss();button.focus'],['document-assistant.js','setOpen(false);$(\'toggle-documents\')']]){
  const s=await src(file);
  const at=s.indexOf(needle);assert.ok(at>0,file+' closes on Esc');
  const guard=s.slice(Math.max(0,at-400),at);
  for(const g of ['isComposing','dialog[open]','input,textarea,select'])assert.ok(guard.includes(g),file+' Esc guard: '+g);
}
// A plain text object is selected where its words are drawn, not around its empty box.
{
  const s=await src('canvas-editor.js');
  assert.match(s,/textBox=o\.type==='text'&&!usesTextAppearance\(o\)&&o\.label\?objectLabelBoxes\(\{objects:\[o\]\}\)\[0\]:null/);
  assert.match(s,/resizeHandles\(bx,unit\)/);
}
// The editor folds the navigation without overwriting the user's saved choice.
{
  const s=await src('workspace-navigation.js');
  const hook=s.slice(s.indexOf('const syncEditing'));
  assert.ok(!hook.slice(0,hook.indexOf('\n')).includes('setItem'),'entering a board does not save a preference');
}
console.log('Redesign: dialog focus, Esc on side panels, text selection and folded navigation hold.');
