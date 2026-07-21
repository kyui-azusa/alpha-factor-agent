import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("intake_service", ROOT / "platform" / "intake_service.py")
intake_service = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(intake_service)


class Headers(dict):
    def get(self, key, default=None):
        return super().get(key, default)


def test_build_receipt_formats_github_comment_and_parses_close_issue():
    receipt = intake_service.build_receipt(
        {
            "issue_number": "12",
            "fixed_by": "Codex",
            "summary": "已补充历史工单回执同步。",
            "repair": "新增受保护接口,向 GitHub issue 写入带标记的评论。",
            "result": "网站历史工单可展示最新回执摘要。",
            "close_issue": "false",
        }
    )

    assert receipt is not None
    assert receipt["issue_number"] == 12
    assert receipt["close_issue"] is False
    assert intake_service.RECEIPT_MARKER in receipt["body"]
    assert "### 修复回执" in receipt["body"]
    assert "**简要概括:** 已补充历史工单回执同步。" in receipt["body"]
    assert "**如何修复:**" in receipt["body"]
    assert "**修复结果:**" in receipt["body"]
    assert "处理人:Codex" in receipt["body"]


def test_build_receipt_rejects_invalid_payloads():
    assert intake_service.build_receipt({"issue_number": "0", "summary": "a", "repair": "b", "result": "c"}) is None
    assert intake_service.build_receipt({"issue_number": "abc", "summary": "a", "repair": "b", "result": "c"}) is None
    assert intake_service.build_receipt({"issue_number": "1", "summary": "a", "repair": "", "result": "c"}) is None


def test_admin_authorized_accepts_bearer_or_admin_header(monkeypatch):
    monkeypatch.setattr(intake_service, "INTAKE_ADMIN_TOKEN", "secret")

    assert intake_service._admin_authorized(Headers({"Authorization": "Bearer secret"}))
    assert intake_service._admin_authorized(Headers({"X-Intake-Admin-Token": "secret"}))
    assert not intake_service._admin_authorized(Headers({"Authorization": "Bearer wrong"}))

    monkeypatch.setattr(intake_service, "INTAKE_ADMIN_TOKEN", "")
    assert not intake_service._admin_authorized(Headers({"Authorization": "Bearer secret"}))


def test_compact_issue_includes_milestone_and_latest_receipt(monkeypatch):
    monkeypatch.setattr(
        intake_service,
        "_latest_receipt",
        lambda url: {"summary": "已修复并验证", "url": "https://github.test/comment", "created_at": "2026-07-22T00:00:00Z"},
    )

    compact = intake_service._compact_issue(
        {
            "number": 8,
            "title": "[反馈] 页面同步回执",
            "state": "open",
            "html_url": "https://github.test/issues/8",
            "created_at": "2026-07-22T00:00:00Z",
            "updated_at": "2026-07-22T00:01:00Z",
            "labels": [{"name": "intake"}, {"name": "功能"}],
            "comments": 1,
            "comments_url": "https://api.github.test/issues/8/comments",
            "milestone": {"title": "M2"},
        }
    )

    assert compact["title"] == "页面同步回执"
    assert compact["milestone"] == "M2"
    assert compact["receipt"]["summary"] == "已修复并验证"


def test_latest_receipt_falls_back_to_latest_plain_comment(monkeypatch):
    comments = [
        {
            "body": "线上截图上传自检通过,关闭测试 issue。",
            "html_url": "https://github.test/issues/3#issuecomment-1",
            "created_at": "2026-07-20T15:54:31Z",
        }
    ]

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(comments).encode("utf-8")

    monkeypatch.setattr(intake_service.urllib.request, "urlopen", lambda req, timeout=15: FakeResponse())

    receipt = intake_service._latest_receipt("https://api.github.test/issues/3/comments")

    assert receipt == {
        "summary": "线上截图上传自检通过,关闭测试 issue。",
        "url": "https://github.test/issues/3#issuecomment-1",
        "created_at": "2026-07-20T15:54:31Z",
        "kind": "comment",
    }


def test_create_receipt_posts_comment_and_optionally_closes_issue(monkeypatch):
    calls = []

    def fake_github_json(path, *, method="GET", payload=None):
        calls.append((path, method, payload))
        if path.endswith("/comments"):
            return {"html_url": "https://github.test/issues/3#issuecomment-1"}
        return {}

    monkeypatch.setattr(intake_service, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(intake_service, "GITHUB_REPO", "owner/repo")
    monkeypatch.setattr(intake_service, "_github_json", fake_github_json)
    intake_service._issues_cache.update({"ts": 123.0, "data": ["stale"]})

    result = intake_service.create_receipt({"issue_number": 3, "body": "body", "close_issue": True})

    assert result == {
        "number": 3,
        "comment_url": "https://github.test/issues/3#issuecomment-1",
        "closed": True,
    }
    assert calls == [
        ("/issues/3/comments", "POST", {"body": "body"}),
        ("/issues/3", "PATCH", {"state": "closed"}),
    ]
    assert intake_service._issues_cache["ts"] == 0.0


def test_create_receipt_dry_run_writes_log(tmp_path, monkeypatch):
    log_path = tmp_path / "dryrun.ndjson"
    monkeypatch.setattr(intake_service, "GITHUB_TOKEN", "")
    monkeypatch.setattr(intake_service, "GITHUB_REPO", "")
    monkeypatch.setattr(intake_service, "INTAKE_LOG", str(log_path))

    result = intake_service.create_receipt({"issue_number": 5, "body": "body", "close_issue": False})

    assert result == {"dry_run": True, "number": 5}
    row = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert row["receipt"]["issue_number"] == 5
