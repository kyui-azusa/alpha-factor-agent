"""工单入口后端(ADR-0002 / CONTEXT: Intake Form)。

同源架构:nginx 提供静态站点并把 `/api/intake` 反代到本服务(127.0.0.1)。
本服务处理 POST /api/intake,把一次表单提交用**项目所有者账号**建一条 GitHub Issue:
    submitter → 正文;title → issue 标题;type/priority → labels;related/attachment/screenshot → 正文。
修复完成后,受保护的 POST /api/intake/receipts 可把简要回执回复到 GitHub Issue,
并由历史工单接口同步给网站展示。
PAT 只在服务端环境变量,绝不进入浏览器 / 静态产物。防滥用:honeypot + 每 IP 限流。
未配置 GITHUB_TOKEN/REPO 时进入 dry-run:提交写入 INTAKE_LOG,便于联调。

环境变量:
    GITHUB_TOKEN   fine-grained PAT(仅本仓库、仅 Issues 读写)
    GITHUB_REPO    owner/repo
    INTAKE_ADMIN_TOKEN  回执写入接口的管理员 token(仅服务端/运维使用)
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
INTAKE_ADMIN_TOKEN = os.environ.get("INTAKE_ADMIN_TOKEN", "").strip()
PORT = int(os.environ.get("PORT", "8791"))
RATE_PER_HOUR = int(os.environ.get("RATE_PER_HOUR", "12"))
INTAKE_LOG = os.environ.get("INTAKE_LOG", "/var/log/alpha-intake/dryrun.ndjson")
UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", str(Path(__file__).resolve().parent / "uploads")))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
MAX_REQUEST_BYTES = MAX_UPLOAD_BYTES + 64 * 1024
ISSUE_CACHE_SECONDS = int(os.environ.get("ISSUE_CACHE_SECONDS", "60"))
RECEIPT_MARKER = "<!-- alpha-intake-receipt -->"

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
    "issue_number": 16,
    "fixed_by": 40,
    "summary": 500,
    "repair": 1200,
    "result": 1200,
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


def _clean_text(value: object, max_len: int) -> str:
    return str(value or "").strip()[:max_len]


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _github_json(path: str, *, method: str = "GET", payload: dict | None = None) -> object:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = _github_headers()
    if payload is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"https://api.github.com/repos/{GITHUB_REPO}{path}",
        data=data,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def _receipt_body(receipt: dict) -> str:
    fixed_by = _clean_text(receipt.get("fixed_by"), MAX["fixed_by"])
    summary = _clean_text(receipt.get("summary"), MAX["summary"])
    repair = _clean_text(receipt.get("repair"), MAX["repair"])
    result = _clean_text(receipt.get("result"), MAX["result"])

    lines = [RECEIPT_MARKER, "### 修复回执", ""]
    if summary:
        lines.append(f"**简要概括:** {summary}")
    if repair:
        lines.extend(["", "**如何修复:**", repair])
    if result:
        lines.extend(["", "**修复结果:**", result])
    meta = []
    if fixed_by:
        meta.append(f"处理人:{fixed_by}")
    meta.append(f"时间:{datetime.now(timezone.utc).isoformat()}")
    lines.extend(["", f"_{' · '.join(meta)}_"])
    return "\n".join(lines)


def build_receipt(payload: dict) -> dict | None:
    try:
        issue_number = int(str(payload.get("issue_number", "")).strip())
    except ValueError:
        return None
    if issue_number <= 0:
        return None
    summary = _clean_text(payload.get("summary"), MAX["summary"])
    repair = _clean_text(payload.get("repair"), MAX["repair"])
    result = _clean_text(payload.get("result"), MAX["result"])
    if not (summary and repair and result):
        return None
    close_issue = _truthy(payload.get("close_issue", False))
    return {
        "issue_number": issue_number,
        "body": _receipt_body(
            {
                "fixed_by": payload.get("fixed_by"),
                "summary": summary,
                "repair": repair,
                "result": result,
            }
        ),
        "close_issue": close_issue,
    }


def create_receipt(receipt: dict) -> dict:
    issue_number = receipt["issue_number"]
    if not (GITHUB_TOKEN and GITHUB_REPO):
        os.makedirs(os.path.dirname(INTAKE_LOG), exist_ok=True)
        with open(INTAKE_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "receipt": receipt}, ensure_ascii=False) + "\n")
        return {"dry_run": True, "number": issue_number}

    comment = _github_json(
        f"/issues/{issue_number}/comments",
        method="POST",
        payload={"body": receipt["body"]},
    )
    if receipt.get("close_issue"):
        _github_json(f"/issues/{issue_number}", method="PATCH", payload={"state": "closed"})
    _issues_cache["ts"] = 0.0
    return {
        "number": issue_number,
        "comment_url": comment.get("html_url") if isinstance(comment, dict) else None,
        "closed": bool(receipt.get("close_issue")),
    }


def _latest_receipt(comments_url: str) -> dict | None:
    if not comments_url:
        return None
    req = urllib.request.Request(comments_url, headers=_github_headers())
    with urllib.request.urlopen(req, timeout=15) as resp:
        comments = json.loads(resp.read().decode("utf-8"))
    if not comments:
        return None
    receipts = [item for item in comments if RECEIPT_MARKER in str(item.get("body") or "")]
    item = receipts[-1] if receipts else comments[-1]
    body = str(item.get("body") or "")
    summary = _clean_text(body.replace(RECEIPT_MARKER, "").replace("### 修复回执", ""), MAX["summary"])
    kind = "comment"
    for line in body.splitlines():
        if line.startswith("**简要概括:**"):
            summary = line.removeprefix("**简要概括:**").strip()
            kind = "receipt"
            break
    if not summary:
        return None
    return {
        "summary": summary,
        "url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "kind": kind,
    }


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
    milestone = item.get("milestone") or {}
    receipt = None
    if int(item.get("comments") or 0) > 0:
        receipt = _latest_receipt(str(item.get("comments_url") or ""))
    return {
        "number": item.get("number"),
        "title": str(item.get("title") or "").removeprefix("[反馈] "),
        "state": item.get("state"),
        "url": item.get("html_url"),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "labels": [label.get("name") for label in item.get("labels", []) if label.get("name")],
        "comments": item.get("comments", 0),
        "milestone": milestone.get("title") if isinstance(milestone, dict) else None,
        "receipt": receipt,
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


def _admin_authorized(headers) -> bool:
    if not INTAKE_ADMIN_TOKEN:
        return False
    token = headers.get("X-Intake-Admin-Token", "").strip()
    auth = headers.get("Authorization", "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    return secrets.compare_digest(token, INTAKE_ADMIN_TOKEN)


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
        path = self.path.split("?")[0]
        if path == "/api/intake/receipts":
            if not _admin_authorized(self.headers):
                return self._json(403, {"error": "回执接口未授权"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length > 16 * 1024:
                    return self._json(413, {"error": "回执内容过大"})
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
                receipt = build_receipt(payload)
                if receipt is None:
                    return self._json(400, {"error": "issue_number、summary、repair、result 为必填"})
                return self._json(201, {"ok": True, **create_receipt(receipt)})
            except json.JSONDecodeError:
                return self._json(400, {"error": "JSON 格式错误"})
            except urllib.error.HTTPError as e:
                return self._json(502, {"error": f"GitHub 拒绝:{e.code}"})
            except Exception as e:  # noqa: BLE001
                self.log_error("receipt failed: %s", e)
                return self._json(500, {"error": "回执写入失败"})

        if path != "/api/intake":
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
