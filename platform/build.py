"""静态站点生成器 —— content/packets/*.md → 单文件 dist/index.html。

产物是**单个自包含 index.html**(内联 CSS/JS,深色 AI-native 风格),便于用
deploy-static-site skill 上传。工单为页面内结构化表单,POST 同源 /api/intake,
由后端用项目所有者账号建 GitHub issue(ADR-0002 / CONTEXT: Intake Form/Fields)。

设计遵循:ADR-0008(feed 为首屏)/ 0014(packet 为内容文件)/ 0002(同源 intake)。
只用 pyyaml(已在 requirements)+ stdlib,无模板/markdown 第三方库。
"""
from __future__ import annotations

import html
import shutil
import urllib.parse
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
PACKETS_DIR = ROOT / "content" / "packets"
SHOWCASE_DIR = ROOT / "content" / "showcase"
CSS_FILE = ROOT / "static" / "style.css"
DIST = ROOT / "dist"

# Intake Fields(CONTEXT.md):提交人 / 标题 / 描述 / 附件 / 相关想法卡片 / 类型 / 优先级
ISSUE_TYPES = ["功能", "缺陷", "问题", "建议"]
PRIORITIES = ["低", "中", "高"]

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <defs>
    <linearGradient id="g" x1="12" y1="10" x2="52" y2="54" gradientUnits="userSpaceOnUse">
      <stop stop-color="#7c5cff"/>
      <stop offset="1" stop-color="#22d3ee"/>
    </linearGradient>
    <filter id="s" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="4" stdDeviation="5" flood-color="#7c5cff" flood-opacity=".55"/>
    </filter>
  </defs>
  <rect x="10" y="10" width="44" height="44" rx="15" fill="url(#g)" filter="url(#s)"/>
  <path d="M24 40V24h5.3l8.3 10.4V24H42v16h-5.1l-8.5-10.6V40H24Z" fill="#06070e"/>
</svg>"""
FAVICON_HREF = "data:image/svg+xml," + urllib.parse.quote(FAVICON_SVG, safe="/:;=?&,%#")


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
    if links:
        parts = []
        for link in links:
            label = _esc(link.get("label", "打开"))
            # stamp: snapshot → 标签后附快照日期,让访客知道站内读的是哪一版
            if link.get("stamp") == "snapshot" and item.get("snapshot_date"):
                label += f'<em class="stamp">{_esc(item["snapshot_date"])}</em>'
            parts.append(
                f'<a class="{"go primary" if link.get("primary") else "go"}" '
                f'href="{_esc(link.get("href", "#"))}" target="_blank" rel="noopener">'
                f"{label}</a>"
            )
        links_block = f'<div class="go-row">{"".join(parts)}</div>'

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


def render_form() -> str:
    type_opts = "".join(f'<option value="{_esc(t)}">{_esc(t)}</option>' for t in ISSUE_TYPES)
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
      <label class="field">相关想法卡片
        <input name="related_packet" maxlength="80" placeholder="卡片 id(可选)">
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
    <div class="issue-list" data-issue-list>
      <p class="empty">正在读取...</p>
    </div>
  </div>
</section>"""


def render_page(packets: list[dict], showcase: list[dict], css: str) -> str:
    cards = "\n".join(render_packet_card(p) for p in packets) or "<p>还没有想法卡片。</p>"
    hero = """<section class="hero">
  <span class="eyebrow"><span class="pulse"></span>AI · 可解释 Alpha 因子</span>
  <h1>智能体能否生成有<em>经济解释</em>的<br>A 股 <em>Alpha 因子</em>?</h1>
  <p class="lede">研究过程沉淀的短想法:一条进展、一张示意图、一个留给你的问题。</p>
  <div class="chips">
    <span class="chip">防 look-ahead</span>
    <span class="chip">样本外滚动</span>
    <span class="chip">纯代码回测</span>
    <span class="chip">LLM 只提想法</span>
  </div>
</section>"""
    return f"""<!doctype html>
<html lang="zh-CN" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<link rel="icon" type="image/svg+xml" href="{FAVICON_HREF}">
<link rel="shortcut icon" type="image/svg+xml" href="{FAVICON_HREF}">
<title>Alpha 研学 · 想法流</title>
<style>
{css}
</style>
</head>
<body>
<div class="bg" aria-hidden="true"><div class="aurora"></div><div class="grid-overlay"></div></div>
<header class="site">
  <a class="brand" href="#top"><span class="logo"></span>Alpha 研学</a>
  <nav><a href="#feed">想法流</a>{'<a href="#showcase">成果</a>' if showcase else ''}<a href="#submit" class="nav-cta">提问 / 建议</a></nav>
</header>
<main id="top">
{hero}
<section id="feed" class="feed-wrap">
  <div class="section-label"><span>想法流</span><em>{len(packets)} 张卡片</em></div>
  <div class="feed">
{cards}
  </div>
</section>
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
{JS}
</script>
</body>
</html>"""


JS = """
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

  function renderIssues(items) {
    if (!issueList) return;
    if (!items || !items.length) {
      issueList.innerHTML = '<p class="empty">还没有历史工单。</p>';
      return;
    }
    issueList.innerHTML = items.map(function (item) {
      var labels = (item.labels || []).filter(function (name) { return name !== 'intake'; })
        .map(function (name) { return '<span class="mini-label">' + escapeHtml(name) + '</span>'; }).join('');
      if (item.milestone) labels += '<span class="mini-label milestone">' + escapeHtml(item.milestone) + '</span>';
      var receipt = item.receipt && item.receipt.summary
        ? '<a class="receipt" href="' + escapeHtml(item.receipt.url || item.url) + '" target="_blank" rel="noopener">回执:' + escapeHtml(item.receipt.summary) + '</a>'
        : '';
      var state = item.state === 'closed' ? '已关闭' : '处理中';
      return '<div class="issue-item">'
        + '<span class="issue-no">#' + escapeHtml(item.number) + '</span>'
        + '<span class="issue-main"><strong><a href="' + escapeHtml(item.url) + '" target="_blank" rel="noopener">' + escapeHtml(item.title) + '</a></strong><span>' + labels + '</span>' + receipt + '</span>'
        + '<span class="issue-side"><em class="state ' + escapeHtml(item.state) + '">' + state + '</em><time>' + escapeHtml(formatDate(item.created_at)) + '</time></span>'
        + '</div>';
    }).join('');
  }

  function loadIssues() {
    if (!issueList) return;
    issueList.innerHTML = '<p class="empty">正在读取...</p>';
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
    css = CSS_FILE.read_text(encoding="utf-8") if CSS_FILE.exists() else ""
    DIST.mkdir(parents=True, exist_ok=True)
    snapshots = copy_snapshots(showcase)
    (DIST / "index.html").write_text(render_page(packets, showcase, css), encoding="utf-8")
    print(f"✔ 单文件生成 {len(packets)} 张卡片 / {len(showcase)} 项成果 → {(DIST / 'index.html').relative_to(ROOT.parent)}")
    for name, snap_date in snapshots:
        print(f"  快照 {name}(源修改于 {snap_date})")
    print(f"  生成日期 {date.today()};工单 → 同源 /api/intake")
    if snapshots:
        names = " ".join(n for n, _ in snapshots)
        print(f"  部署需上传:index.html {names}")


if __name__ == "__main__":
    main()
