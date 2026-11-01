/**
 * Small runtime contract for the workbench chrome.
 *
 * The editor has a deliberately modular UI, so a button can be wired by a
 * different module than the one that renders it.  This audit catches the
 * common silent failures (a command pointing at a removed target, a panel
 * command without a tab, or an aria-controls target that no longer exists).
 * It never blocks editing; the report is exposed for diagnostics and tests.
 */
export function auditUiContract(root = document) {
  const issues = [];
  const escape = value => globalThis.CSS?.escape ? CSS.escape(value) : String(value).replace(/[^a-zA-Z0-9_-]/g, '\\$&');
  const has = selector => !!root.querySelector(selector);
  const id = value => !!root.getElementById(value);
  const add = (kind, element, message) => issues.push({kind, id: element?.id || '', message});

  root.querySelectorAll('[data-command]').forEach(element => {
    const target = element.dataset.command;
    if (!id(target)) add('command-target', element, `命令“${target}”没有对应操作入口`);
  });
  root.querySelectorAll('[data-panel-command]').forEach(element => {
    const target = element.dataset.panelCommand;
    if (!has(`[data-tab="${escape(target)}"]`)) add('panel-target', element, `面板“${target}”没有对应标签`);
  });
  root.querySelectorAll('[data-close]').forEach(element => {
    const target = element.dataset.close;
    if (!id(target)) add('close-target', element, `关闭按钮找不到“${target}”`);
  });
  root.querySelectorAll('[aria-controls]').forEach(element => {
    const target = element.getAttribute('aria-controls');
    if (target && !id(target)) add('aria-target', element, `控件声明的目标“${target}”不存在`);
  });
  root.querySelectorAll('[data-tab]').forEach(element => {
    const tab = element.dataset.tab;
    if (tab !== 'assets' && !id(`panel-${tab}`)) add('tab-target', element, `工作区标签“${tab}”没有内容面板`);
  });
  return {ok: issues.length === 0, issues, checkedAt: Date.now()};
}

/** Install a non-invasive guard for future modules and third-party extensions. */
export function installUiContract({root = document, onIssue = () => {}} = {}) {
  const report = auditUiContract(root);
  root.documentElement?.setAttribute('data-ui-contract', report.ok ? 'ok' : 'warning');
  if (!report.ok) report.issues.forEach(issue => onIssue(issue));
  root.addEventListener('click', event => {
    const element = event.target.closest?.('[data-command],[data-panel-command],[data-close]');
    if (!element || element.disabled) return;
    const target = element.dataset.command || element.dataset.panelCommand || element.dataset.close;
    const exists = element.dataset.panelCommand
      ? root.querySelector(`[data-tab="${escape(target)}"]`)
      : root.getElementById(target);
    if (exists) return;
    event.preventDefault();
    const issue = {kind: 'runtime-target', id: element.id || '', message: `当前操作“${target}”暂不可用`};
    onIssue(issue);
    root.dispatchEvent(new CustomEvent('ui-action-error', {detail: issue}));
  });
  return report;
}

