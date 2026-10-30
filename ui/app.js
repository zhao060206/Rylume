/* Cell Figure Studio — 三栏桌面工作台前端。
   结构：左栏一次性摆完参数，中间画布占主导，右栏结论永远在最上面。
   所有审查数字都来自后端 API，没有任何 mock。 */
(function () {
  "use strict";

  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // Job SVGs are inserted as markup so their fonts/ids work. Strip anything
  // executable first: old job folders and model output are untrusted input.
  function sanitizeSvg(text) {
    const doc = new DOMParser().parseFromString(text, "image/svg+xml");
    if (!doc || doc.querySelector("parsererror")) return "";
    doc.querySelectorAll("script,foreignObject,iframe,audio,video,object,embed")
      .forEach((node) => node.remove());
    doc.querySelectorAll("*").forEach((node) => {
      Array.from(node.attributes).forEach((attr) => {
        const name = attr.name.toLowerCase();
        const value = String(attr.value || "").trim().toLowerCase();
        if (name.startsWith("on")) node.removeAttribute(attr.name);
        else if ((name === "href" || name === "xlink:href")
          && (value.startsWith("javascript:") || value.startsWith("data:text/html"))) {
          node.removeAttribute(attr.name);
        }
      });
    });
    return new XMLSerializer().serializeToString(doc.documentElement);
  }

  const SAMPLES = [
    "软体机器人具身智能闭环推导系统图：多模态传感阵列、物理潜状态推理中枢、柔性执行器与自适应闭环反馈。中心-外围闭环布局，四段主回路与两条虚线反馈，英文标准术语，顶刊扁平矢量风格。",
    "材料制备与器件加工流程：前驱体配制 → 水凝胶交联 → 微结构图案化 → 器件封装与性能表征。横向五阶段流程，每阶段一个矢量图标与英文标签，底部标注关键工艺参数窗口。",
    "细胞外囊泡调控软骨修复的信号通路：配体分泌 → 膜受体结合 → 胞内激酶级联 → 转录因子入核 → 软骨基质合成表型。自上而下单向通路，英文标准术语，色盲友好配色。",
    "柔性压力传感器的分层剖面：封装层 → 电极层 → 介电微结构层 → 基底。等轴测分层剖面，标注材料厚度与功能，中性灰加单一强调色，可直接用于论文方法图。"
  ];

  const STATUS = {
    review: { label: "无硬伤", cls: "pill ok" },
    unverified: { label: "未验证", cls: "pill warn" },
    defects: { label: "有硬伤", cls: "pill bad" },
    failed: { label: "失败", cls: "pill err" },
    canceled: { label: "已取消", cls: "pill" },
    processing: { label: "生成中", cls: "pill warn" }
  };

  const SEV = {
    high: { label: "HIGH", cls: "pill bad" },
    medium: { label: "MEDIUM", cls: "pill warn" },
    low: { label: "LOW", cls: "pill" }
  };

  const KIND_LABEL = {
    overflow: "文字溢出", shift: "错位 / 悬空", occlusion: "遮挡", garbled: "乱码",
    missing: "缺少结构", layout: "版式", vision: "模型审查",
    "vision-unavailable": "模型审查不可用"
  };

  const QUICK = ["三处硬伤全部修掉", "统一色板", "箭头方向改正", "线宽提到 1.6px", "标签字号统一"];

  const STAGE_NAMES = {
    start: 0, research: 1, plan_scene: 1, generate: 2, ocr: 2, remove_text: 2,
    vectorize: 3, assemble: 3, qa: 4
  };

  const S = {
    jobs: [], job: null, currentId: null, activeId: null,
    mode: "image", shape: "rect", ratio: "1.414", archetype: null,
    w: 180, h: 127, dpi: 400,
    pxW: 1600, pxH: 1129,
    zoom: 1, fitW: 0, fitH: 0,
    literature: true, styleDna: null, refImage: null, originalBrief: "",
    filter: "all", query: "", expanded: false,
    inspectorOpen: true, annot: true,
    generating: false, pollTimer: null,
    review: { verdict: "none", legacy: false, rounds: 0, score: null, hasModel: false, model: "", findings: [], defects: [] },
    exports: [], lastSaved: ""
  };

  let CONFIG = {};
  let toastTimer = null;
  let wizardAnswers = {};
  let wizardQuestions = [];
  let wizardStep = 0;
  let wizardResult = null;
  let lastFocus = null;

  /* ------------------------------------------------------------ API */
  async function api(path, opts) {
    opts = opts || {};
    const init = {
      method: opts.method || "GET",
      headers: { "Content-Type": "application/json" },
      cache: "no-store"
    };
    if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
    const res = await fetch(path, init);
    const text = await res.text();
    let data = null;
    try { data = JSON.parse(text); } catch (e) { data = text; }
    if (!res.ok) throw new Error((data && data.error) || text || ("HTTP " + res.status));
    return data;
  }

  function toast(msg, kind) {
    const el = $("#toast");
    if (!el) return;
    $("#toast-text").textContent = msg;
    $("#toast-icon").innerHTML = kind === "alert"
      ? '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>'
      : '<path d="M20 6L9 17l-5-5"/>';
    $("#toast-icon").style.color = kind === "alert" ? "#FFC9BC" : "#9EE7C4";
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
  }

  /* ------------------------------------------------------- 画板参数 */
  function pxFromMm() {
    const ratio = S.w / S.h;
    const max = 1600;
    if (ratio >= 1) return [max, Math.round(max / ratio)];
    return [Math.round(max * ratio), max];
  }

  function clearRatioPressed() {
    $$("[data-ratio]").forEach((b) => b.setAttribute("aria-pressed", "false"));
  }

  function applyFormat() {
    [S.pxW, S.pxH] = pxFromMm();
    const ar = S.w / S.h;
    if (document.activeElement !== $("#out-w")) $("#out-w").value = S.w;
    if (document.activeElement !== $("#out-h")) $("#out-h").value = S.h;
    $("#out-ratio").value = ar.toFixed(3).replace(/0+$/, "").replace(/\.$/, "") + " : 1";
    $("#brief-mode").textContent = S.mode === "image" ? "素材生图 + 排版" : "纯矢量";
    $("#t-canvas").textContent = S.job && S.job.canvas
      ? S.job.canvas.join(" × ") + " px" : S.pxW + " × " + S.pxH + " px";
    fitPaper();
  }

  function fitPaper() {
    const host = $("#mat");
    if (!host) return;
    const availW = Math.max(280, host.clientWidth - 56);
    const availH = Math.max(220, host.clientHeight - 56);
    const ar = S.job && Array.isArray(S.job.canvas) && S.job.canvas[0] > 0 && S.job.canvas[1] > 0
      ? S.job.canvas[0] / S.job.canvas[1]
      : S.w / S.h;
    let wpx = Math.min(availW, availH * ar);
    if (!S.currentId) wpx = Math.min(availW, 620);
    S.fitW = wpx;
    S.fitH = wpx / ar;
    const paper = $("#paper");
    paper.style.width = Math.round(S.fitW * S.zoom) + "px";
    paper.style.height = Math.round(S.fitH * S.zoom) + "px";
  }

  function setZoom(z) {
    S.zoom = Math.min(2, Math.max(0.5, Math.round(z * 20) / 20));
    $("#zoom-val").textContent = Math.round(S.zoom * 100) + "%";
    fitPaper();
  }

  /* --------------------------------------------------------- 任务 */
  function findingsOf(job) {
    return (job && job.visual_findings || []).filter((f) =>
      !(f.kind === "shift" && /PPT 与 SVG/.test(f.message || "")));
  }

  function highCount(job) {
    return findingsOf(job).filter((f) => f.severity === "high").length;
  }

  // "100% no problem" target: high AND medium both block.
  function blockingCount(job) {
    return findingsOf(job).filter((f) =>
      (f.severity === "high" || f.severity === "medium")
      && f.kind !== "vision-unavailable").length;
  }

  function auditGap(job) {
    return findingsOf(job).some((f) => f.kind === "vision-unavailable")
      || job.visual_state === "unverified";
  }

  function jobState(job) {
    if (job.status === "failed" || job.status === "error") return "failed";
    if (job.status === "cancelled" || job.status === "canceled") return "canceled";
    if (job.status !== "completed") return "processing";
    if (blockingCount(job)) return "defects";
    return auditGap(job) ? "unverified" : "review";
  }

  function shortTitle(title) {
    let text = String(title || "").replace(/^【[^】]*】\s*/, "").trim();
    text = text.replace(/^(图表主题|主题|Title)\s*[：:]\s*/i, "").trim();
    text = text.replace(/[（(].*$/, " ").replace(/\s+/g, " ").trim();
    if (!text) return "未命名图版";
    const first = text.split(/[：:。；;\n]/)[0].trim();
    return (first || text).slice(0, 40);
  }

  function jobMeta(job) {
    const mode = job.illustration_mode === "image" ? "插画" : "标准";
    const rw = (job.report || {}).rework || {};
    const model = job.model_review || rw.model_review || {};
    const rounds = (model.rounds || []).length || rw.rounds_executed || 0;
    const canvas = job.canvas ? job.canvas.join("×") : "";
    return [canvas, mode, rounds ? ("审查 " + rounds + " 轮") : ""].filter(Boolean).join(" · ");
  }

  function timeOf(created) {
    if (typeof created !== "number") return "—";
    const d = new Date(created * 1000);
    const p = (n) => String(n).padStart(2, "0");
    return p(d.getHours()) + ":" + p(d.getMinutes());
  }

  function updateFilterLabels() {
    const counts = { all: S.jobs.length, review: 0, defects: 0, stopped: 0 };
    S.jobs.forEach((j) => {
      const st = jobState(j);
      if (st === "review" || st === "unverified") counts.review += 1;
      if (st === "defects") counts.defects += 1;
      if (st === "failed" || st === "canceled") counts.stopped += 1;
    });
    const labels = { all: "全部", review: "无硬伤", defects: "有硬伤", stopped: "失败/取消" };
    $$("[data-filter]").forEach((b) => {
      b.textContent = labels[b.dataset.filter] + " " + (counts[b.dataset.filter] || 0);
    });
  }

  function renderJobs() {
    updateFilterLabels();
    const list = $("#job-list");
    const q = S.query.trim().toLowerCase();
    const filtered = S.jobs.filter((j) => {
      const state = jobState(j);
      if (S.filter === "review" && state !== "review" && state !== "unverified") return false;
      if (S.filter === "defects" && state !== "defects") return false;
      if (S.filter === "stopped" && state !== "failed" && state !== "canceled") return false;
      if (q && ((j.title || "") + j.id).toLowerCase().indexOf(q) < 0) return false;
      return true;
    });
    const shown = S.expanded ? filtered : filtered.slice(0, 8);
    list.innerHTML = shown.length ? shown.map((j) => {
      const state = jobState(j);
      const st = STATUS[state] || STATUS.failed;
      const hi = blockingCount(j);
      const processing = state === "processing";
      const label = state === "defects" ? hi + " 处硬伤"
        : processing ? "生成中 " + Math.round(j.progress || 0) + "%" : st.label;
      return '<div class="job' + (j.id === S.currentId ? " sel" : "") + '" role="button" tabindex="0" data-job="' + esc(j.id) + '">'
        + '<div class="job-top"><span class="' + st.cls + '">' + esc(label) + '</span>'
        + (j.legacy ? '<span class="pill warn">旧版</span>' : "")
        + '<span class="job-id mono">' + esc(j.id) + '</span></div>'
        + '<div class="job-title">' + esc(shortTitle(j.title)) + '</div>'
        + '<div class="job-meta"><span>' + esc(jobMeta(j)) + '</span><span style="margin-left:auto">' + esc(timeOf(j.created)) + '</span></div>'
        + '<div class="job-acts">' + (processing ? "" : (state === "failed" || state === "error" || state === "cancelled"
          ? '<button type="button" class="retry-text" data-act="retry" title="用当前设置重新生成">再试一次</button>'
          : '<button type="button" data-act="retry" title="用当前引擎重绘">↻</button>'))
        + '<button type="button" data-act="folder" title="打开任务文件夹">▤</button>'
        + '<button type="button" data-act="delete" title="删除任务">×</button></div>'
        + '</div>';
    }).join("") : '<p style="font-size:12px;color:var(--ink-3);padding:10px 2px">没有符合当前条件的任务。</p>';

    $("#job-count").textContent = S.jobs.length;
    const more = $("#jobs-expand");
    more.textContent = S.expanded ? "只看前 8 条" : "展开全部";
    more.setAttribute("aria-disabled", filtered.length <= 8 ? "true" : "false");
    $("#jobs-clear").setAttribute("aria-disabled", S.jobs.length ? "false" : "true");
    $$("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === S.filter)));
  }

  async function refreshJobs() {
    const res = await api("/api/jobs");
    S.jobs = res.jobs || [];
    renderJobs();
  }

  async function loadJob(id, depth) {
    depth = depth || 0;
    // Opening a job must always reset the transient "drawing" state. Without
    // this, a completed job opened from the history list keeps the progress
    // panel at 100% forever (the old job's timer is still scheduled).
    clearInterval(S.pollTimer); S.pollTimer = null;
    clearTimeout(S.progressTimer); S.progressTimer = null;
    S.generating = false; S.activeId = null;
    $("#btn-draw").disabled = false;
    $("#progress").hidden = true;
    const job = await api("/api/jobs/" + id);
    if (job.next_job && depth < 5) {
      // Automatic rework produced a child; show the final result, not the
      // intermediate failure. Do not follow a child that died without output.
      const child = await api("/api/jobs/" + job.next_job).catch(() => null);
      if (child && (child.svg_url || child.status === "queued" || child.status === "processing")) {
        return loadJob(child.id, depth + 1);
      }
    }
    if (job.status === "queued" || job.status === "processing") {
      S.job = job; S.currentId = id; S.activeId = id; S.generating = true;
      $("#progress").hidden = false;
      $("#btn-draw").disabled = true;
      updateProgress(job);
      pollJob(id);
      renderJobs();
      return;
    }
    if (!job.svg_url) {
      // Keep failed jobs visible with a retry action instead of an empty stage.
      S.job = job;
      S.currentId = id;
      S.review = buildReview(job);
      $("#canvas-holder").hidden = true;
      $("#empty-state").hidden = false;
      $("#reviewbar").hidden = false;
      $("#proj-title").textContent = shortTitle(job.title);
      $("#proj-id").textContent = job.id;
      setExportEnabled(false);
      renderVerdict();
      renderScores();
      renderDefects();
      renderTask();
      renderRefs();
      renderLog();
      renderJobs();
      if (job.status === "failed" || job.status === "error") toast("任务失败：" + (job.error || "可点再试一次"), "alert");
      return;
    }
    const svgText = await fetch(job.svg_url).then((r) => r.text());
    const cleanSvg = sanitizeSvg(svgText);
    if (!cleanSvg) {
      toast("这张图的结果文件无法解析，已阻止载入", "alert");
      return;
    }
    S.job = job;
    S.currentId = id;
    if (job.illustration_mode === "image" || job.illustration_mode === "vector") {
      setMode(job.illustration_mode);
    }
    if (job.text) { $("#brief-input").value = job.text; syncBrief(); }
    S.originalBrief = job.original_text || "";
    $("#canvas-holder").innerHTML = cleanSvg;
    $("#canvas-holder").hidden = false;
    $("#empty-state").hidden = true;
    $("#reviewbar").hidden = false;
    $("#legacy-notice").hidden = !job.legacy;
    if (job.legacy) {
      const txt = $("#legacy-notice span");
      if (txt) txt.textContent = "任务 " + job.id + " 由旧版流程生成，历史审查结论已失效。";
    }
    $("#proj-title").textContent = shortTitle(job.title);
    $("#proj-id").textContent = job.id;
    setExportEnabled(true);
    $("#export-hint").hidden = true;
    if ($("#export-hint")) {
      $("#export-hint").textContent = job.illustration_mode === "image"
        ? "素材为位图，排版与文字可在 SVG / PPTX 中编辑" : "SVG / PPTX 全部可编辑";
      $("#export-hint").hidden = false;
    }
    if ($("#exp-svg")) $("#exp-svg").textContent = "SVG";
    if ($("#exp-pptx")) $("#exp-pptx").textContent = "PPTX";
    if ($("#exp-png")) $("#exp-png").textContent = "PNG";
    if ($("#exp-pdf")) $("#exp-pdf").textContent = "PDF";
    if ($("#export-hint")) $("#export-hint").textContent =
      job.illustration_mode === "image" ? "素材为位图，排版与文字可在 SVG / PPTX 中编辑" : "SVG / PPTX 全部可编辑";
    if (!S.exports.length) $("#saved-bar").hidden = true;
    $("#toggle-diff").setAttribute("aria-disabled", String(!(job.diff_url || job.comparison_url)));
    S.review = buildReview(job);
    renderVerdict();
    renderScores();
    renderDefects();
    renderTask();
    renderRefs();
    renderLog();
    applyAnnot();
    applyFormat();
    fitPaper();
    renderJobs();
  }

  function resetStage(note) {
    clearInterval(S.pollTimer); S.pollTimer = null;
    clearTimeout(S.progressTimer); S.progressTimer = null;
    S.generating = false; S.activeId = null;
    $("#progress").hidden = true;
    $("#btn-draw").disabled = false;
    S.job = null;
    S.currentId = null;
    S.review = { verdict: "none", legacy: false, rounds: 0, score: null, hasModel: false, model: "", findings: [], defects: [] };
    S.exports = [];
    S.lastSaved = "";
    $("#canvas-holder").innerHTML = "";
    $("#canvas-holder").hidden = true;
    $("#empty-state").hidden = false;
    $("#reviewbar").hidden = true;
    $("#saved-bar").hidden = true;
    $("#export-hint").hidden = false;
    $("#legacy-notice").hidden = true;
    $("#proj-title").textContent = "未打开图版";
    $("#proj-id").textContent = "—";
    setExportEnabled(false);
    $("#draw-note").textContent = S.mode === "image"
      ? "逐对象生成细胞/专业素材，再由模型排版；文字与标注可编辑"
      : "每个图元都是矢量路径，文字可在 PPT 中直接改";
    renderVerdict();
    renderScores();
    renderDefects();
    renderTask();
    renderRefs();
    renderLog();
    applyFormat();
    fitPaper();
    renderJobs();
  }

  function setExportEnabled(on) {
    const raster = !!(S.job && (S.job.report || {}).raster);
    $("#exp-svg").disabled = !on || raster;
    $("#exp-pptx").disabled = !on || raster;
    $("#exp-png").disabled = !on;
    if ($("#exp-pdf")) $("#exp-pdf").disabled = !on;
    $("#toggle-diff").setAttribute("aria-disabled", on ? "false" : "true");
    if (!on) $("#toggle-diff").setAttribute("aria-pressed", "false");
  }

  /* ------------------------------------------------------- 审查 */
  function buildReview(job) {
    const legacy = !!job.legacy;
    const findings = legacy ? [] : findingsOf(job);
    const model = job.model_review || ((job.report || {}).rework || {}).model_review || {};
    const roundList = Array.isArray(model.rounds) ? model.rounds
      : (model.verdict ? [model] : []);
    const reworkRounds = ((job.report || {}).rework || {}).rounds_executed || 0;
    const rounds = Math.max(roundList.length, reworkRounds);
    const last = roundList[roundList.length - 1] || {};
    const rawScore = last.score != null ? Number(last.score) : null;
    let score = rawScore != null && isFinite(rawScore) ? Math.max(0, Math.min(100, rawScore)) : null;
    const highs = findings.filter((f) => f.severity === "high" && f.kind !== "vision-unavailable");
    const auditGap = job.visual_state === "unverified"
      || findings.some((f) => f.kind === "vision-unavailable");
    // A local-only pass must not display a model score; it has none.
    if (auditGap) score = null;
    else if (!legacy) {
      const defectsNow = findings.filter((f) => f.severity === "high" || f.severity === "medium").length;
      const adviceNow = findings.filter((f) => f.severity === "low").length;
      // Score is the audit verdict, not a random model sentiment number.
      if (defectsNow) score = Math.max(0, Math.min(score == null ? 60 : score, 65 - defectsNow * 8));
      else score = adviceNow ? (score == null ? 95 : Math.max(85, score)) : 100;
    }
    const defects = findings.map((f, i) => ({
      id: "D" + (i + 1), sev: f.severity || "medium",
      title: f.message || "缺陷",
      note: (KIND_LABEL[f.kind] || f.kind || "") + (f.suggestion ? " · " + f.suggestion : ""),
      loc: f.box && f.box.length === 4 ? "(" + Math.round(f.box[0]) + ", " + Math.round(f.box[1]) + ")" : "整图范围",
      box: f.box || null
    }));
    return {
      verdict: legacy ? "legacy" : (auditGap && !highs.length ? "unverified"
        : (highs.length || job.visual_state === "failed" ? "fail" : "pass")),
      auditGap: auditGap,
      legacy: legacy, rounds: rounds, score: score, hasModel: roundList.length > 0,
      model: last.model || (roundList[0] || {}).model || "本地几何审查",
      findings: findings, defects: defects
    };
  }

  function renderVerdict() {
    const r = S.review;
    const panel = $("#verdict-panel"), bar = $("#rb-verdict");
    if (!S.currentId || r.verdict === "none") {
      panel.className = "verdict-card";
      $("#vp-icon").innerHTML = '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>';
      $("#vp-title").innerHTML = '尚未生成<span class="sub mono">—</span>';
      $("#vp-text").textContent = "生成完成后，这里显示审查结论、模型轮次与综合分数。";
      bar.className = "rb-verdict ok";
      $("#rb-icon").innerHTML = '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>';
      $("#rb-title").textContent = "等待生成";
      $("#rb-sub").textContent = "尚无审查结果";
      $("#rb-counts").hidden = true;
      $("#act-accept").setAttribute("aria-disabled", "true");
      $("#act-autofix").setAttribute("aria-disabled", "true");
      $("#act-retry").hidden = true;
      return;
    }
    const jobFailed = S.job && ["failed", "error", "cancelled", "canceled"].includes(S.job.status);
    if (jobFailed) {
      const canceled = ["cancelled", "canceled"].includes(S.job.status);
      panel.className = "verdict-card " + (canceled ? "warn" : "bad");
      $("#vp-icon").innerHTML = '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>';
      $("#vp-title").innerHTML = (canceled ? "已取消" : "生成失败")
        + '<span class="sub mono">' + (S.job.id || "") + '</span>';
      $("#vp-text").textContent = canceled
        ? "任务已取消，点「再试一次」可以重新生成。"
        : (S.job.error || S.job.message || "模型服务没有返回结果，点「再试一次」重新生成。");
      bar.className = "rb-verdict " + (canceled ? "warn" : "bad");
      $("#rb-icon").innerHTML = '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>';
      $("#rb-title").textContent = canceled ? "已取消" : "生成失败";
      $("#rb-sub").textContent = "可再试一次";
      $("#rb-counts").hidden = true;
      $("#act-retry").hidden = false;
      $("#act-autofix").hidden = true;
      $("#act-edit").hidden = true;
      $("#act-accept").hidden = true;
      return;
    }
    $("#act-retry").hidden = true;
    $("#act-autofix").hidden = false;
    $("#act-edit").hidden = false;
    $("#act-accept").hidden = false;
    if (r.legacy) {
      panel.className = "verdict-card legacy";
      $("#vp-icon").innerHTML = '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>';
      $("#vp-title").innerHTML = '旧版审查结果<span class="sub mono">已失效</span>';
      $("#vp-text").textContent = "这张图由旧版流程产出，历史缺陷记录不再作为验收依据。点「重新审查」跑当前几何检查与视觉模型审查。";
      bar.className = "rb-verdict warn";
      $("#rb-icon").innerHTML = '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>';
      $("#rb-title").textContent = "旧版结果";
      $("#rb-sub").textContent = "等待重新审查";
      $("#rb-counts").hidden = true;
      $("#act-accept").setAttribute("aria-disabled", "true");
      $("#act-autofix").setAttribute("aria-disabled", "true");
      return;
    }
    const highs = r.findings.filter((f) => f.severity === "high");
    const med = r.findings.filter((f) => f.severity === "medium");
    const low = r.findings.filter((f) => f.severity === "low");
    // Acceptance requires a real model pass and zero high/medium findings.
    // "100% no problem" = zero high AND zero medium. Low is style advice only.
    const ok = highs.length === 0 && med.length === 0 && r.hasModel;
    const unverified = !!(r.auditGap && ok);
    const metrics = r.rounds + " 轮" + (r.score != null ? " · " + r.score + " 分" : " · 无模型评分");
    const title = unverified ? "未验证" : ok ? (r.hasModel ? "审查通过" : "本地审查通过")
      : highs.length ? "审查未通过" : "待打磨";
    panel.className = "verdict-card " + (ok && !unverified ? "ok" : highs.length ? "bad" : "warn");
    $("#vp-icon").innerHTML = ok && !unverified
      ? '<path d="M20 6L9 17l-5-5"/>'
      : '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>';
    $("#vp-title").innerHTML = title + '<span class="sub mono">' + metrics + '</span>';
    const parts = [];
    if (med.length) parts.push(med.length + " 条警告");
    if (low.length) parts.push(low.length + " 条建议");
    $("#vp-text").textContent = unverified
      ? "视觉模型没有参与本轮审查：这张图只通过了本地几何检查，没有模型评分。"
        + "请检查设置里的视觉模型连接，点「重新审查」通过后再验收。"
      : ok
      ? (low.length ? "硬伤与警告均已清零；另有 " + low.length + " 条风格建议，不阻断验收。"
        : "没有检出硬伤或警告，可以确认验收。")
      : "检出 " + highs.length + " 处硬伤、" + med.length + " 处警告"
        + (low.length ? "、" + low.length + " 条建议" : "") + "，尚未达到零问题。"
        + (r.auditGap ? "另有视觉模型审查未执行。" : "")
        + "点「AI 自动修复」按这份清单逐轮修复并重新审查（最多 3 轮）。";
    bar.className = "rb-verdict " + (ok && !unverified ? "ok" : highs.length ? "bad" : "warn");
    $("#rb-icon").innerHTML = ok && !unverified ? '<path d="M20 6L9 17l-5-5"/>' : '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>';
    $("#rb-title").textContent = title;
    $("#rb-sub").textContent = metrics;
    $("#rb-counts").hidden = false;
    $("#c-fail").textContent = highs.length;
    $("#c-sugg").textContent = med.length + low.length;
    $("#act-accept").setAttribute("aria-disabled", ok && !unverified && r.hasModel ? "false" : "true");
    $("#act-accept").title = unverified ? "视觉审查完成前不能验收"
      : !r.hasModel ? "先点「重新审查」完成模型审查"
      : ok ? "确认验收" : "硬伤与警告清零后才能验收";
    const fixable = r.findings.filter((f) =>
      (f.severity === "high" || f.severity === "medium") && f.kind !== "vision-unavailable");
    $("#act-autofix").setAttribute("aria-disabled", fixable.length ? "false" : "true");
    $("#act-autofix").title = fixable.length
      ? "按审查结论逐轮修复并重新审查（最多 3 轮）"
      : "当前没有可修复的问题";
  }

  function renderScores() {
    const r = S.review;
    const has = !!S.currentId && !r.legacy;
    const score = r.score == null ? null : Math.round(r.score);
    const hasHigh = r.findings.some((f) => f.severity === "high");
    const scoreCls = !has || score == null ? ""
      : hasHigh ? " low"
      : score >= 80 ? " good" : score >= 60 ? " mid" : " mid";
    $("#score-box").className = "score" + scoreCls;
    $("#score-val").textContent = !has || score == null ? "—" : String(score);
    $("#k-rounds").textContent = !has ? "—" : (r.rounds ? r.rounds + " 轮" : "—");
    $("#k-vision").textContent = !has ? "—" : (r.legacy ? "旧版流程" : (r.model || "—"));
    const high = r.findings.filter((f) => f.severity === "high" && f.kind !== "vision-unavailable").length;
    const mid = r.findings.filter((f) => f.severity === "medium").length;
    const low = r.findings.filter((f) => f.severity === "low").length;
    const total = Math.max(1, high + mid + low);
    $("#score-bars").innerHTML = !has
      ? '<p style="font-size:11.5px;line-height:1.6;color:var(--ink-3);margin-top:9px">旧版任务没有可引用的模型评分，重新审查后会写入。</p>'
      : [["hard", "硬伤", high], ["medium", "警告", mid], ["low", "建议", low]].map(([cls, label, n]) =>
        '<div class="meter ' + cls + '"><div class="m-top"><span>' + label + '</span><b>' + n + '</b></div>'
        + '<div class="m-track"><div class="m-fill" style="width:' + (n ? Math.max(12, Math.round(n / total * 100)) : 0) + '%"></div></div></div>').join("");
  }

  function renderDefects() {
    const list = $("#defect-list");
    const defects = S.review.defects;
    $("#defect-count").textContent = defects.length;
    const rw = (S.job && S.job.report && S.job.report.rework) || {};
    const before = (rw.before_findings || []).filter((f) => f.kind !== "vision-unavailable").length;
    const after = (rw.after_findings || []).filter((f) => f.kind !== "vision-unavailable").length;
    const steps = Array.isArray(rw.history) ? rw.history : [];
    let trace = "";
    if (steps.length || rw.changed !== undefined) {
      trace = '<div class="repair-trace" style="margin-top:12px;padding:10px;border:1px solid var(--line);border-radius:8px;font-size:12px;line-height:1.65;color:var(--ink-3)">'
        + '<b style="color:var(--ink)">AI 修复记录</b>'
        + '<div>' + (rw.changed === false ? "本轮没有产生像素变化（修复补丁未生效）"
          : rw.changed === true ? "本轮输出已发生变化" : "尚无修复快照") + '</div>'
        + (before || after ? '<div>审查问题：修复前 ' + before + ' 条 → 修复后 ' + after + ' 条</div>' : " ")
        + steps.slice(-4).map((h) => {
          const acts = (h.actions || []).join("；");
          const vActs = (h.vision_actions || []).join("；");
          const err = h.editor_error ? "编辑模型失败：" + h.editor_error : "";
          return '<div style="margin-top:6px">第 ' + (h.round || "?") + ' 轮：'
            + (acts || vActs || err || "重渲染并复审") + '</div>';
        }).join("")
        + '</div>';
    }
    if (!S.currentId) {
      list.innerHTML = '<p style="font-size:12px;color:var(--ink-3)">尚未生成，暂无缺陷记录。</p>';
      return;
    }
    if (S.review.legacy) {
      list.innerHTML = '<p style="font-size:12px;line-height:1.7;color:var(--ink-3)">旧版记录已失效。点上方「重新审查」后，这里会列出当前流程真正检出的缺陷及画布坐标。</p>';
      return;
    }
    if (!defects.length) {
      list.innerHTML = '<p style="font-size:12px;color:var(--ink-3)">本次审查没有检出缺陷。</p>' + trace;
      return;
    }
    list.innerHTML = defects.map((d) => {
      const s = SEV[d.sev] || SEV.medium;
      return '<div class="defect" data-defect="' + d.id + '" role="button" tabindex="0">'
        + '<div class="defect-top"><span class="' + s.cls + '">' + s.label + '</span>'
        + '<span class="code mono">' + d.id + '</span></div>'
        + '<div class="defect-title">' + esc(d.title) + '</div>'
        + '<div class="defect-note">' + esc(d.note) + '</div>'
        + '<span class="defect-loc">画布定位 ' + esc(d.loc) + '</span></div>';
    }).join("") + trace;
  }

  function locate(id) {
    const d = S.review.defects.find((x) => x.id === id);
    if (!d) return;
    $$("#defect-list .defect").forEach((x) => x.classList.toggle("on", x.dataset.defect === id));
    if (!d.box) {
      // 视觉模型的问题描述的是整张图，没有局部坐标：直接高亮整块画布。
      const svg = $("#canvas-holder svg");
      if (!svg) { toast("请先打开一张图", "alert"); return; }
      let layer = $("g#locate-layer", svg);
      if (!layer) {
        layer = document.createElementNS("http://www.w3.org/2000/svg", "g");
        layer.setAttribute("id", "locate-layer");
        svg.appendChild(layer);
      }
      const vb = (svg.getAttribute("viewBox") || "0 0 100 100").split(/[\s,]+/).map(Number);
      layer.innerHTML = '<rect x="' + (vb[0] || 0) + '" y="' + (vb[1] || 0) + '" width="' + (vb[2] || 100)
        + '" height="' + (vb[3] || 100) + '" rx="2"/>';
      toast("该问题针对整张图，已高亮全画布");
      return;
    }
    const svg = $("#canvas-holder svg");
    if (!svg) return;
    let layer = $("g#locate-layer", svg);
    if (!layer) {
      layer = document.createElementNS("http://www.w3.org/2000/svg", "g");
      layer.setAttribute("id", "locate-layer");
      svg.appendChild(layer);
    }
    layer.innerHTML = '<rect x="' + (d.box[0] - 4) + '" y="' + (d.box[1] - 4) + '" width="' + Math.max(10, d.box[2] + 8)
      + '" height="' + Math.max(10, d.box[3] + 8) + '" rx="2"/>';
    const vb = (svg.getAttribute("viewBox") || "").split(/[\s,]+/).map(Number);
    const sr = svg.getBoundingClientRect(), vp = $("#mat"), vr = vp.getBoundingClientRect();
    const sc = sr.width / (vb[2] || svg.clientWidth || 1);
    const cx = sr.left - vr.left + (d.box[0] + d.box[2] / 2 - (vb[0] || 0)) * sc;
    const cy = sr.top - vr.top + (d.box[1] + d.box[3] / 2 - (vb[1] || 0)) * sc;
    vp.scrollLeft += cx - vp.clientWidth / 2;
    vp.scrollTop += cy - vp.clientHeight / 2;
    toast("已定位：" + d.title.slice(0, 42));
  }

  function applyAnnot() {
    const svg = $("#canvas-holder svg");
    if (!svg) return;
    let layer = $("g#locate-layer", svg);
    if (!S.annot || !S.review.findings.length) {
      if (layer) layer.innerHTML = "";
      return;
    }
    if (!layer) {
      layer = document.createElementNS("http://www.w3.org/2000/svg", "g");
      layer.setAttribute("id", "locate-layer");
      svg.appendChild(layer);
    }
    layer.innerHTML = S.review.findings.filter((f) => f.box && f.box.length === 4).map((f) =>
      '<rect x="' + (f.box[0] - 2) + '" y="' + (f.box[1] - 2) + '" width="' + Math.max(6, f.box[2] + 4)
      + '" height="' + Math.max(6, f.box[3] + 4) + '" rx="2" opacity="0.55"/>').join("");
  }

  /* --------------------------------------------------------- 任务信息 */
  function renderTask() {
    const job = S.job;
    $("#task-id").textContent = job ? job.id : "—";
    $("#t-status").textContent = !job ? "—"
      : job.visual_state === "confirmed" ? "已验收"
      : job.legacy ? "旧版审查"
      : job.visual_state === "unverified" ? "待重新审查"
      : job.status === "failed" || job.status === "error" ? "失败"
      : job.status === "cancelled" ? "已取消"
      : job.status === "completed" ? "待验收" : "生成中";
    $("#t-time").textContent = job && job.duration != null ? Number(job.duration).toFixed(1) + " 秒" : "—";
    $("#t-mode").textContent = (job ? job.illustration_mode : S.mode) === "image" ? "素材生图 + 排版" : "纯矢量";
    const refs = job && job.research ? (Number(job.research.direct_count || 0) + Number(job.research.style_count || 0)) : 0;
    $("#t-refs").textContent = refs + " 张";
    $("#t-calls").textContent = S.currentId && S.review.rounds ? S.review.rounds + " 轮" : "—";
    $("#t-start").textContent = job ? timeOf(job.created) : "—";
    $("#stage-dim").textContent = (job && job.canvas ? job.canvas.join(" × ") : S.pxW + " × " + S.pxH) + " px";
    $("#draw-note").textContent = !job
      ? (S.mode === "image" ? "逐对象生成素材后自动排版，文字与标注可编辑" : "最多 3 轮；硬伤与警告清零才通过")
      : (job.visual_state === "confirmed" ? "已验收 · 可重绘或用语言指令修改" : "审查结果在右栏");
  }

  function renderRefs() {
    const body = $("#pane-refs-body");
    if (!body) return;
    const res = (S.job && S.job.research) || {};
    const thumbs = (res.thumbs || []).filter((t) => t && t.relevance && t.relevance !== "unverified");
    $("#ref-count").textContent = thumbs.length;
    if (!S.job) {
      body.innerHTML = '<p style="font-size:12px;line-height:1.7;color:var(--ink-3)">生成时会检索并分析已发表配图，只展示真正参与本次绘制的样本。</p>';
      return;
    }
    if (!thumbs.length) {
      let why = "本次没有可用的已分析配图。";
      if (res.error) why = "文献检索失败：" + res.error;
      else if (S.job.literature_enabled === false) why = "本次生成关闭了文献检索。";
      else if (res.live_count) why = "已分析 " + res.live_count + " 张，但没有与目标图型或系统架构相关的样本。";
      body.innerHTML = '<p style="font-size:12px;line-height:1.7;color:var(--ink-3)">' + esc(why)
        + '生成时使用内置风格档案。</p>';
      return;
    }
    body.innerHTML = thumbs.slice(0, 8).map((t) => {
      const rel = t.relevance === "direct" ? "同图型" : (t.relevance === "style" ? "架构参考" : "配色参考");
      return '<div class="thumb">'
        + '<div class="thumb-top"><span class="thumb-fig"><img src="/api/research/figure?path=' + encodeURIComponent(t.path) + '" alt="' + esc(t.caption || "参考配图") + '" loading="lazy"/></span>'
        + '<span class="thumb-txt"><span class="nm">' + esc((t.caption || "已发表配图").slice(0, 80)) + '</span></span></div>'
        + '<span class="thumb-tags"><span class="pill">' + rel + '</span>'
        + (t.type ? '<span class="pill">' + esc(t.type) + '</span>' : "") + '</span>'
        + '<span class="thumb-note">' + esc(t.source || "OA 论文") + ' · 只提取版式与配色规则，不改科学内容。</span></div>';
    }).join("");
    $$(".thumb-fig img", body).forEach((img) => {
      img.style.width = "100%"; img.style.height = "100%"; img.style.objectFit = "cover";
    });
    const rules = (res.rules || []).filter(Boolean).slice(0, 6);
    if (rules.length) {
      body.insertAdjacentHTML("beforeend", '<div class="ref-rules"><b>学习到的排版规则</b>'
        + '<span>已注入规划提示词；你明确写出的空间布局优先于这些参考规则。</span>'
        + '<ul>' + rules.map((rule) => '<li>' + esc(rule) + '</li>').join("") + '</ul></div>');
    }
  }

  function renderLog() {
    const box = $("#export-log");
    $("#log-count").textContent = S.exports.length;
    if (!S.exports.length) {
      box.innerHTML = '<p style="font-size:12px;color:var(--ink-3)">尚无导出记录。</p>';
      return;
    }
    box.innerHTML = S.exports.slice().reverse().map((e) =>
      '<div class="log-row"><span class="fmt">' + esc(e.fmt) + '</span><span class="info">' + esc(e.size)
      + '</span><span class="when">' + esc(e.when) + '</span></div>').join("");
  }

  /* ------------------------------------------------------- 进度 */
  function updateProgress(job) {
    const pct = Math.max(1, Math.round(job.progress || 0));
    let idx = 0;
    (job.stages || []).forEach((st) => {
      if (st.state === "done" || st.state === "running") {
        idx = Math.max(idx, STAGE_NAMES[st.name] != null ? STAGE_NAMES[st.name] : idx);
      }
    });
    $("#pr-fill").style.width = pct + "%";
    $("#pr-pct").textContent = pct + "%";
    $("#pr-bar").setAttribute("aria-valuenow", String(pct));
    const running = (job.stages || []).find((s) => s.state === "running");
    $("#pr-stage").textContent = running ? (running.detail || running.label) : (job.message || "处理中");
    const elapsed = Number(job.elapsed || 0);
    const eta = pct > 4 ? Math.max(0, elapsed * (100 - pct) / pct) : null;
    $("#pr-eta").textContent = eta == null ? "预估中…" : "预计剩余 " + Math.round(eta) + " 秒";
    $$("#pr-steps li").forEach((li, i) => { li.className = i < idx ? "done" : i === idx ? "on" : ""; });
  }

  function pollJob(id) {
    clearInterval(S.pollTimer);
    S.pollTimer = setInterval(async () => {
      try {
        const job = await api("/api/jobs/" + id);
        if (S.activeId === id) updateProgress(job);
        const row = S.jobs.find((j) => j.id === id);
        if (row) {
          row.status = job.status;
          row.progress = job.progress;
          row.visual_findings = job.visual_findings;
        }
        if (job.status === "completed") {
          clearInterval(S.pollTimer);
          S.pollTimer = null;
          // Automatic rework: a generation with blocking findings chains an
          // auto-fix job; follow it without asking the user to press anything.
          if (job.next_job) {
            S.currentId = job.next_job;
            S.activeId = job.next_job;
            S.generating = true;
            $("#btn-draw").disabled = true;
            $("#progress").hidden = false;
            $("#pr-fill").style.width = "0%";
            $("#pr-pct").textContent = "0%";
            $("#pr-stage").textContent = "检出 " + blockingCount(job) + " 处问题，正在自动返工";
            pollJob(job.next_job);
            await refreshJobs();
            toast("检出 " + blockingCount(job) + " 处问题，已自动返工（最多 3 轮）", "alert");
            return;
          }
          S.generating = false;
          S.activeId = null;
          $("#btn-draw").disabled = false;
          $$("#pr-steps li").forEach((li) => li.className = "done");
          if (S.currentId === id) await loadJob(id);
          await refreshJobs();
          S.progressTimer = setTimeout(() => {
            S.progressTimer = null;
            $("#progress").hidden = true;
          }, 900);
          const hi = blockingCount(job);
          toast(hi ? "生成完成 · " + hi + " 处问题待修复" : "生成完成 · 零问题通过", hi ? "alert" : "check");
          if (document.hidden) api("/api/flash", { method: "POST", body: {} }).catch(() => {});
        } else if (job.status === "failed" || job.status === "error" || job.status === "cancelled") {
          clearInterval(S.pollTimer);
          S.pollTimer = null;
          S.generating = false;
          S.activeId = null;
          $("#btn-draw").disabled = false;
          $("#progress").hidden = true;
          await refreshJobs();
          toast(job.status === "cancelled" ? "任务已取消" : "生成失败：" + (job.error || job.message || ""), "alert");
        } else {
          renderJobs();
        }
      } catch (e) {
        clearInterval(S.pollTimer);
        S.pollTimer = null;
        S.generating = false;
        S.activeId = null;
        $("#btn-draw").disabled = false;
        $("#progress").hidden = true;
        toast("进度读取失败：" + e.message, "alert");
      }
    }, 1000);
  }

  async function startGenerate() {
    if (S.generating) return;
    clearTimeout(S.progressTimer); S.progressTimer = null;
    const text = $("#brief-input").value.trim();
    if (!text) { $("#brief-input").focus(); toast("请先填写研究构想，或点一个示例", "alert"); return; }
    S.generating = true;
    $("#btn-draw").disabled = true;
    $("#progress").hidden = false;
    $("#pr-fill").style.width = "0%";
    $("#pr-pct").textContent = "0%";
    $("#pr-stage").textContent = "提交任务";
    $("#pr-eta").textContent = "预估中…";
    $$("#pr-steps li").forEach((li) => li.className = "");
    try {
      const res = await api("/api/generate", {
        method: "POST",
        body: {
          text: text,
          original_text: S.originalBrief || text,
          canvas: [S.pxW, S.pxH],
          canvas_mm: [S.w, S.h],
          dpi: S.dpi,
          viewport_shape: S.shape === "round" ? "card" : S.shape,
          style_dna: S.styleDna,
          reference_layout: (S.styleDna && S.styleDna.layout_analysis) || undefined,
          reference_layout_mode: S.referenceLayoutMode || undefined,
          archetype: S.archetype || undefined,
          literature: S.literature,
          illustration_mode: S.mode
        }
      });
      S.currentId = res.job_id;
      S.activeId = res.job_id;
      pollJob(res.job_id);
      await refreshJobs();
    } catch (e) {
      S.generating = false;
      $("#btn-draw").disabled = false;
      $("#progress").hidden = true;
      toast("提交失败：" + e.message, "alert");
    }
  }

  async function retryJob(id) {
    try {
      const res = await api("/api/jobs/" + id + "/retry", { method: "POST", body: {} });
      S.currentId = res.job_id;
      S.activeId = res.job_id;
      S.generating = true;
      $("#btn-draw").disabled = true;
      $("#progress").hidden = false;
      $("#pr-fill").style.width = "0%";
      $("#pr-pct").textContent = "0%";
      pollJob(res.job_id);
      await refreshJobs();
      toast("已用当前引擎重新提交", "check");
    } catch (e) { toast("重试失败：" + e.message, "alert"); }
  }

  /* --------------------------------------------------------- 导出 */
  async function saveAs(fmt, extra) {
    if (!S.currentId) return;
    const label = fmt.toUpperCase();
    try {
      const res = await api("/api/jobs/" + S.currentId + "/save-as", {
        method: "POST",
        body: Object.assign({ format: fmt }, extra || {})
      });
      if (res.canceled) { toast("已取消保存"); return; }
      showSaved(label, res.path);
      S.exports.push({ fmt: label, size: "本地文件", when: timeOf(Date.now() / 1000) });
      renderLog();
      toast("已保存到 " + res.path, "check");
    } catch (e) { toast("保存失败：" + e.message, "alert"); }
  }

  function waitPpt(id) {
    return new Promise((resolve, reject) => {
      const timer = setInterval(async () => {
        try {
          const st = await api("/api/jobs/" + id + "/ppt-status");
          const pct = Math.max(1, Math.round(st.pct || 0));
          $("#pr-fill").style.width = pct + "%";
          $("#pr-pct").textContent = pct + "%";
          $("#pr-stage").textContent = (st.stage || "导出 PPTX") + " · " + pct + "%";
          $("#pr-eta").textContent = st.eta == null ? "预估中…" : "预计剩余 " + Math.round(st.eta) + " 秒";
          if (st.state === "done") { clearInterval(timer); resolve(st); }
          else if (st.state === "failed") { clearInterval(timer); reject(new Error(st.error || "导出失败")); }
        } catch (e) { clearInterval(timer); reject(e); }
      }, 900);
    });
  }

  async function exportPptx() {
    if (!S.currentId) return;
    const id = S.currentId;
    $("#progress").hidden = false;
    $("#pr-stage").textContent = "准备导出 PPTX";
    $("#pr-fill").style.width = "0%";
    $("#pr-pct").textContent = "0%";
    try {
      const res = await api("/api/jobs/" + id + "/ppt", { method: "POST", body: {} });
      if (res.started) await waitPpt(id);
      $("#progress").hidden = true;
      S.job = await api("/api/jobs/" + id);
      $("#toggle-diff").setAttribute("aria-disabled", String(!(S.job.diff_url || S.job.comparison_url)));
      await saveAs("pptx");
    } catch (e) {
      $("#progress").hidden = true;
      toast("PPTX 导出失败：" + e.message, "alert");
    }
  }

  function showSaved(title, path) {
    S.lastSaved = path || "";
    $("#saved-title").textContent = "已保存 " + title;
    $("#saved-path").textContent = path || "";
    $("#saved-path").title = path || "";
    $("#saved-bar").hidden = !path;
    $("#export-hint").hidden = !!path;
  }

  /* --------------------------------------------------------- 设置 */
  function renderSettings() {
    const groups = [
      { n: "01", key: "text", name: "文本模型", role: "构图 / 规划" },
      { n: "02", key: "image", name: "生图模型", role: "底图生成" },
      { n: "03", key: "vision", name: "视觉模型", role: "参考图 / 审查" }
    ];
    $("#settings-body").innerHTML = groups.map((g, i) => {
      const m = CONFIG[g.key] || {};
      return '<div class="mgroup"><div class="mgroup-hd"><span class="n">' + g.n + '</span><span class="nm">' + g.name
        + '</span><span class="role">' + g.role + '</span></div><div class="mgroup-bd">'
        + '<div class="mfield"><label for="mg-base-' + i + '">Base URL</label><input class="inp" id="mg-base-' + i + '" type="text" value="' + esc(m.base_url || "") + '" /></div>'
        + '<div class="mfield"><label for="mg-model-' + i + '">Model</label><input class="inp" id="mg-model-' + i + '" type="text" value="' + esc(m.model || "") + '" /></div>'
        + '<div class="mfield"><label for="mg-key-' + i + '">API Key</label><div class="row">'
        + '<input class="inp" id="mg-key-' + i + '" type="password" value="' + esc(m.api_key || "") + '" placeholder="' + (m.api_key_set ? "已保存，留空保持不变" : "粘贴 API Key") + '" />'
        + '<button type="button" class="icon-btn" data-toggle-key="' + i + '" aria-label="显示或隐藏密钥" aria-pressed="false">'
        + '<svg class="i i-sm" viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.6"/></svg></button></div></div>'
        + '<div class="conn"><span class="dot"></span><span data-conn="' + g.key + '">尚未测试</span>'
        + '<button type="button" data-test-group="' + g.key + '">测试</button></div>'
        + '</div></div>';
    }).join("") + '<div class="mgroup"><div class="mgroup-hd"><span class="n">04</span><span class="nm">高级出图偏好</span><span class="role">本地</span></div>'
      + '<div class="mgroup-bd"><div class="mfield"><label for="cfg-engine">素材转 SVG 引擎</label><select class="inp" id="cfg-engine">'
      + '<option value="hifi">高保真自动</option><option value="vtracer">vtracer 快速</option><option value="starvector">StarVector</option></select></div>'
      + '<div class="mfield"><label for="cfg-render">出图方式</label><select class="inp" id="cfg-render">'
      + '<option value="compose">组件拼装</option><option value="fidelity">保真优先</option><option value="vector">整图矢量化</option></select></div>'
      + '<div class="mfield"><label for="cfg-default-mode">默认出图模式</label><select class="inp" id="cfg-default-mode">'
      + '<option value="image">素材生图 + 排版</option><option value="vector">纯矢量</option></select></div>'
      + '<div class="mfield"><label for="cfg-quality">出图质量</label><select class="inp" id="cfg-quality"><option value="hd">高清</option><option value="standard">标准</option></select></div>'
      + '<div class="mfield"><label for="cfg-ocr">文字识别</label><select class="inp" id="cfg-ocr"><option value="auto">自动</option><option value="off">关闭</option></select></div>'
      + '<div class="mfield"><label for="cfg-font">图中字体</label><input class="inp" id="cfg-font" type="text" value="' + esc(CONFIG.font || "Times New Roman") + '" /></div>'
      + '<div class="conn"><span class="dot"></span><span id="conn-all">整体连接检查</span><button type="button" id="test-all">测试全部</button></div>'
      + '</div></div>';
    $("#cfg-engine").value = (CONFIG.vectorize || {}).engine || "hifi";
    $("#cfg-render").value = CONFIG.render_mode || "compose";
    if ($("#cfg-default-mode")) $("#cfg-default-mode").value = CONFIG.default_illustration_mode === "vector" ? "vector" : "image";
    $("#cfg-quality").value = CONFIG.quality === "hd" ? "hd" : "standard";
    $("#cfg-ocr").value = typeof CONFIG.ocr === "string" ? CONFIG.ocr : ((CONFIG.ocr || {}).mode || "auto");
  }

  function settingsPayload() {
    const groups = ["text", "image", "vision"];
    const next = JSON.parse(JSON.stringify(CONFIG));
    delete next.text_model; delete next.image_model; delete next.vision_model;
    groups.forEach((key, i) => {
      const obj = Object.assign({}, next[key] || {});
      const base = $("#mg-base-" + i), model = $("#mg-model-" + i), secret = $("#mg-key-" + i);
      if (base) obj.base_url = base.value.trim();
      if (model) obj.model = model.value.trim();
      if (secret) obj.api_key = secret.value;
      next[key] = obj;
    });
    if ($("#cfg-engine")) next.vectorize = Object.assign({}, next.vectorize || {}, { engine: $("#cfg-engine").value });
    if ($("#cfg-render")) next.render_mode = $("#cfg-render").value;
    if ($("#cfg-default-mode")) next.default_illustration_mode = $("#cfg-default-mode").value;
    if ($("#cfg-quality")) next.quality = $("#cfg-quality").value;
    if ($("#cfg-ocr")) next.ocr = Object.assign({}, typeof next.ocr === "object" ? next.ocr : {}, { mode: $("#cfg-ocr").value });
    if ($("#cfg-font")) next.font = $("#cfg-font").value.trim() || "Times New Roman";
    return next;
  }

  async function testGroup(key) {
    try {
      const res = await api("/api/test", { method: "POST", body: { target: key, config: settingsPayload() } });
      const el = $('[data-conn="' + key + '"]');
      if (!el) return;
      const conn = el.closest(".conn");
      if (res.configured === false) {
        el.textContent = "未配置";
        if (conn) { conn.classList.remove("ok"); conn.classList.add("bad"); }
        return;
      }
      el.textContent = res.ok ? "连接正常" : ("失败：" + (res.error || "检查配置"));
      if (conn) { conn.classList.toggle("ok", !!res.ok); conn.classList.toggle("bad", !res.ok); }
    } catch (e) { toast("连接测试失败：" + e.message, "alert"); }
  }

  async function testAll() {
    try {
      const res = await api("/api/test", { method: "POST", body: { target: "all", config: settingsPayload() } });
      for (const item of res.results || []) {
        const el = $('[data-conn="' + item.target + '"]');
        if (!el) continue;
        const conn = el.closest(".conn");
        const configured = item.configured !== false;
        el.textContent = !configured ? "未配置" : (item.ok ? "连接正常" : ("失败：" + (item.error || "检查配置")));
        if (conn) { conn.classList.toggle("ok", !!item.ok); conn.classList.toggle("bad", configured && !item.ok); }
      }
      $("#conn-all").textContent = res.ok ? "全部连接正常" : "有模型连接失败";
      toast(res.ok ? "连接测试通过" : "部分连接失败，请检查设置", res.ok ? "check" : "alert");
    } catch (e) { toast("连接测试失败：" + e.message, "alert"); }
  }

  async function saveSettings() {
    const next = settingsPayload();
    try {
      await api("/api/config", { method: "POST", body: next });
      const st = await api("/api/state");
      CONFIG = st.config || {};
      closeVeil("#dlg-settings");
      toast("设置已保存", "check");
    } catch (e) { toast("保存失败：" + e.message, "alert"); }
  }

  /* --------------------------------------------------------- 向导 */
  async function optimizeBrief() {
    const text = $("#brief-input").value.trim();
    if (!text) { $("#brief-input").focus(); toast("先写一句构想，再点优化", "alert"); return; }
    if (text.length > 1500) { toast("构想已经很长，不需要再优化", "check"); return; }
    const btn = $("#optimize-brief");
    const label = $("#optimize-label") || btn;
    btn.disabled = true;
    label.textContent = "生成中…";
    try {
      const res = await api("/api/optimize", { method: "POST", body: { text, canvas: [S.pxW, S.pxH] } });
      if (res.text && res.text !== text) {
        S.originalBrief = S.originalBrief || text;
        $("#brief-input").value = res.text.slice(0, 2000);
        syncBrief();
        if (res.canvas) applyWizardCanvas(res.canvas);
        toast("已生成完整绘图提示词，画布比例已同步", "check");
      } else {
        toast("模型认为当前描述已经足够", "check");
      }
    } catch (e) { toast("优化失败：" + e.message, "alert"); }
    btn.disabled = false;
    label.textContent = "快速扩写";
  }

  function wizSvg(body) {
    return '<svg viewBox="0 0 68 50" aria-hidden="true">' + body + '</svg>';
  }

  function wizThumb(qid, value, desc) {
    const v = String(value || "").toLowerCase();
    const S = ' fill="none" stroke="#33475B" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"';
    const A = ' fill="none" stroke="#C2410C" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"';
    if (qid === "archetype") {
      if (v.indexOf("ring") >= 0) return wizSvg(
        '<circle cx="34" cy="25" r="18"' + S + '/><circle cx="34" cy="25" r="12"' + S + '/><circle cx="34" cy="25" r="6"' + S + '/>'
        + '<path d="M34 7v5M34 38v5M16 25h5M47 25h5M21 12l3.5 3.5M43.5 34.5L47 38M21 38l3.5-3.5M43.5 15.5L47 12"' + S + '/>');
      if (v.indexOf("loop") >= 0) return wizSvg(
        '<circle cx="34" cy="25" r="17" stroke-dasharray="3 3"' + S + '/>'
        + '<circle cx="34" cy="9" r="4.5"' + S + '/><circle cx="50" cy="25" r="4.5"' + S + '/><circle cx="34" cy="41" r="4.5"' + S + '/><circle cx="18" cy="25" r="4.5"' + S + '/>'
        + '<path d="M43 13l3 3M46 31l3 3M25 38l-3 3M22 18l-3-3"' + A + '/>');
      if (v.indexOf("pipeline") >= 0 || v.indexOf("process") >= 0) return wizSvg(
        '<rect x="3" y="17" width="14" height="16" rx="2"' + S + '/><rect x="27" y="17" width="14" height="16" rx="2"' + S + '/><rect x="51" y="17" width="14" height="16" rx="2"' + S + '/>'
        + '<path d="M18 25h7M42 25h7"' + A + '/><path d="M23 22l2 3-2 3M47 22l2 3-2 3"' + A + '/>');
      if (v.indexOf("anatomy") >= 0 || v.indexOf("structure") >= 0) return wizSvg(
        '<rect x="10" y="8" width="48" height="9" rx="2"' + S + '/><rect x="10" y="20" width="48" height="9" rx="2"' + S + '/><rect x="10" y="32" width="48" height="9" rx="2"' + S + '/>');
      if (v.indexOf("abstract") >= 0 || v.indexOf("graphical") >= 0) return wizSvg(
        '<rect x="4" y="8" width="18" height="34" rx="2"' + S + '/><rect x="25" y="8" width="18" height="34" rx="2"' + S + '/><rect x="46" y="8" width="18" height="34" rx="2"' + S + '/>'
        + '<path d="M8 16h10M8 21h10M29 16h10M29 21h10M50 16h10M50 21h10"' + S + '/>');
      if (v.indexOf("signal") >= 0 || v.indexOf("pathway") >= 0) return wizSvg(
        '<circle cx="34" cy="9" r="4"' + S + '/><circle cx="34" cy="23" r="4"' + S + '/><circle cx="34" cy="37" r="4"' + S + '/>'
        + '<path d="M34 13v6M34 27v6"' + A + '/><path d="M31 17l3 3 3-3M31 31l3 3 3-3"' + A + '/>');
      return wizSvg('<rect x="8" y="10" width="22" height="13" rx="2"' + S + '/><rect x="38" y="10" width="22" height="13" rx="2"' + S + '/><rect x="8" y="27" width="22" height="13" rx="2"' + S + '/><rect x="38" y="27" width="22" height="13" rx="2"' + S + '/>');
    }
    if (qid === "palette") {
      const preset = {
        nature: ["#0F4D92", "#0284C7", "#D97706", "#E2E8F0"],
        cell: ["#A9713F", "#2E8B7A", "#9333EA", "#F3E8D9"],
        acsnano: ["#0D9488", "#2563EB", "#EA580C", "#E6F4F1"],
        minimal: ["#111827", "#6B7280", "#D1D5DB", "#F3F4F6"]
      };
      let colors = preset[v] || null;
      if (!colors) {
        const hexes = String(desc || "").match(/#[0-9a-fA-F]{6}/g) || [];
        colors = hexes.slice(0, 4);
      }
      if (!colors.length) colors = ["#33475B", "#7FA8A3", "#D9C7A7", "#F0EDE4"];
      while (colors.length < 4) colors.push("#E8E8E2");
      return wizSvg(colors.slice(0, 4).map((c, i) =>
        '<rect x="' + (7 + i * 14) + '" y="10" width="11" height="30" rx="2" fill="' + c + '"/>').join(""));
    }
    if (qid === "ratio") {
      const m = v.match(/([0-9.]+)\s*:\s*([0-9.]+)/);
      let ar = m ? parseFloat(m[1]) / parseFloat(m[2]) : 1.5;
      if (!isFinite(ar) || ar <= 0) ar = 1.5;
      let w = 52, h = w / ar;
      if (h > 36) { h = 36; w = h * ar; }
      return wizSvg('<rect x="' + ((68 - w) / 2).toFixed(1) + '" y="' + ((50 - h) / 2).toFixed(1)
        + '" width="' + w.toFixed(1) + '" height="' + h.toFixed(1) + '" rx="2"' + S + '/>');
    }
    if (qid === "density") {
      const n = v.indexOf("minimal") >= 0 ? 2 : v.indexOf("dense") >= 0 ? 4 : 3;
      const gap = 36 / Math.max(1, n - 1);
      let dots = "";
      for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
        dots += '<circle cx="' + (16 + i * gap).toFixed(1) + '" cy="' + (9 + j * gap * 0.9).toFixed(1) + '" r="2.4" fill="#33475B"/>';
      }
      return wizSvg(dots);
    }
    if (qid === "illustration") {
      if (v.indexOf("image") >= 0) return wizSvg(
        '<rect x="6" y="12" width="17" height="26" rx="4" fill="#F3C9B6" stroke="#C2410C" stroke-width="1.2"/>'
        + '<circle cx="34" cy="25" r="10" fill="#B9DCD6" stroke="#2E8B7A" stroke-width="1.2"/>'
        + '<path d="M50 36l8-22 6 22z" fill="#E8D8B0" stroke="#B7791F" stroke-width="1.2"/>');
      return wizSvg(
        '<rect x="6" y="12" width="17" height="26" rx="4"' + S + '/><circle cx="34" cy="25" r="10"' + S + '/><path d="M50 36l8-22 6 22z"' + S + '/>');
    }
    if (qid === "language") {
      const label = v.indexOf("bilingual") >= 0 ? "中 EN" : v.indexOf("zh") === 0 || v.indexOf("chinese") >= 0 ? "中文" : "EN";
      return wizSvg('<text x="34" y="30" text-anchor="middle" font-family="Segoe UI, sans-serif" font-size="14" font-weight="600" fill="#33475B">' + label + '</text>');
    }
    return wizSvg('<circle cx="34" cy="25" r="15"' + S + '/><path d="M34 10v30M19 25h30"' + S + '/>');
  }

  function wizardNav() {
    if (wizardResult) {
      $("#wizard-progress").textContent = "提示词已生成";
      $("#wizard-prev").hidden = true;
      $("#wizard-next").hidden = true;
      $("#wizard-apply").hidden = true;
      return;
    }
    const n = wizardQuestions.length;
    $("#wizard-progress").textContent = n ? (wizardStep + 1) + " / " + n : "";
    $("#wizard-prev").hidden = !n || wizardStep <= 0;
    $("#wizard-next").hidden = !n || wizardStep >= n - 1;
    $("#wizard-apply").hidden = !n || wizardStep < n - 1;
  }

  function renderWizardStep() {
    if (wizardResult) { renderWizardResult(); return; }
    const q = wizardQuestions[wizardStep];
    if (!q) return;
    const opts = (q.options || []).map((o) => {
      const on = wizardAnswers[q.id] === o.value;
      return '<button type="button" class="wiz-opt" data-qid="' + esc(q.id) + '" data-value="' + esc(o.value)
        + '" aria-pressed="' + (on ? "true" : "false") + '">'
        + '<span class="wiz-thumb">' + wizThumb(q.id, o.value, o.desc) + '</span>'
        + '<span class="wiz-txt"><b>' + esc(o.label) + '</b><span>' + esc(o.desc || "") + '</span></span></button>';
    }).join("");
    $("#wizard-body").innerHTML = '<div class="wizard-q"><h4>' + esc(q.title) + '</h4><div class="wiz-grid">' + opts + '</div></div>';
    wizardNav();
  }

  function renderWizardSeed() {
    wizardQuestions = []; wizardStep = 0; wizardResult = null;
    $("#wizard-progress").textContent = "";
    $("#wizard-intro").textContent = "先用一句话说说你要画什么；如果上传了参考图，AI 会先读它的排版，再按参考图问排版与内容（约 6–8 题）。";
    $("#wizard-body").innerHTML = '<div class="wiz-seed">'
      + '<textarea id="wizard-seed" class="ta" maxlength="2000">' + esc($("#brief-input").value) + '</textarea>'
      + '<div class="chips">' + SAMPLES.map((s, i) =>
        '<button type="button" class="chip" data-seed="' + i + '">' + esc(s.slice(0, 10)) + '</button>').join("") + '</div>'
      + '<button type="button" class="btn primary" id="wizard-start">让 AI 出题</button></div>';
    wizardNav();
  }

  async function loadWizardQuestions(text) {
    wizardResult = null;
    $("#wizard-intro").textContent = "正在根据你的描述出题…";
    $("#wizard-body").innerHTML = '<p style="font-size:12.5px;color:var(--tx-3)">AI 正在读你的描述，请稍候…</p>';
    $("#wizard-prev").hidden = true;
    $("#wizard-next").hidden = true;
    $("#wizard-apply").hidden = true;
    try {
      const res = await api("/api/assist/clarify", {
      method: "POST",
      body: { text, style_dna: S.styleDna, image: S.styleDna ? undefined : S.refImage }
    });
      const data = res.data || {};
      wizardQuestions = data.questions || [];
      wizardAnswers = {};
      wizardQuestions.forEach((q) => {
        const rec = (q.options || []).find((o) => o.recommended) || (q.options || [])[0];
        if (rec) wizardAnswers[q.id] = rec.value;
      });
      $("#wizard-intro").textContent = data.summary || "请确认下面几项：";
      wizardStep = 0;
      renderWizardStep();
    } catch (e) {
      $("#wizard-intro").textContent = "出题失败：" + e.message;
      $("#wizard-body").innerHTML = '<button type="button" class="btn" id="wizard-retry">重试</button>';
      toast("AI 引导失败：" + e.message, "alert");
    }
  }

  async function openWizard() {
    wizardQuestions = []; wizardStep = 0; wizardAnswers = {}; wizardResult = null;
    openVeil("#dlg-wizard");
    const text = $("#brief-input").value.trim();
    if (text.length >= 4) await loadWizardQuestions(text);
    else renderWizardSeed();
  }

  function applyWizardCanvas(canvas) {
    if (!canvas || canvas.length !== 2) return;
    const ar = Number(canvas[0]) / Number(canvas[1]);
    if (!isFinite(ar) || ar <= 0) return;
    S.w = 180;
    S.h = Math.round(180 / ar);
    const map = { "1.618": 1.618, "1.414": 1.414, "1.778": 1.778, "1.333": 1.333, "1": 1, "1.5": 1.5 };
    let hit = null;
    $$("[data-ratio]").forEach((b) => {
      if (!hit && Math.abs((map[b.dataset.ratio] || 0) - ar) < 0.02) hit = b;
      b.setAttribute("aria-pressed", "false");
    });
    if (hit) hit.setAttribute("aria-pressed", "true");
    applyFormat();
  }

  function renderWizardResult() {
    const result = wizardResult || {};
    const picks = wizardQuestions.map((q) => {
      const value = wizardAnswers[q.id];
      const option = (q.options || []).find((o) => o.value === value);
      return option ? option.label : "";
    }).filter(Boolean).join(" · ");
    const canvas = Array.isArray(result.canvas) ? result.canvas.join(" × ") + " px" : "按当前画板";
    $("#wizard-intro").textContent = "AI 已根据你的选择生成完整绘图提示词。可以先修改，再放入研究构想。";
    $("#wizard-body").innerHTML = '<div class="wiz-result">'
      + '<div class="wiz-result-meta"><b>' + esc(picks || "已按向导选择生成") + '</b>'
      + '<span>' + esc(canvas) + ' · ' + (result.illustration_mode === "image" ? "生图配图" : "纯矢量") + '</span></div>'
      + '<textarea id="wizard-prompt" class="ta" maxlength="6000" spellcheck="false">' + esc(result.text || "") + '</textarea>'
      + '<div class="wiz-result-actions">'
      + '<button type="button" class="chip" id="wizard-back">返回修改选项</button>'
      + '<button type="button" class="chip" id="wizard-copy">复制提示词</button>'
      + '<button type="button" class="chip" id="wizard-regen">重新生成</button>'
      + '<button type="button" class="btn primary" id="wizard-use">使用这条提示词</button>'
      + '</div></div>';
    wizardNav();
    $("#wizard-back").addEventListener("click", () => {
      wizardResult = null;
      wizardStep = Math.max(0, wizardQuestions.length - 1);
      renderWizardStep();
    });
    $("#wizard-copy").addEventListener("click", () => {
      const value = $("#wizard-prompt").value;
      const done = () => toast("提示词已复制", "check");
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(done).catch(() => toast("复制失败", "alert"));
      } else {
        $("#wizard-prompt").select();
        document.execCommand("copy");
        done();
      }
    });
    $("#wizard-regen").addEventListener("click", () => applyWizard());
    $("#wizard-use").addEventListener("click", () => useWizardPrompt());
  }

  function useWizardPrompt() {
    const prompt = ($("#wizard-prompt").value || "").trim();
    if (!prompt) { toast("提示词为空，先重新生成", "alert"); return; }
    S.originalBrief = S.originalBrief || $("#brief-input").value.trim();
    $("#brief-input").value = prompt.slice(0, 2000);
    syncBrief();
    // Keep the wizard's structured choices: the archetype forces the render
    // route instead of hoping the prompt text steers it.
    if (wizardAnswers.archetype) S.archetype = wizardAnswers.archetype;
    if (wizardAnswers.reference_layout) S.referenceLayoutMode = wizardAnswers.reference_layout;
    if (wizardResult && wizardResult.reference) S.styleDna = wizardResult.reference;
    const picked = wizardResult && wizardResult.illustration_mode;
    setMode((picked === "vector" || picked === "image") ? picked
      : (wizardAnswers.illustration === "vector" ? "vector" : "image"));
    if (wizardResult && wizardResult.canvas) applyWizardCanvas(wizardResult.canvas);
    applyFormat();
    closeVeil("#dlg-wizard");
    toast("提示词已放入研究构想，确认后点「开始绘制」", "check");
  }

  async function applyWizard() {
    const text = $("#brief-input").value.trim();
    if (!text) return;
    if (!wizardQuestions.length) {
      toast("AI 还在出题，等题目加载完再生成提示词", "alert");
      return;
    }
    const btn = $("#wizard-apply");
    btn.disabled = true;
    btn.textContent = "生成提示词…";
    $("#wizard-intro").textContent = "AI 正在把你的选择和描述合成绘图提示词…";
    try {
      const res = await api("/api/assist/compose-prompt", {
        method: "POST", body: { text, answers: wizardAnswers, style_dna: S.styleDna }
      });
      if (!res.enhanced_text) throw new Error("模型没有返回提示词");
      wizardResult = {
        text: res.enhanced_text,
        canvas: res.canvas,
        illustration_mode: res.illustration_mode,
        reference: res.reference || S.styleDna
      };
      renderWizardResult();
    } catch (e) { toast("生成提示词失败：" + e.message, "alert"); }
    btn.disabled = false;
    btn.textContent = "生成提示词";
  }

  /* --------------------------------------------------------- AI 修改 */
  function openEdit() {
    if (!S.currentId) { toast("请先打开一张已完成的图", "alert"); return; }
    if (S.job && (S.job.report || {}).raster) {
      toast("整图插画是合成图，暂不支持局部 SVG 修改；请修改提示词后重新生成。", "alert");
      return;
    }
    $("#edit-fig").textContent = S.currentId;
    $("#edit-instruction").value = "";
    $("#edit-count").textContent = "0 / 1000";
    $("#quick-chips").innerHTML = QUICK.map((c, i) => '<button type="button" class="chip" data-quick="' + i + '">' + esc(c) + "</button>").join("");
    openVeil("#dlg-edit");
    $("#edit-instruction").focus();
  }

  async function applyEdit() {
    const instruction = $("#edit-instruction").value.trim();
    if (!instruction) { toast("请先写修改指令", "alert"); return; }
    const btn = $("#apply-edit");
    btn.disabled = true;
    btn.textContent = "提交中…";
    try {
      const res = await api("/api/jobs/" + S.currentId + "/revise", { method: "POST", body: { instruction } });
      closeVeil("#dlg-edit");
      S.currentId = res.job_id;
      S.activeId = res.job_id;
      S.generating = true;
      $("#btn-draw").disabled = true;
      $("#progress").hidden = false;
      pollJob(res.job_id);
      await refreshJobs();
      toast("已提交修改 · 思考强度 high", "check");
    } catch (e) { toast("修改失败：" + e.message, "alert"); }
    btn.disabled = false;
    btn.textContent = "应用";
  }

  async function autoFixJob() {
    if (S.job && (S.job.report || {}).raster) {
      toast("整图插画会按提示词整体重新生成，不做逐条矢量回修。", "alert");
      return;
    }
    if (!S.currentId) return;
    if ($("#act-autofix").getAttribute("aria-disabled") === "true") return;
    const btn = $("#act-autofix");
    btn.classList.add("busy");
    btn.textContent = "修复中…";
    try {
      const res = await api("/api/jobs/" + S.currentId + "/auto-fix", { method: "POST", body: {} });
      S.currentId = res.job_id;
      S.activeId = res.job_id;
      S.generating = true;
      $("#btn-draw").disabled = true;
      $("#progress").hidden = false;
      $("#pr-fill").style.width = "0%";
      $("#pr-pct").textContent = "0%";
      $("#pr-stage").textContent = "已提交 " + (res.fix_targets || 0) + " 处问题，准备第 1 轮修复";
      pollJob(res.job_id);
      await refreshJobs();
      toast("已提交 AI 自动修复 · 逐轮修复并重审，最多 3 轮", "check");
    } catch (e) {
      toast("自动修复失败：" + e.message, "alert");
    }
    btn.classList.remove("busy");
    btn.textContent = "AI 自动修复";
  }

  async function recheckJob() {
    if (!S.currentId) return;
    const btn = $("#act-recheck");
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "审查中…";
    const started = Date.now();
    try {
      const res = await api("/api/jobs/" + S.currentId + "/recheck", { method: "POST", body: {} });
      await loadJob(S.currentId);
      const highs = (res.findings || []).filter((f) => f.severity === "high").length;
      const secs = ((Date.now() - started) / 1000).toFixed(1);
      toast("重新审查完成 · " + highs + " 处硬伤 · " + secs + " 秒", highs ? "alert" : "check");
    } catch (e) { toast("重新审查失败：" + e.message, "alert"); }
    btn.disabled = false;
    btn.textContent = label;
  }

  /* --------------------------------------------------------- 弹层 */
  function openVeil(sel) {
    lastFocus = document.activeElement;
    $(sel).hidden = false;
    document.addEventListener("keydown", veilKeys, true);
  }
  function closeVeil(sel) {
    $(sel).hidden = true;
    if (lastFocus && lastFocus.focus) { try { lastFocus.focus(); } catch (e) {} }
    if ($("#dlg-edit").hidden && $("#dlg-settings").hidden && $("#dlg-wizard").hidden) {
      document.removeEventListener("keydown", veilKeys, true);
    }
  }
  function veilKeys(e) {
    if (e.key !== "Escape") return;
    ["#dlg-edit", "#dlg-settings", "#dlg-wizard"].forEach((s) => { if (!$(s).hidden) closeVeil(s); });
  }

  /* --------------------------------------------------------- 页签 */
  function isNarrow() {
    return window.matchMedia("(max-width:1040px)").matches;
  }

  function showInspector() {
    if (isNarrow()) {
      $("#right-panel").classList.add("open");
      $("#backdrop").hidden = false;
      $("#toggle-inspector").setAttribute("aria-pressed", "true");
    } else if (!S.inspectorOpen) {
      S.inspectorOpen = true;
      $("#right-panel").hidden = false;
      $("#toggle-inspector").setAttribute("aria-pressed", "true");
      setTimeout(fitPaper, 30);
    }
  }

  /* --------------------------------------------------------- 其它 */
  function setMode(mode, persist) {
    S.mode = mode === "image" ? "image" : "vector";
    $$("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.mode === S.mode)));
    if (persist !== false) localStorage.setItem("cfs.mode", S.mode);
    const note = $("#mode-note");
    if (note) note.textContent = S.mode === "image"
      ? "细胞/对象逐项生图，再自动排版；文字和标注仍可编辑。"
      : "所有图元都是矢量路径，文字可在 SVG / PPT 中直接改。";
    $("#brief-mode").textContent = S.mode === "image" ? "素材生图 + 排版" : "纯矢量";
    renderTask();
  }

  function syncBrief() {
    $("#brief-len").textContent = $("#brief-input").value.length + " / 2000";
  }

  async function handleReference(file) {
    if (!file.type.startsWith("image/")) { toast("参考图必须是图片文件", "alert"); return; }
    if (file.size > 10 * 1024 * 1024) { toast("参考图不能超过 10MB", "alert"); return; }
    const reader = new FileReader();
    reader.onload = async (ev) => {
      S.refImage = ev.target.result;
      $("#ref-thumb").src = S.refImage;
      $("#ref-name").textContent = file.name;
      $("#ref-desc").textContent = "正在提取期刊风格…";
      $("#ref-chip").hidden = false;
      try {
        const res = await api("/api/analyze-reference-deep", { method: "POST", body: { image: S.refImage } });
        S.styleDna = res.style_dna || null;
        const lay = (S.styleDna && S.styleDna.layout_analysis) || {};
        const refText = (S.styleDna && S.styleDna.reference_summary) || "";
        $("#ref-desc").textContent = S.styleDna
          ? ("已分析排版：" + (refText || [lay.composition, lay.reading_order, lay.label_position].filter(Boolean).join(" / ") || "已提取风格 DNA")).slice(0, 110)
          : "未提取到风格规则";
        toast(S.styleDna ? "参考图风格已提取" : "参考图已载入，但未提取到风格 DNA", S.styleDna ? "check" : "alert");
      } catch (e) {
        S.styleDna = null;
        $("#ref-desc").textContent = "风格提取失败";
        toast("参考图分析失败：" + e.message, "alert");
      }
    };
    reader.readAsDataURL(file);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise((resolve, reject) => {
      try {
        const ta = document.createElement("textarea");
        ta.value = text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
        resolve();
      } catch (e) { reject(e); }
    });
  }

  /* --------------------------------------------------------- 绑定 */
  function bind() {
    $("#brief-input").addEventListener("input", (event) => {
      S.originalBrief = event.target.value;
      syncBrief();
    });
    $("#clear-brief").addEventListener("click", () => {
      $("#brief-input").value = ""; S.originalBrief = ""; syncBrief(); $("#brief-input").focus();
    });
    $$("[data-example]").forEach((b) => b.addEventListener("click", () => {
      $$("[data-example]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      $("#brief-input").value = SAMPLES[+b.dataset.example] || SAMPLES[0];
      S.originalBrief = $("#brief-input").value;
      syncBrief();
      toast("已载入示例构想", "check");
    }));
    $$("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
    $$("[data-ratio]").forEach((b) => b.addEventListener("click", () => {
      const map = { "1.618": [178, 110], "1.414": [180, 127], "1.778": [180, 101], "1.333": [180, 135], "1": [180, 180], "1.5": [180, 120] };
      const r = map[b.dataset.ratio] || [180, 127];
      S.ratio = b.dataset.ratio; S.w = r[0]; S.h = r[1];
      $$("[data-ratio]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      applyFormat();
    }));
    $$("[data-shape]").forEach((b) => b.addEventListener("click", () => {
      S.shape = b.dataset.shape;
      $$("[data-shape]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      applyFormat();
    }));
    $("#out-w").addEventListener("change", () => {
      const v = parseFloat($("#out-w").value);
      if (v > 20 && v < 500) { S.w = v; clearRatioPressed(); }
      applyFormat();
    });
    $("#out-h").addEventListener("change", () => {
      const v = parseFloat($("#out-h").value);
      if (v > 20 && v < 500) { S.h = v; clearRatioPressed(); }
      applyFormat();
    });
    $("#out-dpi").addEventListener("change", () => { S.dpi = +$("#out-dpi").value; applyFormat(); });

    $("#job-search").addEventListener("input", () => { S.query = $("#job-search").value; renderJobs(); });
    $$("[data-filter]").forEach((b) => b.addEventListener("click", () => {
      S.filter = b.dataset.filter; renderJobs();
    }));
    $("#job-list").addEventListener("click", (e) => {
      const act = e.target.closest("[data-act]");
      if (act) {
        const row = act.closest("[data-job]");
        const id = row && row.dataset.job;
        if (!id) return;
        e.stopPropagation();
        if (act.dataset.act === "retry") retryJob(id);
        else if (act.dataset.act === "folder") api("/api/open-folder", { method: "POST", body: { kind: "job", job_id: id } }).catch((x) => toast("打开失败：" + x.message, "alert"));
        else if (act.dataset.act === "delete") {
          if (!confirm("删除任务 " + id + "？任务文件夹与导出文件会一起删除。")) return;
          api("/api/jobs/" + id + "/delete", { method: "POST", body: {} }).then(() => {
            if (S.currentId === id) resetStage();
            refreshJobs(); toast("任务已删除", "check");
          }).catch((x) => toast("删除失败：" + x.message, "alert"));
        }
        return;
      }
      const row = e.target.closest("[data-job]");
      if (row) loadJob(row.dataset.job).catch((x) => toast("加载失败：" + x.message, "alert"));
    });
    $("#job-list").addEventListener("keydown", (e) => {
      const row = e.target.closest("[data-job]");
      if (row && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); row.click(); }
    });
    $("#jobs-expand").addEventListener("click", () => {
      if ($("#jobs-expand").getAttribute("aria-disabled") === "true") return;
      S.expanded = !S.expanded; renderJobs();
    });
    $("#jobs-clear").addEventListener("click", () => {
      if (!S.jobs.length) return;
      if (!confirm("清空所有已完成、失败与已取消任务？任务文件夹会一起删除。")) return;
      api("/api/jobs/clear", { method: "POST", body: {} }).then(() => {
        resetStage(); refreshJobs(); toast("最近任务已清空", "check");
      }).catch((e) => toast("清空失败：" + e.message, "alert"));
    });

    $("#btn-draw").addEventListener("click", startGenerate);
    $("#pr-cancel").addEventListener("click", () => {
      const id = S.activeId || S.currentId;
      if (!id) return;
      api("/api/jobs/" + id + "/cancel", { method: "POST", body: {} })
        .then(() => toast("正在取消，当前步骤结束后停止"))
        .catch((e) => toast("取消失败：" + e.message, "alert"));
    });

    $("#zoom-in").addEventListener("click", () => setZoom(S.zoom + 0.05));
    $("#zoom-out").addEventListener("click", () => setZoom(S.zoom - 0.05));
    $("#zoom-val").addEventListener("click", () => setZoom(1));
    $("#toggle-inspector").addEventListener("click", () => {
      if (isNarrow()) {
        const open = $("#right-panel").classList.toggle("open");
        $("#backdrop").hidden = !open;
        $("#toggle-inspector").setAttribute("aria-pressed", String(open));
      } else {
        S.inspectorOpen = !S.inspectorOpen;
        $("#right-panel").hidden = !S.inspectorOpen;
        $("#toggle-inspector").setAttribute("aria-pressed", String(S.inspectorOpen));
        setTimeout(fitPaper, 30);
      }
    });
    $("#backdrop").addEventListener("click", () => {
      $("#backdrop").hidden = true;
      $("#right-panel").classList.remove("open");
      $("#toggle-inspector").setAttribute("aria-pressed", "false");
    });
    $("#toggle-annot").addEventListener("click", () => {
      S.annot = !S.annot;
      $("#toggle-annot").setAttribute("aria-pressed", String(S.annot));
      applyAnnot();
    });
    $("#toggle-diff").addEventListener("click", () => {
      if (!S.job) { toast("先打开一张已完成的图", "alert"); return; }
      if ($("#toggle-diff").getAttribute("aria-disabled") === "true") {
        toast("还没有差异图；先导出 PPTX 会生成 SVG 与 PPT 对比", "alert"); return;
      }
      const url = S.job.diff_url || S.job.comparison_url;
      $("#viewer-title").textContent = S.job.diff_url ? "差异图" : "SVG 与 PPT 对比";
      $("#viewer-meta").textContent = S.job.id;
      $("#viewer-badge").textContent = S.job.diff_url ? "像素差异" : "对比预览";
      $("#viewer-cap-left").innerHTML = '<span class="mono">A</span> SVG 原图';
      $("#viewer-cap-right").innerHTML = '<span class="mono">B</span> ' + (S.job.diff_url ? "差异图" : "PPT 渲染");
      $("#viewer-left").innerHTML = '<img src="' + esc(S.job.svg_url || "") + '" alt="当前 SVG">';
      $("#viewer-right").innerHTML = '<img src="' + esc(url) + '" alt="对比图">';
      $("#viewer").hidden = false;
    });
    $("#viewer-close").addEventListener("click", () => { $("#viewer").hidden = true; });
    $("#viewer").addEventListener("click", (e) => { if (e.target === $("#viewer")) $("#viewer").hidden = true; });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !$("#viewer").hidden) $("#viewer").hidden = true;
    });

    $("#defect-list").addEventListener("click", (e) => {
      const d = e.target.closest("[data-defect]");
      if (d) locate(d.dataset.defect);
    });
    $("#act-retry").addEventListener("click", () => { if (S.currentId) retryJob(S.currentId); });
    $("#act-recheck").addEventListener("click", recheckJob);
    $("#act-autofix").addEventListener("click", autoFixJob);
    $("#act-edit").addEventListener("click", openEdit);
    $("#act-redraw").addEventListener("click", () => { if (S.currentId) retryJob(S.currentId); });
    $("#act-accept").addEventListener("click", async () => {
      if (!S.currentId) return;
      if (S.review.legacy) { toast("旧版结果不能直接验收，请先重新审查", "alert"); return; }
      if (S.review.findings.some((f) => f.severity === "high")) {
        toast("还有硬伤或警告，先自动修复再验收", "alert"); showInspector(); return;
      }
      try {
        await api("/api/jobs/" + S.currentId + "/confirm", { method: "POST", body: {} });
        S.job.visual_state = "confirmed";
        renderTask(); toast("已确认验收", "check");
      } catch (e) { toast("验收失败：" + e.message, "alert"); }
    });
    $("#legacy-redraw").addEventListener("click", () => { if (S.currentId) retryJob(S.currentId); });
    $("#legacy-close").addEventListener("click", () => { $("#legacy-notice").hidden = true; });

    $("#exp-svg").addEventListener("click", () => {
      if (S.job && (S.job.report || {}).raster) {
        toast("整图插画是位图，选择 PNG / PDF 即可，不能导出可编辑 SVG。", "alert");
        return;
      }
      saveAs("svg");
    });
    $("#exp-pptx").addEventListener("click", exportPptx);
    $("#exp-png").addEventListener("click", () => saveAs("png", { dpi: S.dpi }));
    if ($("#exp-pdf")) $("#exp-pdf").addEventListener("click", () => saveAs("pdf"));

    $("#open-file").addEventListener("click", () => { if (S.lastSaved) api("/api/reveal", { method: "POST", body: { path: S.lastSaved, action: "open" } }).catch((e) => toast("打开失败：" + e.message, "alert")); });
    $("#reveal-file").addEventListener("click", () => { if (S.lastSaved) api("/api/reveal", { method: "POST", body: { path: S.lastSaved, action: "select" } }).catch((e) => toast("定位失败：" + e.message, "alert")); });
    $("#copy-path").addEventListener("click", () => {
      if (!S.lastSaved) return;
      copyText(S.lastSaved).then(() => toast("路径已复制", "check")).catch(() => toast("复制失败", "alert"));
    });

    $("#optimize-brief").addEventListener("click", optimizeBrief);
    $("#open-ai-wizard").addEventListener("click", openWizard);
    $("#start-wizard").addEventListener("click", openWizard);
    $("#wizard-body").addEventListener("click", (e) => {
      const b = e.target.closest(".wiz-opt");
      if (b) {
        const q = b.dataset.qid;
        $$('[data-qid="' + q + '"]').forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        wizardAnswers[q] = b.dataset.value;
        return;
      }
      const seed = e.target.closest("[data-seed]");
      if (seed) {
        const box = $("#wizard-seed");
        if (box) box.value = SAMPLES[+seed.dataset.seed] || SAMPLES[0];
        return;
      }
      if (e.target.closest("#wizard-start")) {
        const box = $("#wizard-seed");
        const text = (box ? box.value : $("#brief-input").value).trim();
        if (!text) { toast("先写一句你想画什么", "alert"); if (box) box.focus(); return; }
        $("#brief-input").value = text;
        syncBrief();
        loadWizardQuestions(text);
        return;
      }
      if (e.target.closest("#wizard-retry")) {
        const text = $("#brief-input").value.trim();
        if (text) loadWizardQuestions(text); else renderWizardSeed();
      }
    });
    $("#wizard-prev").addEventListener("click", () => {
      if (wizardStep > 0) { wizardStep -= 1; renderWizardStep(); }
    });
    $("#wizard-next").addEventListener("click", () => {
      if (wizardStep < wizardQuestions.length - 1) { wizardStep += 1; renderWizardStep(); }
    });
    $("#wizard-apply").addEventListener("click", applyWizard);
    $$("#dlg-wizard [data-close]").forEach((b) => b.addEventListener("click", () => closeVeil("#dlg-wizard")));
    $("#dlg-wizard").addEventListener("click", (e) => { if (e.target === $("#dlg-wizard")) closeVeil("#dlg-wizard"); });

    $("#add-reference").addEventListener("click", () => $("#ref-file").click());
    $("#ref-file").addEventListener("change", () => { if ($("#ref-file").files[0]) handleReference($("#ref-file").files[0]); });
    $("#ref-remove").addEventListener("click", () => {
      S.refImage = null; S.styleDna = null;
      $("#ref-chip").hidden = true; $("#ref-file").value = "";
      toast("已移除参考图，回到内置风格档案");
    });
    $("#search-lit").addEventListener("click", () => {
      S.literature = !S.literature;
      $("#search-lit").setAttribute("aria-pressed", String(S.literature));
      localStorage.setItem("cfs.literature", String(S.literature));
      toast(S.literature ? "生成前会检索顶刊配图" : "已关闭文献检索", "check");
    });

    $("#quick-chips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-quick]");
      if (!b) return;
      const ta = $("#edit-instruction");
      ta.value = ta.value.trim() ? ta.value.trim() + "；" + QUICK[+b.dataset.quick] : QUICK[+b.dataset.quick];
      $("#edit-count").textContent = ta.value.length + " / 1000";
      ta.focus();
    });
    $("#edit-instruction").addEventListener("input", () => {
      $("#edit-count").textContent = $("#edit-instruction").value.length + " / 1000";
    });
    $("#apply-edit").addEventListener("click", applyEdit);
    $$("#dlg-edit [data-close]").forEach((b) => b.addEventListener("click", () => closeVeil("#dlg-edit")));
    $("#dlg-edit").addEventListener("click", (e) => { if (e.target === $("#dlg-edit")) closeVeil("#dlg-edit"); });

    $("#open-settings").addEventListener("click", () => { renderSettings(); openVeil("#dlg-settings"); });
    $$("#dlg-settings [data-close]").forEach((b) => b.addEventListener("click", () => closeVeil("#dlg-settings")));
    $("#dlg-settings").addEventListener("click", (e) => { if (e.target === $("#dlg-settings")) closeVeil("#dlg-settings"); });
    $("#settings-body").addEventListener("click", (e) => {
      if (e.target.closest("#test-all")) { testAll(); return; }
      const t = e.target.closest("[data-toggle-key],[data-test-group]");
      if (!t) return;
      if (t.hasAttribute("data-toggle-key")) {
        const inp = $("#mg-key-" + t.dataset.toggleKey);
        const show = inp.type === "password";
        inp.type = show ? "text" : "password";
        t.setAttribute("aria-pressed", String(show));
      } else testGroup(t.dataset.testGroup);
    });
    $("#save-settings").addEventListener("click", saveSettings);
    $("#open-config").addEventListener("click", () => api("/api/open-folder", { method: "POST", body: { kind: "config" } }).catch((e) => toast("打开失败：" + e.message, "alert")));
    $("#quit-app").addEventListener("click", async () => {
      try { await api("/api/quit", { method: "POST", body: {} }); } catch (e) {}
      window.close();
    });

    $("#load-sample").addEventListener("click", () => {
      $("#brief-input").value = SAMPLES[0]; syncBrief();
      $("#brief-input").focus();
      toast("示例构想已载入", "check");
    });
    window.addEventListener("resize", () => {
      if (!isNarrow()) {
        $("#backdrop").hidden = true;
        $("#right-panel").classList.remove("open");
      }
      fitPaper();
    });
  }

  async function boot() {
    try {
      const state = await api("/api/state");
      CONFIG = state.config || {};
      const jobs = await api("/api/jobs");
      // Legacy one-shot raster jobs are not editable; new image-mode jobs
      // are composed from per-object assets and keep editable labels.
      S.jobs = (jobs.jobs || []).filter(
        (j) => !((j.report || {}).raster || (j.report || {}).whole_figure));
      const savedMode = localStorage.getItem("cfs.mode");
      setMode(savedMode === "vector" ? "vector" : "image", false);
      const savedLit = localStorage.getItem("cfs.literature");
      if (savedLit === "false") S.literature = false;
      $("#search-lit").setAttribute("aria-pressed", String(S.literature));
      if (isNarrow()) {
        $("#toggle-inspector").setAttribute("aria-pressed", "false");
        S.inspectorOpen = false;
      }
      bind();
      syncBrief();
      $("#out-dpi").value = String(S.dpi);
      applyFormat();
      setZoom(1);
      renderJobs();
      const latest = S.jobs[0];
      if (latest) await loadJob(latest.id); else resetStage();
      renderTask();
    } catch (e) {
      console.error("boot failed", e && e.stack || e);
      toast("无法连接本地服务：" + e.message, "alert");
    }
  }

  document.addEventListener("DOMContentLoaded", boot);
})();
