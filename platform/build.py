"""静态站点生成器 —— content/packets/*.md → 单文件 dist/index.html。

产物是**单个自包含 index.html**(内联 CSS/JS,深色 AI-native 风格),便于用
deploy-static-site skill 上传。工单为页面内结构化表单,POST 同源 /api/intake,
由后端用项目所有者账号建 GitHub issue(ADR-0002 / CONTEXT: Intake Form/Fields)。

设计遵循:ADR-0008(feed 为首屏)/ 0014(packet 为内容文件)/ 0002(同源 intake)。
只用 pyyaml(已在 requirements)+ stdlib,无模板/markdown 第三方库。
"""
from __future__ import annotations

import html
import json
import shutil
import urllib.parse
from datetime import date
from pathlib import Path

import yaml

import graph as graph_mod

ROOT = Path(__file__).resolve().parent
PACKETS_DIR = ROOT / "content" / "packets"
SHOWCASE_DIR = ROOT / "content" / "showcase"
HERO_FILE = ROOT / "content" / "hero.md"
CSS_FILE = ROOT / "static" / "style.css"
DIST = ROOT / "dist"

# Intake Fields(CONTEXT.md):提交人 / 标题 / 描述 / 附件 / 关联工单 / 类型 / 优先级
# 关联工单只是「指着老工单说话」:写进正文由 GitHub 自动交叉引用,不做站内回复层级。
MAX_RELATED_ISSUES = 5
REVIEW_LABEL = "待审核"      # 与 intake_service.REVIEW_LABEL 同步
ISSUE_TYPES = ["功能", "缺陷", "问题", "建议"]
PRIORITIES = ["低", "中", "高"]

# 站点左上角的品牌标记(.brand .logo:圆角方块 + 紫青渐变 + 紫色辉光)原样搬成 favicon,
# 两处必须一致 —— 改渐变色时记得同步 style.css 的 --a1/--a2。
FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="10" y1="8" x2="54" y2="56" gradientUnits="userSpaceOnUse">
      <stop stop-color="#7c5cff"/>
      <stop offset="1" stop-color="#22d3ee"/>
    </linearGradient>
    <filter id="s" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#7c5cff" flood-opacity=".55"/>
    </filter>
  </defs>
  <rect x="8" y="8" width="48" height="48" rx="16" fill="url(#g)" filter="url(#s)"/>
</svg>"""
# `#` 必须编码成 %23:data URI 写在 href 属性里,第一个裸 # 会被当成 fragment 起点,
# URL 从那里截断 —— 色值 #7c5cff 和 url(#g) 都带 #,不编码的话 SVG 只剩半句,favicon 直接不显示。
FAVICON_HREF = "data:image/svg+xml," + urllib.parse.quote(FAVICON_SVG, safe="/:;=?&,%")


def parse_packet(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path.name} 缺少 frontmatter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm) or {}
    meta["body"] = body.strip()
    meta.setdefault("tags", [])
    meta.setdefault("id", path.stem)
    return meta


def load_packets() -> list[dict]:
    packets = [parse_packet(p) for p in PACKETS_DIR.glob("*.md")]
    packets.sort(key=lambda m: (str(m.get("date", "")), str(m.get("id", ""))), reverse=True)
    return packets


def load_showcase() -> list[dict]:
    """成果展示条目。**fail-closed:只渲染显式写了 public: true 的条目**(ADR-0020)。"""
    if not SHOWCASE_DIR.exists():
        return []
    items = [parse_packet(p) for p in SHOWCASE_DIR.glob("*.md")]
    items = [m for m in items if m.get("public") is True]
    items.sort(key=lambda m: (int(m.get("order", 999)), str(m.get("id", ""))))
    return items


def load_hero_film() -> dict:
    """首屏视频。同样 fail-closed:没有 hero.md 或没写 public: true 就整块不渲染(ADR-0020)。"""
    if not HERO_FILE.exists():
        return {}
    meta = parse_packet(HERO_FILE)
    if meta.get("public") is not True:
        return {}
    for key in ("poster_dark", "poster_light", "video"):
        if not (ROOT / str(meta.get(key, ""))).exists():
            raise FileNotFoundError(
                f"hero.md 的 {key} 指向 {meta.get(key)},文件不存在 —— 先跑 scripts/make_hero_media.py"
            )
    return meta


def copy_media(film: dict) -> list[str]:
    """视频不能内联进单文件 HTML(6MB base64 会涨到 8MB+),按 paper.pdf 的老规矩单独拷。"""
    if not film:
        return []
    names = []
    for key in ("poster_dark", "poster_light", "video"):
        rel = str(film[key])
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, dest)
        names.append(rel)
    return names


def copy_snapshots(items: list[dict]) -> list[tuple[str, str]]:
    """把条目声明的 snapshot 文件拷进 dist/,并给条目打上快照日期。

    站内放**快照**(所有者选定的版本),仓库放**最新版** —— 两者故意不同步:
    快照的滞后是特性,它让 casual 访客看策展过的稳定版,真感兴趣的自己进仓库。
    """
    copied: list[tuple[str, str]] = []
    for item in items:
        snap = item.get("snapshot")
        if not snap:
            continue
        src = ROOT.parent / str(snap.get("src", ""))
        if not src.exists():
            raise FileNotFoundError(f"{item['id']}: 快照源不存在 {src}")
        dest_name = str(snap.get("as") or src.name)
        DIST.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, DIST / dest_name)
        item["snapshot_date"] = date.fromtimestamp(src.stat().st_mtime).isoformat()
        copied.append((dest_name, item["snapshot_date"]))
    return copied


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def render_packet_card(p: dict) -> str:
    tags = "".join(f'<span class="tag">{_esc(t)}</span>' for t in p.get("tags", []))
    visual = p.get("visual", "").rstrip()
    visual_block = (
        f'<div class="visual"><span class="dots"><i></i><i></i><i></i></span>'
        f'<pre>{_esc(visual)}</pre></div>'
        if visual
        else ""
    )
    follow = p.get("follow_up", "")
    follow_block = (
        f'<p class="follow"><span class="follow-label">留一个问题</span>{_esc(follow)}</p>'
        if follow
        else ""
    )
    return f"""<article class="packet reveal" id="{_esc(p['id'])}">
  <header>
    <time>{_esc(p.get('date', ''))}</time>
    <div class="tags">{tags}</div>
  </header>
  <h3>{_esc(p.get('title', '(无标题)'))}</h3>
  <p class="insight">{_esc(p.get('insight', ''))}</p>
  {visual_block}
  {follow_block}
  <div class="actions">
    <button class="copy" data-id="{_esc(p['id'])}">复制转发文案</button>
    <a class="permalink" href="#{_esc(p['id'])}" aria-label="卡片链接">#</a>
  </div>
</article>"""


KIND_LABELS = {
    "paper": "论文",
    "system": "系统",
    "method-demo": "方法演示",
    "figure": "图表",
    "model": "模型",
}


def render_showcase_card(item: dict) -> str:
    """按 kind 决定长相、内容不写死(PLATFORM_V2_SPEC §3.2 的通用 artifact 渲染器)。

    展开区默认折叠,用原生 <details> —— 纯 UI 叙事节奏,不承担访问控制(ADR-0020)。
    """
    kind = str(item.get("kind", ""))
    status = item.get("status", "")
    status_block = f'<span class="status">{_esc(status)}</span>' if status else ""

    note = item.get("note", "")
    note_block = f'<p class="note">{_esc(note)}</p>' if note else ""

    sections = item.get("sections") or []
    sections_block = ""
    if sections:
        lis = "".join(f"<li>{_esc(s)}</li>" for s in sections)
        sections_block = (
            f'<details class="menu"><summary>目录:这篇讲了什么（{len(sections)} 节）</summary>'
            f"<ol>{lis}</ol></details>"
        )

    links = item.get("links") or []
    links_block = ""
    embed_block = ""
    if links:
        parts = []
        for link in links:
            label = _esc(link.get("label", "打开"))
            href = _esc(link.get("href", "#"))
            cls = "go primary" if link.get("primary") else "go"
            # stamp: snapshot → 标签后附快照日期,让访客知道站内读的是哪一版
            if link.get("stamp") == "snapshot" and item.get("snapshot_date"):
                label += f'<em class="stamp">{_esc(item["snapshot_date"])}</em>'
            # mode: embed → 站内展开阅读(iframe 懒加载,点开才请求,不拖慢首屏)
            if link.get("mode") == "embed":
                parts.append(
                    f'<button type="button" class="{cls}" data-embed="{href}" '
                    f'aria-expanded="false">{label}</button>'
                )
                embed_block = f"""<div class="embed" data-embed-wrap hidden>
    <iframe data-embed-frame title="{_esc(item.get('title', '文档'))}" loading="lazy"></iframe>
    <p class="embed-fallback">看不到内容?<a href="{href}" target="_blank" rel="noopener">在新标签打开</a>(部分手机浏览器不支持内嵌 PDF)。</p>
  </div>"""
            else:
                parts.append(
                    f'<a class="{cls}" href="{href}" target="_blank" rel="noopener">{label}</a>'
                )
        links_block = f'<div class="go-row">{"".join(parts)}</div>{embed_block}'

    body = item.get("body", "")
    body_block = f'<p class="sc-body">{_esc(body)}</p>' if body else ""

    return f"""<article class="sc-card reveal" id="sc-{_esc(item['id'])}">
  <header>
    <span class="kind">{_esc(KIND_LABELS.get(kind, kind or '产出'))}</span>
    {status_block}
  </header>
  <h3>{_esc(item.get('title', '(无标题)'))}</h3>
  <p class="sc-summary">{_esc(item.get('summary', ''))}</p>
{note_block}
{sections_block}
{body_block}
{links_block}
</article>"""


def render_showcase(items: list[dict]) -> str:
    if not items:
        return ""
    cards = "\n".join(render_showcase_card(i) for i in items)
    return f"""<section id="showcase" class="showcase-wrap">
  <div class="section-label"><span>成果</span><em>{len(items)} 项</em></div>
  <p class="showcase-lede">方法与系统已就位，真结果在路上。以下链接均指向仓库最新版本。</p>
  <div class="showcase">
{cards}
  </div>
</section>"""


# 评价指标不进画布:它跟每个因子都连,画进去就是一片蜘蛛网,还白占一整列。
# 改成浮在画布右上角的贴片,点它照样高亮完整上游链路(ADR-0019 的论点不变)。
OVERLAY_LAYERS = frozenset({"metric"})


def render_metric_card(g: "graph_mod.Graph") -> str:
    layer = next((l for l in g.layers if l["id"] in OVERLAY_LAYERS), None)
    ids = [n for lid in OVERLAY_LAYERS for n in g.nodes_in(lid)]
    if not layer or not ids:
        return ""
    hue = graph_mod.LAYER_HUE.get(layer["id"], 320)
    chips = "".join(
        f'<button type="button" class="m-chip{" has-guard" if g.guards_of(nid) else ""}" '
        f'data-node="{_esc(nid)}">{_esc(g.nodes[nid].get("label", nid))}</button>'
        for nid in ids
    )
    return f"""<aside class="metrics" data-metrics style="--m-hue:{hue}">
            <span class="m-head">{_esc(layer["label"])}<em>{_esc(layer.get("note", ""))}</em></span>
            <div class="m-chips">{chips}</div>
          </aside>"""


def render_film(film: dict) -> str:
    """首屏内联播放器。原生控件保证移动端可直接播放,不再跳进灯箱。"""
    if not film:
        return ""
    status = film.get("status", "")
    return f"""  <figure class="film r-5">
    <div class="film-head">
      <div>
        <span class="film-label">{_esc(film.get('label', '演示'))}{f' · {_esc(status)}' if status else ''}</span>
        <strong>{_esc(film.get('title', ''))}</strong>
      </div>
      <span class="film-dur">{_esc(film.get('duration', ''))}</span>
    </div>
    <video class="film-player" src="{_esc(film['video'])}"
           poster="{_esc(film['poster_dark'])}"
           data-theme-poster data-poster-dark="{_esc(film['poster_dark'])}"
           data-poster-light="{_esc(film['poster_light'])}"
           controls playsinline preload="metadata"
           aria-label="{_esc(film.get('title', '演示视频'))}"></video>
    <figcaption>{_esc(film.get('summary', ''))}{f'<span class="film-note">{_esc(film["note"])}</span>' if film.get("note") else ''}</figcaption>
  </figure>"""


def render_graph_section() -> tuple[str, str]:
    """方法依赖图。返回 (HTML, 喂给 JS 的 JSON)。图不存在时静默跳过。"""
    if not graph_mod.GRAPH_FILE.exists():
        return "", ""
    g = graph_mod.load_graph()
    if not graph_mod.is_dag(g):
        raise ValueError("graph.yaml 有环:回溯会死循环")
    laid = graph_mod.layout(g, exclude=OVERLAY_LAYERS)
    svg = graph_mod.render_svg(g, laid)
    payload = json.dumps(graph_mod.node_payload(g), ensure_ascii=False, separators=(",", ":"))
    legend = "".join(
        f'<span class="lg"><i style="background:hsl({graph_mod.LAYER_HUE.get(l["id"], 220)} 70% var(--g-lum))"></i>'
        f'{_esc(l["label"])}</span>'
        for l in g.layers
    )
    # --canvas 是图的自然宽度:展开的终点与 svg 宽度都由它算,别再各处写死数字。
    # 注意 reveal 只挂在导语上,**不能挂在 section 上** —— 入场动画的 transform 会成为
    # 里面 position:sticky 的包含块,那 0.6s 里粘住的图会跟着位移 16px,看着就是"抖一下"。
    html_block = f"""<section id="graph" class="graph-wrap" style="--canvas:{laid['width']}px">
  <div class="graph-intro reveal">
    <div class="section-label"><span>方法依赖图</span><em>{len(g.nodes)} 节点 · {len(g.edges)} 依赖</em></div>
    <p class="graph-lede">论文说因子的可解释性"可一路回溯到具体字段与有限算子"。<strong>点任意节点(含右上角的评价指标),看它的完整上游链路</strong> —— 这张图就是那句话的证据。</p>
    <div class="graph-legend">{legend}<span class="lg guard"><i></i>带防线的节点</span></div>
  </div>
  <div class="graph-track" data-graph-track>
    <div class="graph-sticky" data-graph-sticky>
      <div class="graph-stage graph-bleed">
        <div class="graph-col">
          <div class="graph-scroll" data-graph-scroll>{svg}</div>
          {render_metric_card(g)}
          <p class="graph-hint" data-graph-hint>← 左右滑动查看完整图 →</p>
        </div>
        <aside class="trace" data-trace hidden>
        <button type="button" class="trace-close" data-trace-close aria-label="关闭">×</button>
        <span class="trace-layer" data-trace-layer></span>
        <h3 data-trace-title></h3>
        <p class="trace-one" data-trace-one></p>
        <div class="trace-guards" data-trace-guards></div>
        <div class="trace-chain" data-trace-chain></div>
        <div class="trace-refs" data-trace-refs></div>
        </aside>
      </div>
    </div>
    <div class="graph-runway" aria-hidden="true"></div>
  </div>
</section>"""
    return html_block, payload


def render_form() -> str:
    type_opts = "".join(f'<option value="{_esc(t)}">{_esc(t)}</option>' for t in ISSUE_TYPES)
    filter_type_opts = type_opts
    prio_opts = "".join(
        f'<option value="{_esc(v)}"{" selected" if v == "中" else ""}>{_esc(v)}</option>'
        for v in PRIORITIES
    )
    # honeypot 字段 website:真人不可见,机器人易填 → 后端据此丢弃
    return f"""<section id="submit" class="submit reveal">
  <div class="submit-head">
    <span class="eyebrow">工单入口</span>
    <h2>提问 / 建议</h2>
    <p>在这里直接提交,系统会用项目账号同步成一条 GitHub Issue —— <strong>你不需要 GitHub 账号</strong>。仓库公开,请勿填敏感数据。</p>
  </div>
  <form id="intake" novalidate>
    <div class="grid">
      <label class="field">你的称呼 <span class="req">*</span>
        <input name="submitter" required maxlength="40" placeholder="怎么称呼你">
      </label>
      <label class="field">标题 <span class="req">*</span>
        <input name="title" required maxlength="120" placeholder="一句话说清问题或建议">
      </label>
    </div>
    <label class="field">详细描述 <span class="req">*</span>
      <textarea name="description" required rows="5" maxlength="4000" placeholder="背景、你观察到什么、期望怎样"></textarea>
    </label>
    <div class="grid grid-3">
      <label class="field">类型
        <select name="type">{type_opts}</select>
      </label>
      <label class="field">优先级
        <select name="priority">{prio_opts}</select>
      </label>
      <label class="field">关联工单
        <input name="related_issues" data-ref-input maxlength="80" inputmode="numeric" placeholder="工单号,如 #12(可选)">
        <span class="hint" data-ref-hint>最多 {MAX_RELATED_ISSUES} 条;也可在下方「历史工单」点「引用」</span>
      </label>
    </div>
    <div class="grid">
      <div class="field">截图
        <input class="file-hidden" name="screenshot" type="file" accept="image/png,image/jpeg,image/webp,image/gif" tabindex="-1">
        <div class="shot-zone" data-screenshot-zone tabindex="0" role="button" aria-label="截图粘贴区域">
          <span data-screenshot-hint>点此后粘贴截图,也可拖入图片。</span>
          <button type="button" class="pick-btn" data-screenshot-pick>选择图片</button>
        </div>
      </div>
      <label class="field">附件链接
      <input name="attachment" type="url" maxlength="500" placeholder="截图 / 文档的公开链接(可选)">
      </label>
    </div>
    <div class="shot-preview" data-screenshot-preview hidden>
      <img alt="截图预览" data-screenshot-image>
      <div class="shot-meta">
        <strong data-screenshot-name></strong>
        <span data-screenshot-size></span>
      </div>
      <div class="shot-actions">
        <button type="button" class="icon-btn" data-screenshot-edit aria-label="更换截图" title="更换截图">↻</button>
        <button type="button" class="icon-btn danger" data-screenshot-remove aria-label="删除截图" title="删除截图">×</button>
      </div>
    </div>
    <label class="check">
      <input type="checkbox" name="needs_review" value="1">
      <span>
        <strong>需要他人审核</strong>
        <em>内容还没验证过(比如和 AI 讨论出来的结论),希望别人复核后再采信 —— 会打上「{REVIEW_LABEL}」标签</em>
      </span>
    </label>
    <input class="hp" type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">
    <div class="submit-row">
      <button type="submit" class="btn-primary">提交工单</button>
      <p id="result" class="result" role="status" aria-live="polite"></p>
    </div>
  </form>
  <div class="history" id="history">
    <div class="history-head">
      <div>
        <span class="eyebrow">历史工单</span>
        <h3>最近提交</h3>
      </div>
      <button type="button" class="icon-btn" data-issues-refresh aria-label="刷新历史工单" title="刷新历史工单">↻</button>
    </div>
    <div class="filters" hidden data-issue-filters>
      <select data-filter-state aria-label="按状态筛选">
        <option value="">全部状态</option>
        <option value="open">处理中</option>
        <option value="closed">已关闭</option>
      </select>
      <select data-filter-type aria-label="按类型筛选">
        <option value="">全部类型</option>
        {filter_type_opts}
      </select>
      <select data-filter-submitter aria-label="按提出者筛选">
        <option value="">全部提出者</option>
      </select>
      <label class="toggle"><input type="checkbox" data-filter-review>只看{REVIEW_LABEL}</label>
      <label class="toggle"><input type="checkbox" data-collapse-replies>收起回复</label>
      <button type="button" class="link-btn" data-filter-reset hidden>清除筛选</button>
    </div>
    <div class="issue-list" data-issue-list>
      <p class="empty">正在读取...</p>
    </div>
    <p class="empty" data-issue-empty hidden>没有符合筛选条件的工单。</p>
    <button type="button" class="more-btn" data-issues-more hidden>展开全部</button>
  </div>
</section>"""


# 主题在 <head> 里就定下来:等到底部 JS 再切会先闪一帧深色,白天看着刺眼。
# 无历史选择时跟随系统 —— 白天系统本来就是浅色。
THEME_BOOT_JS = (
    "(function(){try{var s=localStorage.getItem('alpha-theme');"
    "var t=(s==='light'||s==='dark')?s:"
    "((window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark');"
    "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();"
)

THEME_TOGGLE = (
    '<button type="button" class="theme-toggle" data-theme-toggle aria-label="切换配色">'
    '<svg class="i-sun" viewBox="0 0 24 24" aria-hidden="true">'
    '<circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2.6v2M12 19.4v2M4.4 4.4l1.4 1.4M18.2 18.2l1.4 1.4'
    'M2.6 12h2M19.4 12h2M4.4 19.6l1.4-1.4M18.2 5.8l1.4-1.4"/></svg>'
    '<svg class="i-moon" viewBox="0 0 24 24" aria-hidden="true">'
    '<path d="M20 14.6A8.6 8.6 0 0 1 9.4 4 7.1 7.1 0 1 0 20 14.6Z"/></svg>'
    "</button>"
)


def render_page(packets: list[dict], showcase: list[dict], css: str, film: dict | None = None) -> str:
    film = film or {}
    graph_html, graph_data = render_graph_section()
    cards = "\n".join(render_packet_card(p) for p in packets) or "<p>还没有想法卡片。</p>"
    hero = f"""<section class="hero{' has-film' if film else ''}">
  <div class="hero-copy">
    <span class="eyebrow r-1"><span class="pulse"></span>AI · 可解释 Alpha 因子</span>
    <h1 class="r-2">结构化字段之外,<br><em>文本</em>还剩多少 <em>alpha</em>?</h1>
    <p class="lede r-3">当数据库已经公开了同一事件的关键数字,LLM 读公告正文还能多告诉我们什么?
    以 A 股业绩预告为检验场 —— 增量存在与否,两个方向都是结论。</p>
    <div class="chips r-4">
      <span class="chip">防 look-ahead</span>
      <span class="chip">样本外滚动</span>
      <span class="chip">纯代码回测</span>
      <span class="chip">有对照组</span>
      <span class="chip">阴性结果也是结论</span>
    </div>
  </div>
{render_film(film)}
</section>"""
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark light">
<link rel="icon" type="image/svg+xml" href="{FAVICON_HREF}">
<link rel="shortcut icon" type="image/svg+xml" href="{FAVICON_HREF}">
<title>Alpha 研学 · 想法流</title>
<script>{THEME_BOOT_JS}</script>
<style>
{css}
</style>
</head>
<body>
<div class="bg" aria-hidden="true"><div class="aurora"></div><div class="grid-overlay"></div></div>
<header class="site">
  <a class="brand" href="#top"><span class="logo"></span>Alpha 研学</a>
  <nav><a href="#feed">想法流</a>{'<a href="#graph">方法图</a>' if graph_html else ''}{'<a href="#showcase">成果</a>' if showcase else ''}<a href="#submit" class="nav-cta">提问 / 建议</a>{THEME_TOGGLE}</nav>
</header>
<main id="top">
{hero}
<section id="feed" class="feed-wrap">
  <div class="section-label"><span>想法流</span><em>{len(packets)} 张卡片</em></div>
  <div class="feed">
{cards}
  </div>
</section>
{graph_html}
{render_showcase(showcase)}
{render_form()}
</main>
<footer class="site-foot">
  <p>可解释 Alpha 因子研究 · AI 提假设,确定性回测裁决真伪。</p>
  <a class="credit" href="https://github.com/kyui-azusa" target="_blank" rel="noopener" aria-label="GitHub @kyui-azusa">
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 .5a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.4-4-1.4-.5-1.3-1.2-1.7-1.2-1.7-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.7 2.6 1.2 3.3.9.1-.7.4-1.2.7-1.5-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0c2.3-1.5 3.3-1.2 3.3-1.2.6 1.6.2 2.9.1 3.2.8.9 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .5Z"/></svg>
    <span>Powered by 周梓煜 · GitHub @kyui-azusa</span>
  </a>
</footer>
<script>
var GRAPH_DATA = {graph_data or "null"};
{GRAPH_JS}
{JS}
</script>
</body>
</html>"""


GRAPH_JS = """
// 方法依赖图:点节点 → 高亮全部上游祖先 + 回溯面板(ADR-0019)
(function () {
  if (!window.GRAPH_DATA) return;
  var G = window.GRAPH_DATA;
  var svg = document.getElementById('graph-svg');
  var panel = document.querySelector('[data-trace]');
  var stage = document.querySelector('.graph-stage');
  if (!svg || !panel) return;

  var preds = {};
  G.edges.forEach(function (e) { (preds[e.t] = preds[e.t] || []).push(e.f); });

  function ancestors(id) {
    var seen = {}, stack = (preds[id] || []).slice();
    while (stack.length) {
      var cur = stack.pop();
      if (seen[cur]) continue;
      seen[cur] = 1;
      (preds[cur] || []).forEach(function (p) { stack.push(p); });
    }
    return seen;
  }

  function esc(t) {
    return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  // 评价指标是浮在画布上的贴片(不在 SVG 里),但点它要和点节点完全一样
  var chips = Array.prototype.slice.call(document.querySelectorAll('.m-chip'));
  function syncChips(id) {
    chips.forEach(function (c) { c.classList.toggle('is-on', c.dataset.node === id); });
  }
  chips.forEach(function (c) {
    c.addEventListener('click', function () { select(c.dataset.node); });
  });

  function reset() {
    svg.querySelectorAll('.g-node, .g-edge').forEach(function (el) {
      el.classList.remove('lit'); el.classList.remove('dim');
    });
    syncChips(null);
    panel.hidden = true;
    if (stage) stage.classList.remove('with-panel');
    syncHint();          // 面板收起后画布变宽,提示行要跟着重算
  }

  function select(id) {
    var lit = ancestors(id);
    lit[id] = 1;
    syncChips(id);
    svg.querySelectorAll('.g-node').forEach(function (el) {
      var on = lit[el.dataset.node];
      el.classList.toggle('lit', !!on);
      el.classList.toggle('dim', !on);
    });
    svg.querySelectorAll('.g-edge').forEach(function (el) {
      var on = lit[el.dataset.from] && lit[el.dataset.to];
      el.classList.toggle('lit', !!on);
      el.classList.toggle('dim', !on);
    });

    var node = G.nodes[id];
    panel.querySelector('[data-trace-layer]').textContent = G.layerLabels[node.layer] || node.layer;
    panel.querySelector('[data-trace-title]').textContent = node.label;
    panel.querySelector('[data-trace-one]').textContent = node.one;

    panel.querySelector('[data-trace-guards]').innerHTML = (node.guards || []).map(function (g) {
      return '<div class="tg"><strong>' + esc(g.label) + '</strong><span>' + esc(g.one) + '</span></div>';
    }).join('');

    // 上游链路:按层分组、逐层缩进,一直列到原始字段
    var chain = '';
    var total = 0;
    G.layers.forEach(function (layerId) {
      var members = Object.keys(lit).filter(function (n) {
        return n !== id && G.nodes[n] && G.nodes[n].layer === layerId;
      }).sort();
      if (!members.length) return;
      total += members.length;
      chain += '<div class="tc-layer"><span class="tc-name">' + esc(G.layerLabels[layerId]) + '</span>'
        + '<div class="tc-items">' + members.map(function (n) {
          return '<code>' + esc(G.nodes[n].label) + '</code>';
        }).join('') + '</div></div>';
    });
    panel.querySelector('[data-trace-chain]').innerHTML = total
      ? '<p class="tc-head">上游依赖 ' + total + ' 项 —— 一路回溯到原始字段</p>' + chain
      : '<p class="tc-head">这是链路起点:原始字段,没有上游。</p>';

    panel.querySelector('[data-trace-refs]').innerHTML = (node.refs || []).length
      ? '<span class="tr-label">代码位置</span>' + node.refs.map(function (r) {
          return '<code>' + esc(r) + '</code>';
        }).join('')
      : '';

    panel.hidden = false;
    if (stage) stage.classList.add('with-panel');
    syncHint();          // 面板占掉 330px 后画布又变窄,提示行要跟着重算
    keepVisible(id);
  }

  // 选中的节点常在右侧列、正好在横向滚动区之外 —— 把它带进视野
  function keepVisible(id) {
    var sc = document.querySelector('[data-graph-scroll]');
    var el = svg.querySelector('.g-node[data-node="' + id + '"]');
    if (!sc || !el || sc.scrollWidth <= sc.clientWidth) return;
    var er = el.getBoundingClientRect(), sr = sc.getBoundingClientRect();
    var pad = 24;
    if (er.right > sr.right - pad) sc.scrollLeft += er.right - sr.right + pad;
    else if (er.left < sr.left + pad) sc.scrollLeft -= sr.left + pad - er.left;
  }

  svg.querySelectorAll('.g-node').forEach(function (el) {
    el.addEventListener('click', function () { select(el.dataset.node); });
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(el.dataset.node); }
    });
  });
  svg.addEventListener('click', function (e) { if (e.target === svg) reset(); });
  panel.querySelector('[data-trace-close]').addEventListener('click', reset);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') reset(); });

  // 图比屏幕宽时才提示可横向滑动。
  // 带滞回(12px 才亮、≤2px 才灭)且只改透明度不改 display —— 临界点上宽度来回一两像素时,
  // 用 display 会一边抽一边改变页面高度,底下的内容跟着跳。
  var scroller = document.querySelector('[data-graph-scroll]');
  var hint = document.querySelector('[data-graph-hint]');
  function syncHint() {
    if (!scroller || !hint) return;
    var over = scroller.scrollWidth - scroller.clientWidth;
    if (over > 12) hint.classList.remove('is-off');
    else if (over <= 2) hint.classList.add('is-off');
  }
  syncHint();

  // 展开:滚到这一节先粘住,把画布从版心宽推到整张图放得下(--gx 0→1),再放行
  var wrap = document.querySelector('.graph-wrap');
  var track = document.querySelector('[data-graph-track]');
  var stick = document.querySelector('[data-graph-sticky]');
  var runway = document.querySelector('.graph-runway');
  var canStick = window.matchMedia('(min-width: 820px) and (min-height: 760px) and (prefers-reduced-motion: no-preference)');
  var geo = null;        // 几何只在 resize 时量一次;滚动中只做算术,不读布局
  var queued = false;
  var lastP = -1;

  function measure() {
    if (!canStick.matches) {
      geo = null;
      wrap.style.removeProperty('--gx');   // 交回给 CSS(窄屏/矮屏直接是展开态)
      lastP = -1;
      return;
    }
    // 行程直接取跑道高度:它不受提示行显隐影响,量出来才稳
    var span = runway.offsetHeight;
    var top = parseFloat(getComputedStyle(stick).top) || 0;
    // 用 offsetTop 累加而不是 getBoundingClientRect:.reveal 入场时带着 transform,
    // rect 会把那 16px 位移一起量进去,算出来的起点偏一截
    var y = 0;
    for (var el = track; el; el = el.offsetParent) y += el.offsetTop;
    geo = span > 8 ? { start: y - top, span: span } : null;
  }

  function apply() {
    queued = false;
    if (!geo) return;
    var p = (window.scrollY - geo.start) / geo.span;
    // 两端吸附 + 量化到 1%:临界点附近不再因为亚像素抖动反复改样式
    p = p < 0.02 ? 0 : p > 0.98 ? 1 : p;
    p = p * p * (3 - 2 * p);                              // smoothstep:两头缓,中段跟手
    p = Math.round(p * 100) / 100;
    if (p === lastP) return;
    lastP = p;
    wrap.style.setProperty('--gx', p);
    syncHint();
  }

  function onScroll() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(apply);
  }

  var resizeTimer = null;
  function onResize() {
    // 重量一次的活儿防抖:拖窗口 / 手机地址栏收放会连着触发几十次 resize
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      measure();
      lastP = -1;
      apply();
      syncHint();
    }, 120);
  }

  if (wrap && track && stick && runway) {
    measure();
    apply();
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onResize);
    window.addEventListener('load', onResize);   // 字体/图加载完位置会挪,重量一次
    if (canStick.addEventListener) canStick.addEventListener('change', onResize);
  }
})();
"""

JS = """
// 配色切换:选择记在 localStorage;没选过就跟随系统(含系统白天/夜间的实时切换)
(function () {
  var root = document.documentElement;
  var btn = document.querySelector('[data-theme-toggle]');
  var film = document.querySelector('[data-theme-poster]');
  var KEY = 'alpha-theme';
  function syncFilmPoster() {
    if (!film) return;
    var key = root.getAttribute('data-theme') === 'light' ? 'posterLight' : 'posterDark';
    var next = film.dataset[key];
    if (next && film.getAttribute('poster') !== next) film.setAttribute('poster', next);
  }
  function label() {
    var light = root.getAttribute('data-theme') === 'light';
    var text = light ? '切换到深色' : '切换到浅色';
    if (!btn) return;
    btn.setAttribute('aria-label', text);
    btn.setAttribute('title', text);
    btn.setAttribute('aria-pressed', String(light));
  }
  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }
  if (btn) {
    btn.addEventListener('click', function () {
      var next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
      syncFilmPoster();
      label();
    });
  }
  if (window.matchMedia) {
    var mq = window.matchMedia('(prefers-color-scheme: light)');
    var follow = function (e) {
      if (stored()) return;   // 手动选过就不再被系统覆盖
      root.setAttribute('data-theme', e.matches ? 'light' : 'dark');
      syncFilmPoster();
      label();
    };
    if (mq.addEventListener) mq.addEventListener('change', follow);
    else if (mq.addListener) mq.addListener(follow);
  }
  syncFilmPoster();
  label();
})();

// 站内阅读:iframe 懒加载,点开才请求(574KB 的 PDF 不该拖慢首屏)
document.querySelectorAll('[data-embed]').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var card = btn.closest('.sc-card');
    var wrap = card && card.querySelector('[data-embed-wrap]');
    if (!wrap) return;
    var frame = wrap.querySelector('[data-embed-frame]');
    var opening = wrap.hidden;
    if (opening && frame && !frame.getAttribute('src')) {
      frame.setAttribute('src', btn.dataset.embed + '#view=FitH');
    }
    wrap.hidden = !opening;
    btn.setAttribute('aria-expanded', String(opening));
    btn.classList.toggle('open', opening);
    if (opening) wrap.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  });
});

// 复制转发文案
document.querySelectorAll('.copy').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var card = document.getElementById(btn.dataset.id);
    var title = card.querySelector('h3').innerText;
    var insight = card.querySelector('.insight').innerText;
    var text = '【' + title + '】' + insight + ' ' + location.href.split('#')[0] + '#' + btn.dataset.id;
    navigator.clipboard.writeText(text).then(function () {
      var old = btn.innerText; btn.innerText = '已复制 ✔';
      setTimeout(function () { btn.innerText = old; }, 1500);
    });
  });
});

// 入场动效(尊重 reduced-motion)
if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches && 'IntersectionObserver' in window) {
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12 });
  document.querySelectorAll('.reveal').forEach(function (el) { io.observe(el); });
} else {
  document.querySelectorAll('.reveal').forEach(function (el) { el.classList.add('in'); });
}

// 工单表单 → 同源 /api/intake(后端用项目账号建 issue)
var form = document.getElementById('intake');
if (form) {
  var screenshotFile = null;
  var screenshotUrl = null;
  var screenshotInput = form.querySelector('input[name=screenshot]');
  var screenshotZone = form.querySelector('[data-screenshot-zone]');
  var screenshotHint = form.querySelector('[data-screenshot-hint]');
  var screenshotPreview = form.querySelector('[data-screenshot-preview]');
  var screenshotImage = form.querySelector('[data-screenshot-image]');
  var screenshotName = form.querySelector('[data-screenshot-name]');
  var screenshotSize = form.querySelector('[data-screenshot-size]');
  var screenshotEdit = form.querySelector('[data-screenshot-edit]');
  var screenshotRemove = form.querySelector('[data-screenshot-remove]');
  var screenshotPick = form.querySelector('[data-screenshot-pick]');
  var issueList = document.querySelector('[data-issue-list]');
  var issuesRefresh = document.querySelector('[data-issues-refresh]');
  var issuesMore = document.querySelector('[data-issues-more]');
  var issueEmpty = document.querySelector('[data-issue-empty]');
  var issueFilters = document.querySelector('[data-issue-filters]');
  var filterState = document.querySelector('[data-filter-state]');
  var filterType = document.querySelector('[data-filter-type]');
  var filterSubmitter = document.querySelector('[data-filter-submitter]');
  var filterReview = document.querySelector('[data-filter-review]');
  var filterReset = document.querySelector('[data-filter-reset]');
  var collapseReplies = document.querySelector('[data-collapse-replies]');
  var ISSUE_TYPE_NAMES = ['功能', '缺陷', '问题', '建议'];   // 与 build.py 的 ISSUE_TYPES 同步
  var REVIEW_LABEL = '待审核';                              // 与 intake_service.REVIEW_LABEL 同步
  var ISSUE_PREVIEW = 8;      // 全量工单一次铺开会把页面撑得很长,先露最近几条
  var issuesExpanded = false;
  var refInput = form.querySelector('[data-ref-input]');
  var refHint = form.querySelector('[data-ref-hint]');
  var refHintText = refHint ? refHint.textContent : '';
  var REF_MAX = 5;

  function escapeHtml(text) {
    return String(text == null ? '' : text).replace(/[&<>"']/g, function (ch) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch];
    });
  }

  function formatDate(value) {
    if (!value) return '';
    try {
      return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
    } catch (_) {
      return value;
    }
  }

  // 关联工单:新工单可以指着老工单说话。只往输入框里塞号码,不做站内回复层级 ——
  // 正文里的 #12 由 GitHub 自动交叉引用。
  function parseRefs(text) {
    var out = [];
    var found = String(text == null ? '' : text).match(/\\d{1,7}/g) || [];
    for (var i = 0; i < found.length; i += 1) {
      var n = parseInt(found[i], 10);
      if (n > 0 && out.indexOf(n) < 0) out.push(n);
    }
    return out.slice(0, REF_MAX);
  }

  function currentRefs() { return refInput ? parseRefs(refInput.value) : []; }

  function setRefs(list) {
    if (!refInput) return;
    refInput.value = list.map(function (n) { return '#' + n; }).join(' ');
    syncCiteButtons();
  }

  function refMessage(text, isError) {
    if (!refHint) return;
    refHint.textContent = text || refHintText;
    refHint.classList.toggle('err', !!isError);
    refHint.classList.toggle('ok', !isError && !!text);
  }

  function syncCiteButtons() {
    if (!issueList) return;
    var refs = currentRefs();
    var buttons = issueList.querySelectorAll('[data-cite]');
    for (var i = 0; i < buttons.length; i += 1) {
      var cited = refs.indexOf(parseInt(buttons[i].getAttribute('data-cite'), 10)) >= 0;
      buttons[i].classList.toggle('done', cited);
      buttons[i].textContent = cited ? '已引用' : '引用';
    }
  }

  function citeIssue(number) {
    if (!refInput || !(number > 0)) return;
    var refs = currentRefs();
    var at = refs.indexOf(number);
    if (at >= 0) {                       // 再点一次 = 取消引用,不用回表单里删字
      refs.splice(at, 1);
      setRefs(refs);
      refMessage('已取消引用 #' + number, false);
      return;
    }
    if (refs.length >= REF_MAX) {
      refMessage('最多关联 ' + REF_MAX + ' 条工单', true);
      return;
    }
    refs.push(number);
    setRefs(refs);
    refMessage('已关联 #' + number, false);
    refInput.classList.add('flash');
    setTimeout(function () { refInput.classList.remove('flash'); }, 900);
    if (refInput.scrollIntoView) refInput.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }

  function renderIssues(items) {
    if (!issueList) return;
    if (!items || !items.length) {
      issueList.innerHTML = '<p class="empty">还没有历史工单。</p>';
      return;
    }
    issueList.innerHTML = items.map(function (item) {
      var labels = (item.labels || []).filter(function (name) { return name !== 'intake'; })
        .map(function (name) {
          var cls = name === REVIEW_LABEL ? ' review' : '';
          return '<span class="mini-label' + cls + '">' + escapeHtml(name) + '</span>';
        }).join('');
      // 标签可能被人在 GitHub 上摘掉,正文里的声明还在 —— 那也要显示出来
      if (item.needs_review && (item.labels || []).indexOf(REVIEW_LABEL) < 0) {
        labels += '<span class="mini-label review">' + REVIEW_LABEL + '</span>';
      }
      if (item.milestone) labels += '<span class="mini-label milestone">' + escapeHtml(item.milestone) + '</span>';
      // 回复是这块最有价值的内容,给它独立的答复块而不是挤在一行里截断
      var reply = '';
      if (item.receipt && item.receipt.summary) {
        var isReceipt = item.receipt.kind !== 'comment';
        reply = '<a class="reply' + (isReceipt ? ' is-receipt' : '') + '" href="'
          + escapeHtml(item.receipt.url || item.url) + '" target="_blank" rel="noopener">'
          + '<span class="reply-tag">' + (isReceipt ? '修复回执' : '项目回复') + '</span>'
          + '<span class="reply-text">' + escapeHtml(item.receipt.summary) + '</span>'
          + (item.receipt.created_at ? '<time>' + escapeHtml(formatDate(item.receipt.created_at)) + '</time>' : '')
          + '</a>';
      }
      var state = item.state === 'closed' ? '已关闭' : '处理中';
      // 筛选要用的三个维度直接挂在元素上:列表就是数据源,不再另存一份
      return '<div class="issue-item' + (reply ? ' has-reply' : '') + (item.needs_review ? ' needs-review' : '') + '"'
        + ' data-state="' + escapeHtml(item.state) + '"'
        + ' data-type="' + escapeHtml(issueType(item)) + '"'
        + ' data-submitter="' + escapeHtml(item.submitter || '') + '"'
        + ' data-review="' + (item.needs_review ? '1' : '') + '">'
        + '<span class="issue-no">#' + escapeHtml(item.number) + '</span>'
        + '<span class="issue-main"><strong><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + escapeHtml(item.title) + '</a></strong><span class="issue-tags">' + labels + '</span>' + reply + '</span>'
        + '<span class="issue-side"><em class="state ' + escapeHtml(item.state) + '">' + state + '</em><time>' + escapeHtml(formatDate(item.created_at)) + '</time>'
        + '<button type="button" class="cite-btn" data-cite="' + escapeHtml(item.number) + '" title="在新工单里引用 #' + escapeHtml(item.number) + '">引用</button></span>'
        + '</div>';
    }).join('');
    fillSubmitters(items);
    if (issueFilters) issueFilters.hidden = false;
    applyIssueView();
    syncCiteButtons();
  }

  // 类型取四选一那枚标签(其余是 P:x / 待审核 / milestone,不是类型)
  function issueType(item) {
    var names = item.labels || [];
    for (var i = 0; i < names.length; i += 1) {
      if (ISSUE_TYPE_NAMES.indexOf(names[i]) >= 0) return names[i];
    }
    return '';
  }

  function fillSubmitters(items) {
    if (!filterSubmitter) return;
    var kept = filterSubmitter.value;
    var names = [];
    for (var i = 0; i < items.length; i += 1) {
      var name = items[i].submitter;
      if (name && names.indexOf(name) < 0) names.push(name);
    }
    names.sort();
    filterSubmitter.innerHTML = '<option value="">全部提出者</option>'
      + names.map(function (n) { return '<option value="' + escapeHtml(n) + '">' + escapeHtml(n) + '</option>'; }).join('');
    if (names.indexOf(kept) >= 0) filterSubmitter.value = kept;   // 刷新不该把已选的筛选条件弄丢
  }

  function filterValues() {
    return {
      state: filterState ? filterState.value : '',
      type: filterType ? filterType.value : '',
      submitter: filterSubmitter ? filterSubmitter.value : '',
      review: !!(filterReview && filterReview.checked)
    };
  }

  // 筛选先跑,折叠再跑:「展开全部 N 条」里的 N 说的是筛完还剩几条
  function applyIssueView() {
    if (!issueList) return;
    var f = filterValues();
    var active = !!(f.state || f.type || f.submitter || f.review);
    var items = issueList.querySelectorAll('.issue-item');
    var matched = 0;
    for (var i = 0; i < items.length; i += 1) {
      var el = items[i];
      var ok = (!f.state || el.getAttribute('data-state') === f.state)
        && (!f.type || el.getAttribute('data-type') === f.type)
        && (!f.submitter || el.getAttribute('data-submitter') === f.submitter)
        && (!f.review || el.getAttribute('data-review') === '1');
      if (!ok) { el.hidden = true; continue; }
      matched += 1;
      el.hidden = !issuesExpanded && matched > ISSUE_PREVIEW;
    }
    if (issueEmpty) issueEmpty.hidden = matched > 0 || !items.length;
    if (filterReset) filterReset.hidden = !active;
    if (issuesMore) {
      issuesMore.hidden = matched <= ISSUE_PREVIEW;
      issuesMore.textContent = issuesExpanded ? '收起' : '展开全部 ' + matched + ' 条';
    }
  }

  function loadIssues() {
    if (!issueList) return;
    issueList.innerHTML = '<p class="empty">正在读取...</p>';
    if (issuesMore) issuesMore.hidden = true;
    if (issueEmpty) issueEmpty.hidden = true;
    if (issueFilters) issueFilters.hidden = true;
    fetch('/api/intake/issues')
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (res.ok) renderIssues(res.d.issues || []);
        else issueList.innerHTML = '<p class="empty err">读取失败:' + escapeHtml(res.d.error || '请稍后重试') + '</p>';
      })
      .catch(function () { issueList.innerHTML = '<p class="empty err">网络错误,历史工单暂时不可用。</p>'; });
  }

  function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return Math.max(1, Math.round(bytes / 1024)) + ' KB';
    return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  }

  function showScreenshotHint(text, isError) {
    if (!screenshotHint) return;
    screenshotHint.textContent = text;
    if (screenshotZone) {
      screenshotZone.classList.toggle('ok', !isError && text.indexOf('已') === 0);
      screenshotZone.classList.toggle('err', !!isError);
    }
  }

  function setScreenshotFile(file, source) {
    if (!file || !file.type || file.type.indexOf('image/') !== 0) return false;
    if (file.size > 5 * 1024 * 1024) {
      showScreenshotHint('截图不能超过 5MB', true);
      return true;
    }
    if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
    screenshotFile = file;
    screenshotUrl = URL.createObjectURL(file);
    if (screenshotInput && window.DataTransfer) {
      var dt = new DataTransfer();
      dt.items.add(file);
      screenshotInput.files = dt.files;
    }
    if (screenshotPreview) screenshotPreview.hidden = false;
    if (screenshotImage) screenshotImage.src = screenshotUrl;
    if (screenshotName) screenshotName.textContent = file.name || 'clipboard-image';
    if (screenshotSize) screenshotSize.textContent = formatBytes(file.size);
    showScreenshotHint(source + ':' + (file.name || 'clipboard-image'), false);
    return true;
  }

  function clearScreenshot() {
    screenshotFile = null;
    if (screenshotUrl) URL.revokeObjectURL(screenshotUrl);
    screenshotUrl = null;
    if (screenshotInput) screenshotInput.value = '';
    if (screenshotPreview) screenshotPreview.hidden = true;
    if (screenshotImage) screenshotImage.removeAttribute('src');
    if (screenshotName) screenshotName.textContent = '';
    if (screenshotSize) screenshotSize.textContent = '';
    showScreenshotHint('点此后粘贴截图,也可拖入图片。', false);
  }

  function findImageFile(items) {
    for (var i = 0; i < items.length; i += 1) {
      var item = items[i];
      if (item.kind === 'file' && item.type && item.type.indexOf('image/') === 0) {
        return item.getAsFile();
      }
    }
    return null;
  }

  if (screenshotInput) {
    screenshotInput.addEventListener('change', function () {
      var file = screenshotInput.files && screenshotInput.files[0] ? screenshotInput.files[0] : null;
      if (file) setScreenshotFile(file, '已选择');
    });
  }

  if (screenshotPick) screenshotPick.addEventListener('click', function () { if (screenshotInput) screenshotInput.click(); });
  if (screenshotEdit) screenshotEdit.addEventListener('click', function () { if (screenshotInput) screenshotInput.click(); });
  if (screenshotRemove) screenshotRemove.addEventListener('click', clearScreenshot);
  if (issuesRefresh) issuesRefresh.addEventListener('click', loadIssues);

  [filterState, filterType, filterSubmitter, filterReview].forEach(function (el) {
    if (!el) return;
    el.addEventListener('change', function () {
      issuesExpanded = false;      // 换了筛选条件就回到「先看前几条」
      applyIssueView();
    });
  });

  if (filterReset) {
    filterReset.addEventListener('click', function () {
      if (filterState) filterState.value = '';
      if (filterType) filterType.value = '';
      if (filterSubmitter) filterSubmitter.value = '';
      if (filterReview) filterReview.checked = false;
      issuesExpanded = false;
      applyIssueView();
    });
  }

  if (collapseReplies && issueList) {
    collapseReplies.addEventListener('change', function () {
      issueList.classList.toggle('replies-off', collapseReplies.checked);
    });
  }

  if (issuesMore) {
    issuesMore.addEventListener('click', function () {
      issuesExpanded = !issuesExpanded;
      applyIssueView();
      if (!issuesExpanded && issueList.scrollIntoView) issueList.scrollIntoView({ block: 'start', behavior: 'smooth' });
    });
  }

  if (issueList) {
    issueList.addEventListener('click', function (e) {
      var btn = e.target.closest ? e.target.closest('[data-cite]') : null;
      if (!btn) return;
      e.preventDefault();
      citeIssue(parseInt(btn.getAttribute('data-cite'), 10));
    });
  }

  if (refInput) {
    refInput.addEventListener('input', function () { refMessage('', false); syncCiteButtons(); });
    refInput.addEventListener('blur', function () { setRefs(currentRefs()); });
  }

  if (screenshotZone) {
    screenshotZone.addEventListener('click', function (e) {
      if (e.target === screenshotPick) return;
      screenshotZone.focus();
    });
  }

  form.addEventListener('paste', function (e) {
    var file = e.clipboardData && e.clipboardData.items ? findImageFile(e.clipboardData.items) : null;
    if (setScreenshotFile(file, '已粘贴')) e.preventDefault();
  });

  form.addEventListener('dragover', function (e) {
    e.preventDefault();
    form.classList.add('dragging');
    if (screenshotZone) screenshotZone.classList.add('dragging');
  });
  form.addEventListener('dragleave', function () {
    form.classList.remove('dragging');
    if (screenshotZone) screenshotZone.classList.remove('dragging');
  });
  form.addEventListener('drop', function (e) {
    e.preventDefault();
    form.classList.remove('dragging');
    if (screenshotZone) screenshotZone.classList.remove('dragging');
    var file = e.dataTransfer && e.dataTransfer.files ? e.dataTransfer.files[0] : null;
    setScreenshotFile(file, '已拖入');
  });

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    var out = document.getElementById('result');
    var btn = form.querySelector('button[type=submit]');
    if (!form.submitter.value.trim() || !form.title.value.trim() || !form.description.value.trim()) {
      out.className = 'result err'; out.textContent = '请填写称呼、标题和描述'; return;
    }
    var shot = screenshotFile || (form.screenshot && form.screenshot.files ? form.screenshot.files[0] : null);
    if (shot && shot.size > 5 * 1024 * 1024) {
      out.className = 'result err'; out.textContent = '截图不能超过 5MB'; return;
    }
    btn.disabled = true; out.className = 'result'; out.textContent = '提交中…';
    var data = new FormData(form);
    if (screenshotFile) data.set('screenshot', screenshotFile, screenshotFile.name || 'clipboard-image.png');
    fetch('/api/intake', { method: 'POST', body: data })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (res) {
        if (res.ok) {
          out.className = 'result ok';
          out.innerHTML = res.d.issue_url
            ? '已提交 ✔ 已同步到 <a href="' + res.d.issue_url + '" target="_blank" rel="noopener">Issue #' + res.d.number + '</a>,谢谢!'
            : '已收到 ✔ 谢谢!(后台稍后同步)';
          form.reset();
          clearScreenshot();
          refMessage('', false);
          loadIssues();
        } else {
          out.className = 'result err'; out.textContent = '提交失败:' + (res.d.error || '请稍后重试');
        }
      })
      .catch(function () { out.className = 'result err'; out.textContent = '网络错误,请稍后重试'; })
      .finally(function () { btn.disabled = false; });
  });

  loadIssues();
}
"""


def main() -> None:
    packets = load_packets()
    showcase = load_showcase()
    film = load_hero_film()
    css = CSS_FILE.read_text(encoding="utf-8") if CSS_FILE.exists() else ""
    DIST.mkdir(parents=True, exist_ok=True)
    snapshots = copy_snapshots(showcase)
    media = copy_media(film)
    (DIST / "index.html").write_text(render_page(packets, showcase, css, film), encoding="utf-8")
    print(f"✔ 单文件生成 {len(packets)} 张卡片 / {len(showcase)} 项成果 → {(DIST / 'index.html').relative_to(ROOT.parent)}")
    for name, snap_date in snapshots:
        print(f"  快照 {name}(源修改于 {snap_date})")
    for name in media:
        print(f"  首屏视频 {name}({(DIST / name).stat().st_size / 1024:.0f} KB)")
    print(f"  生成日期 {date.today()};工单 → 同源 /api/intake")
    extras = [n for n, _ in snapshots] + media
    if extras:
        print(f"  部署需上传:index.html {' '.join(extras)}")


if __name__ == "__main__":
    main()
