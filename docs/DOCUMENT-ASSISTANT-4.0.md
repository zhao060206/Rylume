# 文档助手 · 4.0

右上角「文档助手」或首页「从文档提取」，打开与绘图区并排的右栏。

1. 添加论文、实验方案、汇报或其他文档，可一次选择多份。
2. 等待本机转换，点「查看 Markdown」核对提取文字，也可下载。
3. 勾选 1–8 份就绪文档，填写可选的分析重点，点击「分析绘图建议」。使用「设置 → 模型设置」里已有的文本模型。
4. 查看图的类型、推荐理由、对象与排版、原文依据及待确认项。
5. 点「编辑提示词」先调整，或「用于 AI 绘图」直接带入创作区。此时不会自动调用绘图。可以继续优化描述、预览结构，再生成可编辑初稿。

替换创作描述时保留之前的描述、参考图与创作设置，可点「恢复原描述」。连续切换建议时保留最初的草稿；手动改写后再换建议，则备份改写后的草稿。恢复按钮只用于对应的创作上下文。图版内容不会被建议直接覆盖。

## 转换方式

- PDF、PPTX、DOCX、TXT、MD、HTML、CSV、JSON、XML：Microsoft MarkItDown 0.1.9，禁用第三方插件与在线转换服务。
- PDF 按页提取，保留页码。扫描 PDF 可点「本机 OCR 重试」，使用已有 RapidOCR；一次最多识别 20 个扫描页，失败或超过限制的页会明确列出。
- XLSX：openpyxl 读取后生成 Markdown 表格；公式使用文件内缓存结果，不执行宏或重新计算工作簿。
- PPT、DOC、RTF、ODT、ODP：本机安装 LibreOffice 时，先在隔离配置下转换为 PPTX / DOCX，再转换为 Markdown。软件不捆绑 LibreOffice；其他电脑可安装它，或先在 Office 另存为新版格式。

单份文件最多 16 MB；PDF 最多 200 页；单份转换内容最多 80 万字符；一次模型分析最多 36 万字符，超限明确拒绝，不默默丢弃尾部内容。表格最多 10000 行、80 列。转换器提取的是文字结构，不能可靠还原复杂双栏阅读顺序、图片内机制、公式或版面。转换警告与 Markdown 预览用于核对这些问题。

原文件、Markdown、分析输入快照与建议保存在数据目录 `document-assistant/` 下。上传和转换均在本机完成；仅点击分析后，所选文字才发给自配的文本模型。模型的服务地址和密钥不写入分析快照。移出文档可通过「已移出」移回；分析历史独立保存。

分析和转换各有独立队列，可取消。取消后晚到的模型结果不应用；断连、转换失败或软件退出时保留原文件和已有 Markdown。建议是规划辅助，原文引用可定位并不等于其中每项科学判断已被人工确认。数据图单独标明需要原始数据，不能直接凭描述生成统计图。

## GitHub 提示词调研

已读取以下项目的实际实现和许可，提取适用方法，再重新编写 Rylume 的中文提示词；没有整段复制其提示词，也没有执行下载的代码。

| 来源 | 阅读内容 | 采用的方法 | 许可 |
| --- | --- | --- | --- |
| [dwzhu-pku/PaperBanana](https://github.com/dwzhu-pku/PaperBanana/blob/main/agents/planner_agent.py) | Planner 与 [Critic](https://github.com/dwzhu-pku/PaperBanana/blob/main/agents/critic_agent.py) | 对象、连接、分组与阅读顺序分开规划，提交前检查忠实性 | Apache-2.0 |
| [llmsresearch/paperbanana](https://github.com/llmsresearch/paperbanana/blob/main/prompts/diagram/planner.txt) | Planner、[Context Enricher](https://github.com/llmsresearch/paperbanana/blob/main/prompts/diagram/context_enricher.txt)、[Faithfulness](https://github.com/llmsresearch/paperbanana/blob/main/prompts/evaluation/faithfulness.txt) | 从原文抽取准确名称、输入输出、顺序与并行，禁止补写缺失事实 | MIT |
| [OpenDCAI/Paper2Any](https://github.com/OpenDCAI/Paper2Any/blob/main/dataflow_agent/promptstemplates/resources/pt_technical_route_desc_generator_repo.py) | Technical Route Description 与 [Diagram Planner](https://github.com/OpenDCAI/Paper2Any/blob/main/dataflow_agent/agentroles/paper2any_agents/diagram_planner.py) | 区分技术路线、机制和实验流程，明确分层与布局 | Apache-2.0 |
| [microsoft/markitdown](https://github.com/microsoft/markitdown) | 本机文件转换接口、Office/PDF 转换器 | 统一转为 Markdown 后再送给模型 | MIT |

原创提示词位于 `document_advisor.py`，版本 `document-figure-advisor-v1`。它要求结构化 JSON，分别给出图的类型、对象、关系、视觉规划、待确认项与连续原文摘录。服务端核验引用的文档和章节存在、摘录可在原文中定位、连接端点有效；无法定位的建议会排除。长文逐组提交所有选中章节，再合并主题。文档里的角色指令、工具调用和外链要求均当作资料内容，不赋予执行权限。

## 验收边界

自动化使用合成文档与本机测试模型，验证文件转换、HTTP 接口、引用定位、取消与重试、提示词替换及恢复。界面验证使用独立数据目录，不读取用户论文或调用用户收费模型。实际建议质量仍取决于文档可读性和所配置模型。

2026-10-31 验证：537 项 Python 测试、7 项子测试通过，23 组 JavaScript 测试通过。Windows 冻结版实际上传并转换 PDF、PPT/PPTX、DOC/DOCX、XLSX、TXT、CSV；扫描 PDF 首次提示无文字，选择本机 OCR 后获得可用文本。通过本机模拟模型完成带引用建议，未使用真实付费服务。首页和已有画板分别验证提示词编辑、带入及恢复，1040 px 窗口采用可关闭浮层。
