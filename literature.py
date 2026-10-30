"""Top-journal figure retrieval and style learning.

Before drawing, the studio can pull real open-access papers for the user's
topic, extract their figures from the PDFs, and have the vision model describe
what those figures do (palette, typography, label placement, connectors,
density).  The aggregated rules are injected into the drawing prompts, so the
generator is conditioned on actual published practice instead of my taste.

Sources are deliberately dependency-free and OA-only:
  * Crossref  -> DOI metadata (any field)
  * Unpaywall -> legal open-access PDF link for that DOI
  * arXiv     -> preprints with direct PDFs (engineering / physics / CS)
Everything is cached under research/<hash>/ so repeat runs are instant.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

import pipeline

_BASE = (Path(sys.executable).resolve().parent
         if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
RESEARCH_DIR = _BASE / "research"
COLLECT_VERSION = 5
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

KEYWORD_INSTRUCTION = """You turn a Chinese/English research brief into literature search queries.
Return ONLY a JSON object:
{"queries": ["4-6 short English keyword queries, no quotes"], "figure_kind": "one of concentric_ring, closed_loop, pipeline, pathway, anatomy, graphical_abstract, chart, other"}
Rules: standard English technical terms; each query 3-7 words; at least two queries must name a figure genre (system architecture diagram, framework schematic, process flowchart, mechanism pathway, graphical abstract); no author names, no booleans.
"""

ANALYZE_INSTRUCTION = """你是顶刊科研插图的分析师。仔细看这张已发表论文的插图，只输出一个 JSON 对象，不要解释：
{
  "figure_type": "concentric_ring|closed_loop|pipeline|pathway|anatomy|graphical_abstract|chart|other",
  "layout": "一句话描述版式拓扑（如 central hub + 3 concentric bands）",
  "palette": ["最多 5 个十六进制主色，按面积从大到小"],
  "typography": {"family": "serif|sans|mixed", "weight": "regular|bold|mixed", "case": "title|sentence|upper", "size_levels": 3},
  "labels": {"orientation": "horizontal|radial|curved|mixed", "placement": "inside|outside|leader_lines|mixed"},
  "connectors": {"style": "orthogonal|curved|straight|none", "arrowheads": "filled|open|none", "dashed_usage": "feedback|grouping|none"},
  "containers": "cards|bands|outline_only|none|mixed",
  "background": "white|pale_tint|dark",
  "density": "low|medium|high",
  "curved_text": true_or_false,
  "notable_rules": ["2-4 条可直接复用的排版规律"],
  "problems": ["1-2 条这张图的不足，避免模仿"]
}
只描述你真正看见的东西，不要推测论文内容。
"""


def _get(url: str, timeout: int = 40, binary: bool = False):
    last = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
            return data if binary else data.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code in (429, 503):
                time.sleep(4 + attempt * 4)
                continue
            break
        except Exception as exc:
            last = exc
            time.sleep(1.5 + attempt * 2)
    raise last if last else RuntimeError("request failed")


def _post_json(url: str, payload: dict, timeout: int = 60) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": UA}, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _cache_key(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode("utf-8")).hexdigest()[:12]


def make_queries(text: str, config: dict) -> tuple[list[str], str]:
    """Ask the text model for English search queries; fall back to the raw text."""
    try:
        raw = pipeline._chat(config, [
            {"role": "system", "content": KEYWORD_INSTRUCTION},
            {"role": "user", "content": text[:1200]},
        ], temperature=0.2, max_tokens=600)
        data = pipeline._json_object(raw)
        queries = [re.sub(r"[^\w\s\-]", " ", str(q)).strip()
                   for q in (data.get("queries") or [])][:6]
        queries = [q for q in queries if 2 <= len(q) <= 90]
        return queries or [text[:90]], str(data.get("figure_kind") or "other")
    except Exception:
        return [text[:90]], "other"


def search_crossref(query: str, rows: int = 12) -> list[dict]:
    url = ("https://api.crossref.org/works?query=" + urllib.parse.quote(query)
           + f"&rows={rows}&filter=type:journal-article,has-full-text:true,from-pub-date:2016-01-01"
           + "&select=DOI,title,container-title,issued&mailto=zhao@example.org")
    try:
        data = json.loads(_get(url, timeout=40))
    except Exception:
        return []
    out = []
    for item in (data.get("message") or {}).get("items") or []:
        title = (item.get("title") or [""])[0]
        if not title:
            continue
        out.append({
            "doi": item.get("DOI"),
            "title": title[:160],
            "journal": ((item.get("container-title") or [""])[0] or "")[:80],
        })
    return out


def search_arxiv(query: str, rows: int = 8) -> list[dict]:
    url = ("https://export.arxiv.org/api/query?search_query=all:"
           + urllib.parse.quote(query) + f"&max_results={rows}&sortBy=relevance")
    try:
        root = ET.fromstring(_get(url, timeout=40).encode("utf-8"))
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("a:entry", ns):
        title = " ".join((entry.findtext("a:title", "", ns) or "").split())
        pdfs = [link.get("href") for link in entry.findall("a:link", ns)
                if link.get("title") == "pdf"]
        if title and pdfs:
            out.append({"title": title[:160], "pdf": pdfs[0], "doi": None,
                        "journal": "arXiv"})
    return out


def unpaywall_pdf(doi: str, timeout: int = 30) -> str | None:
    if not doi:
        return None
    try:
        data = json.loads(_get(
            f"https://api.unpaywall.org/v2/{urllib.parse.quote(doi)}?email=zhao@example.org",
            timeout=timeout))
    except Exception:
        return None
    best = data.get("best_oa_location") or {}
    if best.get("url_for_pdf"):
        return best["url_for_pdf"]
    for item in data.get("oa_locations") or []:
        if item.get("url_for_pdf"):
            return item["url_for_pdf"]
    return None


def _caption_for(page_text: str, fallback: str) -> str:
    matches = re.findall(r"((?:Fig(?:ure)?\.?)\s*\d+[.:]?\s+.{0,220})", page_text, re.S)
    if not matches:
        return fallback[:220]
    text = re.sub(r"\s+", " ", matches[0]).strip()
    return text[:220]


_FIGURE_HINTS = re.compile(
    r"architect|framework|schematic|diagram|overview|workflow|pipeline|"
    r"graphical abstract|system|structure|classification|taxonomy|concept", re.I)

_DECOR_HINTS = re.compile(
    r"experimental setup|benchtop|photo of|photograph of|apparatus|"
    r"board (left|right)|prototype|schematic map|metro|street map|"
    r"case study (in|of)|field photo|image of", re.I)


def _phash(raw: bytes) -> list[int] | None:
    try:
        import io as _io
        from PIL import Image
        image = Image.open(_io.BytesIO(raw)).convert("L").resize((24, 24))
        return list(image.getdata())
    except Exception:
        return None


def _near_duplicate(a: list[int] | None, b: list[int] | None) -> bool:
    if not a or not b or len(a) != len(b):
        return False
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a) < 4.0


def _caption_near(page, rect, fallback: str) -> str:
    if rect is not None:
        best, best_dy = None, 1e9
        try:
            for block in page.get_text("blocks"):
                text = re.sub(r"\s+", " ", block[4] or "").strip()
                if not re.match(r"(?:Fig(?:ure)?\.?)\s*\d+", text):
                    continue
                dy = abs(block[1] - rect.y1)
                if dy < best_dy:
                    best, best_dy = text, dy
        except Exception:
            best = None
        if best:
            return best[:220]
    return _caption_for(page.get_text(), fallback)


def extract_pdf_figures(pdf_bytes: bytes, out_dir: Path, fallback_title: str,
                        max_figures: int = 8) -> list[dict]:
    """Pull large raster figures out of a paper PDF, with their captions."""
    try:
        import fitz
    except Exception:
        return []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = hashlib.md5(fallback_title.encode("utf-8")).hexdigest()[:8]
    found, seen_hashes = [], []
    pages = list(range(min(doc.page_count, 18)))
    # Prefer pages whose text suggests an architecture / framework figure.
    def page_score(pno):
        try:
            text = doc[pno].get_text()
        except Exception:
            return 0
        return len(_FIGURE_HINTS.findall(text)) + (2 if _FIGURE_HINTS.search(text) else 0)
    pages.sort(key=page_score, reverse=True)
    for pno in pages:
        if len(found) >= max_figures:
            break
        page = doc[pno]
        try:
            page_text = page.get_text()
        except Exception:
            page_text = ""
        candidates = []
        for image in page.get_images(full=True):
            xref = image[0]
            try:
                info = doc.extract_image(xref)
            except Exception:
                continue
            raw = info.get("image") or b""
            width, height = info.get("width", 0), info.get("height", 0)
            if len(raw) < 25_000 or width < 480 or height < 280:
                continue
            ratio = width / max(1, height)
            if not 0.45 <= ratio <= 2.9:
                continue
            try:
                rects = page.get_image_rects(xref)
                rect = rects[0] if rects else None
            except Exception:
                rect = None
            candidates.append((width * height, info, rect))
        candidates.sort(key=lambda row: -row[0])
        for area, info, rect in candidates[:2]:
            if len(found) >= max_figures:
                break
            raw = info.get("image") or b""
            width, height = info.get("width", 0), info.get("height", 0)
            signature = _phash(raw)
            if any(_near_duplicate(signature, old) for old in seen_hashes):
                continue
            seen_hashes.append(signature)
            caption = _caption_near(page, rect, page_text or fallback_title)
            ext = info.get("ext") or "png"
            path = out_dir / f"fig_{prefix}_{len(found):02d}.{ext}"
            path.write_bytes(raw)
            found.append({"path": str(path), "caption": caption,
                          "paper": fallback_title, "page": pno + 1,
                          "size": [width, height]})
    try:
        doc.close()
    except Exception:
        pass
    return found


def _target_kind(text: str, config: dict, model_kind: str) -> str:
    """Use the renderer's routing rules, not the prompt's decorative words."""
    requested = str((config or {}).get("archetype") or "").strip().lower()
    dna = (config or {}).get("style_dna") or {}
    requested = requested or str(dna.get("archetype") or "").strip().lower()
    mapping = {"ring_architecture": "concentric_ring", "closed_loop": "closed_loop",
               "signal_pathway": "pathway", "process_pipeline": "pipeline",
               "structural_anatomy": "anatomy", "graphical_abstract": "graphical_abstract"}
    if requested in mapping:
        return mapping[requested]
    if re.search(r"圆环|同心圆|环状|环形架构|环形图|radial|ring[-_ ]?architecture", text, re.I):
        return "concentric_ring"
    if re.search(r"闭环|回路|循环|反馈|closed[-_ ]?loop|feedback|cycle", text, re.I):
        return "closed_loop"
    if re.search(r"信号通路|通路|级联|pathway|signal|signaling", text, re.I):
        return "pathway"
    if re.search(r"流程|工序|制备|工艺|pipeline|workflow|process", text, re.I):
        return "pipeline"
    if re.search(r"剖面|分层|结构|anatomy|cross[-_ ]?section|layer", text, re.I):
        return "anatomy"
    return model_kind


def collect(text: str, config: dict, limit: int = 24,
            on_stage=None) -> dict:
    """Search OA papers for the topic and extract figures. Cached by brief."""
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    key = _cache_key(text)
    root = RESEARCH_DIR / key
    manifest = root / "corpus.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if data.get("figures") and data.get("collect_version") == COLLECT_VERSION:
                stage("research", f"复用已缓存的 {len(data['figures'])} 张配图")
                return data
        except Exception:
            pass

    root.mkdir(parents=True, exist_ok=True)
    for stale in (root / "analysis.json", root / "style_summary.json"):
        try:
            stale.unlink()
        except OSError:
            pass
    queries, model_kind = make_queries(text, config)
    kind = _target_kind(text, config, model_kind)
    for extra in _KIND_QUERIES.get(kind, []):
        if extra not in queries:
            queries.append(extra)
    stage("research", "检索开放获取论文：" + " / ".join(queries[:2]))

    papers: list[dict] = []
    for query in queries[:8]:
        papers.extend(search_arxiv(query, rows=5))
        papers.extend(search_crossref(query, rows=8))
        if len(papers) >= 60:
            break
        time.sleep(0.4)

    # de-duplicate by title and keep the first (arXiv entries carry a direct PDF)
    unique, seen_titles = [], set()
    for paper in papers:
        sig = re.sub(r"\W+", "", paper.get("title", "").lower())[:80]
        if not sig or sig in seen_titles:
            continue
        seen_titles.add(sig)
        unique.append(paper)

    figures: list[dict] = []
    fig_dir = root / "figures"
    for index, paper in enumerate(unique[:24]):
        if len(figures) >= limit:
            break
        stage("research", f"分析论文 {index + 1}/{min(len(unique), 24)}：{paper['title'][:40]}")
        pdf_url = paper.get("pdf") or unpaywall_pdf(paper.get("doi") or "")
        if not pdf_url:
            continue
        try:
            pdf = _get(pdf_url, timeout=50, binary=True)
        except Exception:
            continue
        if not pdf.startswith(b"%PDF") or len(pdf) > 35 * 1024 * 1024:
            continue
        extracted = extract_pdf_figures(
            pdf, fig_dir, paper["title"],
            max_figures=min(6, limit - len(figures)))
        paper_hint = bool(_FIGURE_HINTS.search(paper.get("title") or ""))
        kept = 0
        for item in extracted:
            caption = item.get("caption") or ""
            caption_hint = bool(_FIGURE_HINTS.search(caption))
            if _DECOR_HINTS.search(caption):
                continue
            if not caption_hint and not paper_hint:
                continue
            item["source"] = paper.get("journal") or ""
            item["doi"] = paper.get("doi")
            item["queries"] = queries[:2]
            item["hint"] = caption_hint
            item["kind_match"] = _kind_match(kind, caption, paper.get("title") or "")
            # Keep architecture-looking candidates for the vision pass; the
            # vision model is the reliable judge of figure type.
            figures.append(item)
            kept += 1
            if kept >= 4:
                break


    unique_figures, seen_figs = [], set()
    for item in figures:
        sig = (re.sub(r"\W+", "", (item.get("caption") or "").lower())[:80],
               tuple(item.get("size") or []))
        if sig in seen_figs:
            continue
        seen_figs.add(sig)
        unique_figures.append(item)
    figures = unique_figures[:limit]
    data = {
        "brief": text[:800],
        "queries": queries,
        "figure_kind": kind,
        "figure_count": len(figures),
        "figures": figures,
        "sources": sorted({f.get("source") or "" for f in figures if f.get("source")}),
        "created": time.time(),
        "collect_version": COLLECT_VERSION,
    }
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


_KIND_QUERIES = {
    "concentric_ring": ["concentric ring architecture diagram",
                        "radial system architecture schematic",
                        "system architecture review overview figure",
                        "conceptual framework diagram"],
    "closed_loop": ["closed-loop control architecture diagram",
                    "feedback loop system architecture schematic",
                    "soft robotics review system architecture",
                    "embodied intelligence architecture review",
                    "system integration overview framework"],
    "pipeline": ["process flow diagram pipeline schematic",
                 "fabrication workflow schematic",
                 "system architecture review overview"],
    "pathway": ["signaling pathway diagram mechanism schematic",
                "molecular pathway figure",
                "mechanism overview diagram review"],
    "anatomy": ["device cross-section schematic layer stack",
                "structural anatomy diagram",
                "system architecture review overview"],
    "graphical_abstract": ["graphical abstract system schematic",
                           "conceptual framework diagram",
                           "system architecture review overview"],
}

_KIND_HINTS = {
    "concentric_ring": ("radial", "ring", "concentric", "circular", "wheel", "onion",
                        "层级圆", "同心圆", "环"),
    "closed_loop": ("loop", "closed", "feedback", "cycle", "circuit", "recurrent",
                    "closed-loop", "closed loop", "闭环", "回路"),
    "pipeline": ("pipeline", "workflow", "process", "flow", "sequence", "stage",
                 "protocol", "stepwise", "流程"),
    "pathway": ("pathway", "signal", "cascade", "network", "circuit", "route",
                "通路", "级联"),
    "anatomy": ("anatomy", "structure", "cross-section", "cross section", "layer",
                "stack", "strat", "section", "剖面", "分层"),
}


_ARCH_HINTS = re.compile(
    r"architect|framework|overview|schematic|diagram|conceptual|taxonomy|"
    r"classification|system\s+(architecture|overview|design|framework)", re.I)


def _kind_match(kind: str, caption: str, title: str) -> bool:
    if not kind or kind == "other":
        return True
    seg = (caption + " " + title).lower()
    return any(w in seg for w in _KIND_HINTS.get(kind, ()))


def _analyze_one(item: dict, config: dict) -> dict | None:
    try:
        import base64
        import io as _io
        from PIL import Image
        raw = Path(item["path"]).read_bytes()
        # Downscale before sending: huge PDF scans make the vision call slow.
        image = Image.open(_io.BytesIO(raw)).convert("RGB")
        image.thumbnail((800, 800))
        buffer = _io.BytesIO()
        image.save(buffer, "JPEG", quality=85)
        data_url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
        vision = config.get("vision") or config.get("text") or {}
        if not (vision.get("base_url") and vision.get("model")):
            return None
        # Prefer the vision-capable model. The configured text model is often
        # text-only and returns no JSON for images.
        models = []
        if vision.get("model"):
            models.append(vision["model"])
        if "cn:glm-5v-turbo" not in models:
            models.append("cn:glm-5v-turbo")
        for model in models:
            parsed = _analyze_with_model(vision, model, data_url)
            if parsed:
                return parsed
        return None
    except Exception:
        return None


def _analyze_with_model(vision: dict, model: str, data_url: str) -> dict | None:
    try:
        for attempt in range(2):
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": [
                    {"type": "text", "text": ANALYZE_INSTRUCTION},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}],
                "temperature": 0,
                "max_tokens": 1300 if attempt == 0 else 900,
            }
            response = pipeline._post_json(
                pipeline._endpoint(vision["base_url"], "/chat/completions"),
                pipeline._api_key(vision), payload, timeout=120)
            message = response["choices"][0]["message"]
            content = message.get("content") or ""
            if not content.strip():
                reasoning = message.get("reasoning_content") or ""
                start, end = reasoning.rfind("{"), reasoning.rfind("}")
                content = reasoning[start:end + 1] if 0 <= start < end else ""
            try:
                parsed = pipeline._json_object(content)
            except Exception:
                continue
            if isinstance(parsed, dict) and parsed.get("figure_type"):
                return parsed
        return None
    except Exception:
        return None


def learn(corpus: dict, config: dict, max_figures: int = 24,
          on_stage=None) -> dict:
    """Vision-model pass over the corpus, then aggregate the recurring rules."""
    def stage(name, detail=None):
        if on_stage:
            on_stage(name, detail)

    root = Path(corpus["figures"][0]["path"]).parent.parent if corpus.get("figures") else RESEARCH_DIR
    analysis_path = root / "analysis.json"
    analyses = []
    if analysis_path.is_file():
        try:
            analyses = json.loads(analysis_path.read_text(encoding="utf-8")).get("items") or []
        except Exception:
            analyses = []

    todo = list(corpus.get("figures") or [])
    kind = str((corpus or {}).get("figure_kind") or "other").lower()
    todo_paths = {item.get("path") for item in todo}
    analyses = [item for item in analyses if item.get("path") in todo_paths]
    kind_by_path = {item.get("path"): bool(item.get("kind_match")) for item in todo}
    for item in analyses:
        item.setdefault("caption_match", kind_by_path.get(item.get("path"), False))
    analyzed_paths = {item.get("path") for item in analyses}
    pending = [item for item in todo if item.get("path") not in analyzed_paths]
    budget = max(0, max_figures - len(analyses))
    matched_so_far = sum(1 for a in analyses if a.get("figure_type") == kind)
    for index, item in enumerate(pending[:budget], len(analyses) + 1):
        stage("research", f"学习配图 {index}/{min(len(todo), max_figures)}")
        parsed = _analyze_one(item, config)
        if parsed:
            parsed["path"] = item["path"]
            parsed["caption"] = item.get("caption", "")[:160]
            parsed["caption_match"] = bool(item.get("kind_match"))
            parsed["source"] = item.get("source") or ""
            analyses.append(parsed)
            if parsed.get("figure_type") == kind:
                matched_so_far += 1
            analysis_path.write_text(json.dumps({"items": analyses}, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
            if kind != "other" and matched_so_far >= 6:
                break

    total_analyzed = len(analyses)
    all_items_for_types = list(analyses)
    keep_types = {"concentric_ring", "closed_loop", "pipeline", "pathway",
                  "anatomy", "graphical_abstract", "chart", "other"}
    filtered = [a for a in analyses if a.get("figure_type") in keep_types]
    direct = [a for a in filtered
              if a.get("figure_type") == kind
              or (a.get("caption_match") and _kind_match(kind, a.get("caption") or "", ""))]
    style = [a for a in filtered
             if a not in direct and _ARCH_HINTS.search(a.get("caption") or "")]
    for item in direct:
        item["relevance"] = "direct"
    for item in style:
        item["relevance"] = "style"
    preferred = direct + style
    matched = len(direct)
    style_matched = len(style)
    if kind != "other" and preferred:
        analyses = preferred
    elif kind == "other":
        # "other" has no specific figure_type to match; keep every analyzed
        # figure so the style profile still aggregates real data instead of
        # silently falling back to the built-in seed.
        for item in filtered:
            if not item.get("relevance"):
                item["relevance"] = "style"
        preferred = filtered
        style_matched = len(filtered)
        matched = 0
        analyses = filtered or analyses
    analyses_all = analyses
    if kind != "other" and not preferred:
        analyses = []

    def usable_color(value: str) -> bool:
        value = str(value).upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", value):
            return False
        r, g, b = int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16)
        high, low = max(r, g, b), min(r, g, b)
        sat = 0 if high == 0 else (high - low) / high
        return sat < 0.80 and 0.12 < high / 255 < 0.98

    palette_counts: dict[str, int] = {}
    orientations: dict[str, int] = {}
    density: dict[str, int] = {}
    families: dict[str, int] = {}
    types: dict[str, int] = {}
    curved = 0
    rules: list[str] = []
    for item in analyses:
        for color in item.get("palette") or []:
            color = str(color).upper()
            if usable_color(color):
                palette_counts[color] = palette_counts.get(color, 0) + 1
        labels = item.get("labels") or {}
        orientations[labels.get("orientation", "?")] = orientations.get(labels.get("orientation", "?"), 0) + 1
        density[item.get("density", "?")] = density.get(item.get("density", "?"), 0) + 1
        family = (item.get("typography") or {}).get("family", "?")
        families[family] = families.get(family, 0) + 1
        types[item.get("figure_type", "?")] = types.get(item.get("figure_type", "?"), 0) + 1
        if item.get("curved_text"):
            curved += 1
        for rule in (item.get("notable_rules") or [])[:2]:
            rule = str(rule).strip()
            if 8 <= len(rule) <= 120 and rule not in rules:
                rules.append(rule)

    top_colors = [c for c, _ in sorted(palette_counts.items(), key=lambda kv: -kv[1])[:6]]
    major_type = max(types.items(), key=lambda kv: kv[1])[0] if types else "other"
    orientation = max(orientations.items(), key=lambda kv: kv[1])[0] if orientations else "mixed"
    dens = max(density.items(), key=lambda kv: kv[1])[0] if density else "medium"
    fam = max(families.items(), key=lambda kv: kv[1])[0] if families else "sans"

    brief_lines = [
        f"从 {len(analyses)} 张已发表插图中总结（主要图型：{major_type}）：",
        f"- 配色：主色集中在 {', '.join(top_colors[:4]) or '低饱和蓝/青/琥珀'}；同图最多 2 个饱和度较高的颜色，其余用同色系淡化。",
        f"- 文字：以 {fam} 字体为主，字号层级 3 级；标签朝向以 {orientation} 为主"
        + ("（少部分使用弧形文字）" if curved < max(1, len(analyses) // 3) else "（弧形文字常见）") + "。",
        f"- 信息密度：{dens}；容器以细描边卡片/环带为主，避免粗重阴影和渐变。",
        f"- 连接：主通路实线加实心箭头，反馈/调控用虚线；箭头不穿过文字。",
        f"- 背景：纯白或极浅同色底；环/带之间留白清晰，不靠深色底提升对比。",
    ]
    for rule in rules[:6]:
        brief_lines.append(f"- {rule}")
    brief = chr(10).join(brief_lines)

    types_all: dict[str, int] = {}
    for item in all_items_for_types:
        key = str(item.get("figure_type") or "other")
        types_all[key] = types_all.get(key, 0) + 1
    summary = {
        "analyzed": len(analyses),
        "analyzed_all": total_analyzed,
        "matched": matched,
        "style_matched": style_matched,
        "figure_types": types_all or types,
        "orientations": orientations,
        "density": density,
        "fonts": families,
        "curved_text": curved,
        "palette": top_colors,
        "brief": brief,
        "rules": rules[:12],
        "items": analyses,
    }
    (root / "style_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary


def bundled_profile() -> dict:
    path = Path(__file__).resolve().parent / "assets" / "style_profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _merge_profile(summary: dict) -> dict:
    """Blend live analysis with the bundled baseline instead of silently
    discarding the live run when the sample is small."""
    seed = json.loads(json.dumps(bundled_profile()))
    analyzed = summary.get("analyzed") or 0
    matched = summary.get("matched")
    if matched is None:
        matched = analyzed
    style_matched = summary.get("style_matched") or 0
    fonts = summary.get("fonts") or {}
    orient = summary.get("orientations") or {}
    dens = summary.get("density") or {}
    live_palette = summary.get("palette") or []
    live_rules = summary.get("rules") or []
    if analyzed >= 1 and (matched + style_matched) > 0:
        if len(live_palette) >= 2:
            seed["palette"] = live_palette
        if live_rules:
            seed["rules"] = live_rules[:8]
        if summary.get("brief"):
            seed["brief"] = summary["brief"]
        if fonts:
            seed["font_family"] = max(fonts.items(), key=lambda kv: kv[1])[0]
        if orient:
            seed["label_orientation"] = max(orient.items(), key=lambda kv: kv[1])[0]
        if dens:
            seed["density"] = max(dens.items(), key=lambda kv: kv[1])[0]
        seed["curved_text_ratio"] = (summary.get("curved_text") or 0) / max(1, analyzed)
        seed["figure_types"] = summary.get("figure_types") or {}
        seed["analyzed"] = analyzed
        seed["live_analyzed"] = analyzed
        seed["live_types"] = summary.get("figure_types") or {}
        seed["profile_source"] = "live" if analyzed >= 3 else "seed+live"
        seed["matched"] = matched
        seed["style_matched"] = style_matched
    else:
        seed["analyzed"] = 0
        seed["live_analyzed"] = summary.get("analyzed_all") or analyzed
        seed["live_types"] = summary.get("figure_types") or {}
        seed["matched"] = 0
        seed["style_matched"] = 0
        seed["profile_source"] = "seed"
    return seed


def research_for_generation(text: str, config: dict, on_stage=None) -> dict:
    """Collect + learn, returning a compact payload for the planner prompts."""
    profile = bundled_profile()
    corpus = {}
    summary = {}
    try:
        corpus = collect(text, config, limit=24, on_stage=on_stage)
    except Exception:
        corpus = {}
    if corpus.get("figures"):
        try:
            summary = learn(corpus, config, max_figures=24, on_stage=on_stage)
            profile = _merge_profile(summary)
        except Exception:
            pass
    if not profile:
        return {"ok": False, "reason": "no figures available", "brief": "", "count": 0}
    figures = []
    kind = str(corpus.get("figure_kind") or "other").lower()
    analyzed = (summary.get("items") or []) if summary else []
    for item in analyzed:
        try:
            rel = Path(item["path"]).resolve().relative_to(RESEARCH_DIR.resolve())
        except Exception:
            continue
        figures.append({"path": rel.as_posix(),
                        "caption": (item.get("caption") or "")[:160],
                        "source": item.get("source") or "",
                        "type": ("architecture" if item.get("relevance") == "style"
                                 else (item.get("figure_type") or "unknown")),
                        "relevance": item.get("relevance") or "direct"})
        if len(figures) >= 8:
            break
    analyzed_all = (summary.get("analyzed_all") or len(analyzed)) if summary else 0
    matched = (summary.get("matched") or 0) if summary else 0
    style_matched = (summary.get("style_matched") or 0) if summary else 0
    return {
        "ok": True,
        "count": matched + style_matched,
        "analyzed_count": analyzed_all,
        "direct_count": matched,
        "style_count": style_matched,
        "figure_kind": kind,
        "figures": figures,
        "live_count": analyzed_all,
        "brief": profile.get("brief", ""),
        "profile": profile,
        "palette": profile.get("palette") or [],
        "figure_types": summary.get("figure_types") or {} if summary else {},
        "rules": profile.get("rules") or [],
        "sources": corpus.get("sources") or [],
        "corpus_dir": (str(Path(corpus["figures"][0]["path"]).parent.parent)
                       if corpus.get("figures") else ""),
    }
