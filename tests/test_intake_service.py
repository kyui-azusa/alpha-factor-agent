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


def test_parse_related_issues_normalizes_free_text():
    # 表单让人随手填,`#12`/`12`/中英逗号都要认;去重、保序、限量
    assert intake_service.parse_related_issues("#12, 15") == [12, 15]
    assert intake_service.parse_related_issues("12 12 #15") == [12, 15]
    assert intake_service.parse_related_issues("#1 #2 #3 #4 #5 #6") == [1, 2, 3, 4, 5]
    assert intake_service.parse_related_issues("0 无 issue") == []
    assert intake_service.parse_related_issues("") == []


def test_build_issue_writes_related_issues_as_github_references():
    payload = intake_service.build_issue(
        {
            "submitter": ["阿祖"],
            "title": ["回测报告缺换手率"],
            "description": ["和 #12 是同一处"],
            "type": ["缺陷"],
            "priority": ["高"],
            "related_issues": ["#12, 12 15"],
        }
    )

    assert payload is not None
    # 写成 #N 才能让 GitHub 自动建交叉引用 —— 被引用的工单时间线上会出现 mention
    assert "**关联工单:** #12 #15" in payload["body"]
    assert payload["labels"] == ["intake", "缺陷", "P:高"]


def test_build_issue_omits_related_line_when_no_valid_number():
    payload = intake_service.build_issue(
        {
            "submitter": ["阿祖"],
            "title": ["标题"],
            "description": ["描述"],
            "related_issues": ["无"],
        }
    )

    assert payload is not None
    assert "关联工单" not in payload["body"]


def test_build_issue_marks_needs_review_in_label_and_body():
    payload = intake_service.build_issue(
        {
            "submitter": ["阿祖"],
            "title": ["和 AI 讨论出来的猜想"],
            "description": ["还没验证"],
            "type": ["建议"],
            "needs_review": ["1"],
        }
    )

    assert payload is not None
    assert intake_service.REVIEW_LABEL in payload["labels"]
    # 标签会被人在 GitHub 上摘掉,正文那句声明不会
    assert f"**{intake_service.REVIEW_LABEL}:**" in payload["body"]


def test_build_issue_without_needs_review_stays_clean():
    payload = intake_service.build_issue(
        {"submitter": ["阿祖"], "title": ["标题"], "description": ["描述"], "needs_review": [""]}
    )

    assert payload is not None
    assert intake_service.REVIEW_LABEL not in payload["labels"]
    assert intake_service.REVIEW_LABEL not in payload["body"]


def test_compact_issue_exposes_submitter_and_review_flag_for_filtering():
    body = "**提交人:** 阿祖\n**类型:** 建议　**优先级:** 中\n\n---\n\n正文"
    compact = intake_service._compact_issue(
        {"number": 7, "title": "[反馈] 标题", "state": "open", "labels": [{"name": "intake"}], "body": body}
    )

    assert compact["submitter"] == "阿祖"
    assert compact["needs_review"] is False

    # 标签被摘掉也仍算待审核 —— 正文里的声明是准的
    flagged = intake_service._compact_issue(
        {"number": 8, "title": "[反馈] 标题", "state": "open", "labels": [],
         "body": body + f"\n**{intake_service.REVIEW_LABEL}:** 内容未经证实"}
    )
    assert flagged["needs_review"] is True
    assert intake_service._compact_issue({"number": 9, "body": ""})["submitter"] == ""


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


def test_compact_issue_includes_milestone_and_latest_receipt():
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
        },
        {"summary": "已修复并验证", "url": "https://github.test/comment", "created_at": "2026-07-22T00:00:00Z", "kind": "receipt"},
    )

    assert compact["title"] == "页面同步回执"
    assert compact["milestone"] == "M2"
    assert compact["receipt"]["summary"] == "已修复并验证"


def test_receipt_from_comment_falls_back_to_plain_comment_text():
    receipt = intake_service._receipt_from_comment(
        {
            "body": "线上截图上传自检通过,关闭测试 issue。",
            "html_url": "https://github.test/issues/3#issuecomment-1",
            "created_at": "2026-07-20T15:54:31Z",
        }
    )

    assert receipt == {
        "summary": "线上截图上传自检通过,关闭测试 issue。",
        "url": "https://github.test/issues/3#issuecomment-1",
        "created_at": "2026-07-20T15:54:31Z",
        "kind": "comment",
    }


def test_latest_receipts_picks_newest_per_issue_in_one_pass(monkeypatch):
    # 仓库级评论接口:时间倒序,同一条工单第一次遇到的就是最新的;回执优先于普通评论
    comments = [
        {"issue_url": "https://api.github.test/repos/o/r/issues/8", "body": "随口一句最新评论",
         "html_url": "https://github.test/8#c3", "created_at": "2026-07-22T03:00:00Z"},
        {"issue_url": "https://api.github.test/repos/o/r/issues/8",
         "body": intake_service.RECEIPT_MARKER + "\n### 修复回执\n\n**简要概括:** 第二版回执",
         "html_url": "https://github.test/8#c2", "created_at": "2026-07-22T02:00:00Z"},
        {"issue_url": "https://api.github.test/repos/o/r/issues/8",
         "body": intake_service.RECEIPT_MARKER + "\n### 修复回执\n\n**简要概括:** 第一版回执",
         "html_url": "https://github.test/8#c1", "created_at": "2026-07-22T01:00:00Z"},
        {"issue_url": "https://api.github.test/repos/o/r/issues/99", "body": "别的工单,不在名单里",
         "html_url": "https://github.test/99#c1", "created_at": "2026-07-22T04:00:00Z"},
    ]
    calls = []

    def fake_github_json(path, *, method="GET", payload=None):
        calls.append(path)
        return comments

    monkeypatch.setattr(intake_service, "GITHUB_REPO", "o/r")
    monkeypatch.setattr(intake_service, "_github_json", fake_github_json)

    receipts = intake_service._latest_receipts({8, 12})

    assert set(receipts) == {8}
    assert receipts[8]["summary"] == "第二版回执"      # 比普通评论旧,但回执优先
    assert receipts[8]["kind"] == "receipt"
    assert len(calls) == 1                             # 一次请求覆盖所有工单,不再每条一发


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
