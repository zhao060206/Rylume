// Opening a dialog should not paint a focus ring on its close button. When the browser's
// initial focus lands on a dismiss control, it moves to the dialog itself; Tab still reaches
// every control and Esc still closes.
const DISMISS='[data-close],.icon-button,.dialog-heading button,.floating-window-actions button,.annotation-head button';
export function setupDialogFocus(doc=globalThis.document){
 if(!doc?.addEventListener)return;
 doc.addEventListener('toggle',event=>{
  const dialog=event.target;
  if(dialog?.tagName!=='DIALOG'||event.newState!=='open')return;
  const active=doc.activeElement;
  if(!active||active===dialog||!dialog.contains(active)||!active.matches?.(DISMISS))return;
  if(!dialog.hasAttribute('tabindex'))dialog.tabIndex=-1;
  dialog.focus({preventScroll:true});
 },true);
}
