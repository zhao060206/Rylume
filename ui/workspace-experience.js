/** One writing surface; other starting points launch their actual workflow. */
export function setupWorkspaceExperience({imports,composer,blank}) {
 const $=id=>document.getElementById(id);
 $('home-convert-figure').onclick=imports.open;
 $('welcome-blank').hidden=false;
 $('welcome-blank').onclick=blank;
 const action=document.createElement('button');
 action.id='toolbar-import-figure';action.type='button';action.className='rail-item';
 action.title='导入整张科研图，创建可编辑图版';
 action.innerHTML='<svg class="icon" aria-hidden="true"><use href="#download"></use></svg><span>导入科研图</span>';
 action.onclick=imports.open;
 document.querySelector('.top-tools [data-tab=templates]').after(action);
 const quick=document.querySelector('.quick-edit');quick.classList.add('inspector-quick-edit');
 $('toolbar-guidance-text').textContent='点选拖动 · 双击改字';
 $('toggle-properties').classList.remove('professional-only');
 return {showAI(){composer.open();}};
}
