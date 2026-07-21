"""工单入口后端(ADR-0002 / CONTEXT: Intake Form)。

同源架构:nginx 提供静态站点并把 `/api/intake` 反代到本服务(127.0.0.1)。
本服务只处理 POST /api/intake,把一次表单提交用**项目所有者账号**建一条 GitHub Issue:
    submitter → 正文;title → issue 标题;type/priority → labels;related/attachment/screenshot → 正文。
PAT 只在服务端环境变量,绝不进入浏览器 / 静态产物。防滥用:honeypot + 每 IP 限流。
未配置 GITHUB_TOKEN/REPO 时进入 dry-run:提交写入 INTAKE_LOG,便于联调。

环境变量:
    GITHUB_TOKEN   fine-grained PAT(仅本仓库、仅 Issues 读写)
    GITHUB_REPO    owner/repo
    PORT           监听端口,默认 8791(仅 127.0.0.1)
    RATE_PER_HOUR  每 IP 每小时上限,默认 12
    INTAKE_LOG     dry-run 落盘路径,默认 /var/log/alpha-intake/dryrun.ndjson
"""
from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "").strip()
PORT = int(os.environ.get("PORT", "8791"))
RATE_PER_HOUR = int(os.environ.get("RATE_PER_HOUR", "12"))
INTAKE_LOG = os.environ.get("INTAKE_LOG", "/var/log/alpha-intake/dryrun.ndjson")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(Path(__file__).resolve().parent / "uploads")))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
ISSUE_CACHE_SECONDS = int(os.environ.get("ISSUE_CACHE_SECONDS", "60"))

TYPE_LABELS = {
    "功能": "功能",
    "缺陷": "缺陷",
    "问题": "问题",
    "建议": "建议",
    "问题反馈": "问题",
    "改进建议": "建议",
    "疑问求解": "问题",
    "Bug": "缺陷",
}
VALID_PRIORITIES = {"低", "中", "高"}
MAX = {
    "submitter": 40,
    "title": 120,
    "description": 4000,
    "attachment": 500,
    "related_packet": 80,
    "screenshot_url": 500,
    "screenshot_name": 120,
}

_hits: dict[str, deque] = defaultdict(deque)
_issues_cache: dict[str, object] = {"ts": 0.0, "data": []}


def _github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "alpha-intake",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def _rate_limited(ip: str) -> bool:
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_PER_HOUR:
        return True
    q.append(now)
    return False


def _clean(form: dict, key: str) -> str:
    return (form.get(key, [""])[0] or "").strip()[: MAX.get(key, 500)]


def _detect_image(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif", ".gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    return None


def _public_base_from_headers(headers) -> str:
    if PUBLIC_BASE_URL:
        return PUBLIC_BASE_URL
    proto = headers.get("X-Forwarded-Proto") or "http"
    host = headers.get("Host") or f"127.0.0.1:{PORT}"
    return f"{proto}://{host}".rstrip("/")


def _save_screenshot(data: bytes, filename: str, headers) -> tuple[str, str]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("截图不能超过 5MB")
    detected = _detect_image(data)
    if detected is None:
        raise ValueError("截图格式仅支持 PNG、JPG、WebP 或 GIF")
    _, ext = detected

    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    rel_dir = Path("uploads") / day
    target_dir = UPLOAD_DIR / day
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{int(time.time())}-{secrets.token_urlsafe(8)}{ext}"
    (target_dir / safe_name).write_bytes(data)
    public_url = f"{_public_base_from_headers(headers)}/{rel_dir.as_posix()}/{safe_name}"
    display_name = Path(filename or safe_name).name[: MAX["screenshot_name"]]
    return public_url, display_name


def _parse_multipart(raw: bytes, content_type: str, headers) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\nMIME-Version: 1.0\r\n\r\n" + raw
    )
    form: dict[str, list[str]] = {}
    for part in msg.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename:
            if name != "screenshot" or not payload:
                continue
            url, display_name = _save_screenshot(payload, filename, headers)
            form.setdefault("screenshot_url", []).append(url)
            form.setdefault("screenshot_name", []).append(display_name)
            continue
        charset = part.get_content_charset() or "utf-8"
        form.setdefault(name, []).append(payload.decode(charset, errors="replace"))
    return form


def build_issue(form: dict) -> dict | None:
    if _clean(form, "website"):  # honeypot
        return None
    submitter = _clean(form, "submitter")
    title = _clean(form, "title")
    description = _clean(form, "description")
    if not (submitter and title and description):
        return None

    itype = _clean(form, "type")
    priority = _clean(form, "priority")
    related = _clean(form, "related_packet")
    attachment = _clean(form, "attachment")
    screenshot_url = _clean(form, "screenshot_url")
    screenshot_name = _clean(form, "screenshot_name")

    labels = ["intake"]
    if itype in TYPE_LABELS:
        labels.append(TYPE_LABELS[itype])
    if priority in VALID_PRIORITIES:
        labels.append(f"P:{priority}")

    body = [
        f"**提交人:** {submitter}",
        f"**类型:** {itype or '未指定'}　**优先级:** {priority or '未指定'}",
    ]
    if related:
        body.append(f"**相关想法卡片:** `{related}`")
    if attachment:
        body.append(f"**附件链接:** {attachment}")
    if screenshot_url:
        body.extend([f"**截图:** {screenshot_name or 'screenshot'}", f"![截图]({screenshot_url})"])
    body += ["", "---", "", description, "",
             f"_经想法流工单入口于 {datetime.now(timezone.utc).isoformat()} 提交_"]
    return {"title": f"[反馈] {title}", "body": "\n".join(body), "labels": labels}


def create_issue(payload: dict) -> dict:
    if not (GITHUB_TOKEN and GITHUB_REPO):
        os.makedirs(os.path.dirname(INTAKE_LOG), exist_ok=True)
        with open(INTAKE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), **payload}, ensure_ascii=False) + "\n")
        return {"dry_run": True}
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={**_github_headers(), "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    _issues_cache["ts"] = 0.0
    return {"issue_url": data.get("html_url"), "number": data.get("number")}


def _compact_issue(item: dict) -> dict:
    return {
        "number": item.get("number"),
        "title": str(item.get("title") or "").removeprefix("[反馈] "),
        "state": item.get("state"),
        "url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "labels": [label.get("name") for label in item.get("labels", []) if label.get("name")],
        "comments": item.get("comments", 0),
    }


def list_issues(limit: int = 20) -> dict:
    now = time.time()
    if now - float(_issues_cache.get("ts", 0.0)) < ISSUE_CACHE_SECONDS:
        return {"issues": _issues_cache.get("data", []), "cached": True}
    if not GITHUB_REPO:
        return {"issues": [], "cached": False}
    params = urllib.parse.urlencode(
        {"state": "all", "labels": "intake", "sort": "created", "direction": "desc", "per_page": limit}
    )
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}/issues?{params}",
        headers=_github_headers(),
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    issues = [_compact_issue(item) for item in data if "pull_request" not in item]
    _issues_cache.update({"ts": now, "data": issues})
    return {"issues": issues, "cached": False}


class Handler(BaseHTTPRequestHandler):
    server_version = "alpha-intake/2.0"

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _ip(self) -> str:
        xff = self.headers.get("X-Forwarded-For", "")
        return xff.split(",")[0].strip() if xff else self.client_address[0]

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/api/intake":
            return self._json(404, {"error": "not found"})
        if _rate_limited(self._ip()):
            return self._json(429, {"error": "提交过于频繁,请稍后再试"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_REQUEST_BYTES:
                return self._json(413, {"error": "提交内容过大,截图请控制在 5MB 以内"})
            raw = self.rfile.read(length)
            content_type = self.headers.get("Content-Type", "")
            if content_type.startswith("multipart/form-data"):
                form = _parse_multipart(raw, content_type, self.headers)
            else:
                form = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
            payload = build_issue(form)
            if payload is None:
                return self._json(400, {"error": "必填项缺失或提交被拒绝"})
            return self._json(201, {"ok": True, **create_issue(payload)})
        except ValueError as e:
            return self._json(400, {"error": str(e)})
        except urllib.error.HTTPError as e:
            return self._json(502, {"error": f"GitHub 拒绝:{e.code}"})
        except Exception as e:  # noqa: BLE001
            self.log_error("intake failed: %s", e)
            return self._json(500, {"error": "服务器内部错误"})

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        if path == "/api/intake/health":
            mode = "github" if (GITHUB_TOKEN and GITHUB_REPO) else "dry-run"
            return self._json(200, {"ok": True, "mode": mode})
        if path == "/api/intake/issues":
            try:
                return self._json(200, {"ok": True, **list_issues()})
            except urllib.error.HTTPError as e:
                return self._json(502, {"error": f"GitHub 拒绝:{e.code}"})
            except Exception as e:  # noqa: BLE001
                self.log_error("issue list failed: %s", e)
                return self._json(500, {"error": "历史工单读取失败"})
        return self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print(f"{self._ip()} - {fmt % args}")


def main() -> None:
    mode = "GitHub" if (GITHUB_TOKEN and GITHUB_REPO) else f"DRY-RUN → {INTAKE_LOG}"
    print(f"alpha-intake 监听 127.0.0.1:{PORT}  模式={mode}  限流={RATE_PER_HOUR}/时/IP")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
