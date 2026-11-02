# 大图编辑性能验收

本轮优化针对实际使用中的卡顿：大图改字、拖动、自动保存、恢复副本，以及审查轮询。安装版和既有发布资产没有被替换；变更记录在 CHANGELOG 的「待发布」部分。

## 样本与测量

使用真实论文的 JAK–STAT 图，原图 1770 × 900 px，场景含 417 个对象、48,201 条 SVG 路径，场景 JSON 约 19.8 MB、SVG 约 21.1 MB。论文来源：Li 与 Battista，*JAK-STAT Signaling: Mechanisms and Therapeutics in Stem Cell Biology*，Figure 1，DOI [10.3390/ijms27209052](https://doi.org/10.3390/ijms27209052)，CC BY。

对照版本为提交 `3a525a0`。同机 Windows、Python 3.13、Node 24，实际浏览器运行生产 SceneEditor。改字 8 次，拖动采样 30 次；以下为本次测量，不能外推为所有图的固定耗时。

| 操作 | 优化前 | 优化后 |
|---|---:|---:|
| 改字 JavaScript 处理，中位数 | 129.8 ms | 8.5 ms |
| 拖动 JavaScript 处理，中位数 | 83.6 ms | 2.3 ms |
| 恢复副本同步入队 | 74.6 ms | 2.6 ms |
| 单次标签保存响应 | 41,233,004 B | 1,537 B |
| 场景校验次数 / 保存 | 7 | 3 |
| 后端场景提交与响应序列化，3 次中位数 | 0.852 s | 0.398 s |

后端时间来自隔离 SceneRepository，包含持久化和响应编码，不含 HTTP 与应用元数据发布。实际 HTTP 的改字、移动、撤销/重做共 6 条命令使用 445 B 请求和 1,376 B 响应；保存后重新读取与原始对象完全一致。

浏览器环境部分 animation frame 回调出现超时，基准页使用了有界等待，因此不将「绘制等待」当作真实屏幕帧率，也不据此承诺 60 FPS。首次绘制本次为 861 / 1,134 ms，未证明启动提速。恢复副本的异步落盘仍需时间，同步入队时间才代表这里的主线程负担。

## 修改与兼容

- 画布保留根 SVG 和未变化的对象节点；缓存直接比较对象字段，不再将整份 SVG 字符串反复编码为缓存键。对象来源与基准对象各建立一次 ID 索引。
- 连续 pointermove 每帧处理最新位置，pointerup 刷入最终位置，取消操作会撤销待处理帧。没有抽稀或栅格化科研内容。
- `PATCH /api/jobs/{id}/scene` 可请求 `response: "delta"`。返回服务端规范化后的变化字段，处理删除字段、增删对象与顺序；旧客户端继续收到完整 scene + SVG。
- 模板、画布、区室和原生图形状态改变时返回完整 SVG，保留规范图形；保存中继续输入时，完整图形来源跨后续增量批次保留，避免显示临时占位图。
- 大恢复副本直接写 IndexedDB，跳过注定超出同步存储容量的整图 JSON 编码。快照共享不可变字符串；排队中的旧快照由最新快照替代，clear 与后续写入仍按顺序执行。
- 减少后端重复读取、深拷贝和规范化。新增 `GET /api/jobs/{id}/audit`，仅返回修订号与审查结果，保留作者确认、视觉意见与已处理建议。
- 隐藏的图层列表按打开时刷新；矢量细节入口改用文档事件，移除覆盖数万路径的 DOM 变化监听。移除已经被文档工作流覆盖的下载处理器。旧任务与兼容模块继续保留。
- PowerPoint 的控制点使用已声明的 DrawingML 命名空间创建，省去每个点的命名空间映射重建。路径、控制点与原生形状保持不变。
- 48,201 条路径的 PowerPoint 单独顺序对照：旧版 110.8 s / CPU 108.6 s，新版 93.6 s / CPU 91.4 s。其他同时运行测试的耗时不用于该对照。大型导出仍需约一分钟以上；完成后显式回收演示文稿部件与形状代理之间的循环引用。
- 原始轮廓文字补上标签交互标记，支持直接双击编辑。

## 可靠性证据

- 完整 Python 回归：632 passed、1 skipped、7 subtests passed。之后补跑最终导出与内存回收专项 3 项、增量 API 专项 3 项，均通过。加入内部元素编辑验收后，全部 39 个前端测试文件通过。
- 新增 HTTP 验证：规范化后的增量与重开结果相同、过期版本返回 409、旧完整响应兼容、模板/图形状态刷新、轻量审查保持作者确认。
- 新增编辑验证：恢复队列不写回过时快照、取消不会留下待执行拖动、松开鼠标落在最终位置、保存中结构变化与继续改字可以同时保留。
- 大恢复副本落盘失败时保留上一份恢复副本；超过 5,000 个形状的原生导出完成后，演示文稿对象可被释放，5,001 条测试曲线全部保留。
- 实机界面完成论文图双击改字、自动保存、撤销、重开；状态显示「已保存到本机」，原始标签与全部路径恢复。
- 原始场景重新渲染的 SVG 与优化前逐字节一致，SHA-256 为 `e2ea4b9cf97cd8f06f3239cfe402ec009bf30bbad4de0fc0a996f562c690be62`。
- SVG / PNG / PDF / PPTX 四种导出验收通过；SVG 和 PPTX 各 48,201 条原生路径，无位图，50 组原始文字轮廓保留。导出固定修订号。
- PowerPoint 新旧导出的 slide1.xml 逐字节一致，包括全部路径、贝塞尔控制点、文本、样式、位置及形状编号。大型 PPTX 仍属于耗时操作，不能用编辑耗时代替导出耗时。

## 可复现工具

`tools/benchmark_performance.py --scene SCENE_JSON --output REPORT_DIR` 在临时目录提交修订，不接触用户文档。加 `--baseline-python OLD_MODULE_DIR` 可比较旧版后端；该目录需包含旧版 scene_document、scene_render 与 scientific_library。

`--serve PORT --svg SVG_FILE --baseline-ui OLD_UI_DIR` 提供仅监听本机的可视化基准页；`?baseline=1` 测旧版，默认测当前版。旧 UI 目录需包含 canvas-editor.js 与 draft-store.js。页面显示脚本、恢复存储和节点保留的实际结果。

`node tools/verify_large_edit.mjs URL JOB REPORT_JSON` 对隔离运行服务执行生产编辑命令、真实增量保存和重开验证。

本轮参考并安装的 GitHub skills：

- [Cloudflare web-perf](https://github.com/cloudflare/skills/tree/main/skills/web-perf)：实测热点、DOM/网络证据及确认无用后再删除。
- [Python performance optimization](https://github.com/wshobson/agents/tree/main/plugins/python-development/skills/python-performance-optimization)：cProfile、热点调用、重复计算与拷贝分析。
