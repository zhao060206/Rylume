export const COMMANDS = [
  {id:'new',title:'新建图版',hint:'开始一张新的科研图',terms:'new home 首页 新图',group:'图版'},
  {id:'blank',title:'创建空白图版',hint:'从空白纸张手动绘制',terms:'blank canvas 手动 空白',group:'图版'},
  {id:'generate',title:'AI 绘图',hint:'描述研究内容，生成初稿',terms:'ai prompt generate 生成 提示词',group:'创作'},
  {id:'import',title:'导入科研图',hint:'图片转为可编辑矢量',terms:'import vector 图片 转换 矢量',group:'创作'},
  {id:'assets',title:'打开素材库',hint:'搜索和添加科研素材',terms:'assets library 素材',group:'创作'},
  {id:'templates',title:'打开模板库',hint:'从已有排版开始',terms:'templates layouts 模板 排版',group:'创作'},
  {id:'documents',title:'打开文档助手',hint:'从论文和资料提取绘图建议',terms:'documents pdf word ppt 文档 论文',group:'创作'},
  {id:'guide',title:'分步填写绘图需求',hint:'用必要问题梳理科学内容',terms:'guide help 引导 向导 分步 需求',group:'创作'},
  {id:'sketch',title:'画一张参考草稿',hint:'先画大致布局，再用于 AI 绘图',terms:'sketch draft 草图 草稿 手绘',group:'创作'},
  {id:'personal',title:'我的素材',hint:'导入、整理自己的素材图片',terms:'personal assets 自己的素材 上传素材',group:'创作'},
  {id:'mytemplates',title:'我的模板',hint:'复用自己保存的科研图版',terms:'my templates 个人模板',group:'创作'},
  {id:'project',title:'新建项目',hint:'把相关图版放在一起',terms:'project folder 项目 文件夹',group:'图版'},
  {id:'rename',title:'修改图版名称与项目',hint:'整理当前图版',terms:'rename name 名称 重命名',group:'图版',document:true},
  {id:'save',title:'保存当前图版',hint:'保存到本机',terms:'save 保存',key:'Ctrl S',group:'图版',document:true},
  {id:'export',title:'导出图版',hint:'SVG、PDF、PNG 或 PowerPoint',terms:'export svg pdf png pptx 导出',group:'图版',document:true},
  {id:'fit',title:'适合窗口',hint:'找回整张画布',terms:'fit zoom 缩放 窗口',group:'画布',document:true},
  {id:'focus',title:'专注画布',hint:'收起侧栏，再次执行可恢复',terms:'focus 专注 全屏',group:'画布',document:true},
  {id:'properties',title:'对象属性',hint:'修改文字、颜色和位置',terms:'properties text 属性 改字 文字',group:'画布',document:true},
  {id:'annotations',title:'批注修改',hint:'圈出区域，向 AI 提出修改要求',terms:'annotate revise 批注 修改',group:'画布',document:true},
  {id:'review',title:'检查当前图版',hint:'查看具体对象的检查建议',terms:'review audit 检查 审查',group:'画布',document:true},
  {id:'settings',title:'模型与服务设置',hint:'配置自己的文本、生图和视觉模型',terms:'settings model api 设置 模型',group:'设置'},
  {id:'shortcuts',title:'查看快捷键',hint:'常用绘图操作',terms:'keyboard shortcuts 快捷键 帮助',group:'设置'},
];

export function searchCommands(query, commands = COMMANDS) {
  const words = String(query || '').trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  return commands.filter(c => words.every(word => `${c.title} ${c.terms} ${c.group}`.toLocaleLowerCase().includes(word)));
}

export function setupCommandPalette({actions, hasDocument, toast}) {
  const dialog = document.getElementById('command-dialog');
  const input = document.getElementById('command-search');
  const list = document.getElementById('command-results');
  let matches = [], active = 0;
  function select(index) {
    active = index;
    [...list.querySelectorAll('[role=option]')].forEach((item, i) => item.setAttribute('aria-selected', String(i === active)));
    const item = list.querySelector(`[data-index="${active}"]`);
    if (item) {input.setAttribute('aria-activedescendant', item.id); item.scrollIntoView({block:'nearest'});}
    else input.removeAttribute('aria-activedescendant');
  }
  async function run(command) {
    if (!command || command.document && !hasDocument()) return;
    dialog.close();
    try {await actions[command.id]();} catch (error) {toast(error.message, true);}
  }
  function render() {
    const found = searchCommands(input.value);
    matches = found.filter(c => actions[c.id] && (!c.document || hasDocument()));
    list.replaceChildren();
    if (!matches.length) {
      const empty = document.createElement('p'); empty.className = 'command-empty';
      empty.textContent = found.some(c=>c.document)&&!hasDocument()
        ? '请先打开一张图版，再使用保存、导出和画布编辑操作'
        : '没有找到可用操作，试试“素材”“模板”或“设置”'; list.append(empty);
    }
    matches.forEach((command, index) => {
      const row = document.createElement('button'); row.type = 'button'; row.id = `command-${command.id}`;
      row.className = 'command-item'; row.dataset.index = index; row.tabIndex = -1; row.setAttribute('role','option');
      const copy = document.createElement('span'), title = document.createElement('strong'), hint = document.createElement('small');
      title.textContent = command.title; hint.textContent = command.hint; copy.append(title, hint);
      const group = document.createElement(command.key ? 'kbd' : 'span'); group.className = 'command-group'; group.textContent = command.key || command.group;
      row.append(copy, group); row.onclick = () => run(command); row.onpointermove = () => {if(active!==index)select(index);}; list.append(row);
    });
    select(0);
    document.getElementById('command-count').textContent = `${matches.length} 个操作`;
  }
  function open() {
    if (document.querySelector('dialog:modal')) return;
    input.value = ''; dialog.showModal(); render(); input.focus();
  }
  input.addEventListener('input', render);
  input.addEventListener('keydown', event => {
    if (!['ArrowDown','ArrowUp','Enter'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    if (event.key === 'Enter') run(matches[active]);
    else if (matches.length) select((active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length);
  });
  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !event.isComposing) {
      event.preventDefault(); event.stopPropagation(); if (dialog.open) dialog.close(); else open();
    }
  }, true);
  document.getElementById('open-commands').onclick = open;
  return {open};
}
