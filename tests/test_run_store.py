import pytest

from src.research.run_store import ERROR_CODES, ERROR_MESSAGES, InvalidRunTransition, RunStore


def _advance_to(store: RunStore, run_id: str, target: str) -> None:
    states = [
        "preflight_running",
        "awaiting_confirmation",
        "queued",
        "generating",
        "validating",
        "backtesting",
        "summarizing",
    ]
    for state in states:
        store.transition(run_id, state, output_artifacts={"finished": state})
        if state == target:
            return


def test_run_state_survives_store_restart_and_preserves_stage_artifacts(tmp_path):
    path = tmp_path / "research-runs.sqlite3"
    store = RunStore(path)
    store.create_run("request_1", {"contract": "abc"}, run_id="run_1")
    store.transition("run_1", "preflight_running", output_artifacts={"draft": "saved"})

    reopened = RunStore(path)
    run = reopened.get_run("run_1")

    assert run["status"] == "preflight_running"
    assert run["artifacts"]["draft"] == {"draft": "saved"}
    assert reopened.list_runs(request_id="request_1")[0]["run_id"] == "run_1"


def test_state_machine_rejects_skips_and_canceled_run_cannot_start_work(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run("request_1", {}, run_id="run_1")

    with pytest.raises(InvalidRunTransition, match="draft -> completed"):
        store.transition("run_1", "completed")

    canceled = store.cancel_run("run_1")
    assert canceled["status"] == "canceled"
    assert canceled["incomplete"] is True
    with pytest.raises(InvalidRunTransition):
        store.transition("run_1", "preflight_running")
    with pytest.raises(InvalidRunTransition):
        store.upsert_candidate("run_1", "candidate_1", "running")


def test_retry_is_idempotent_and_changed_inputs_create_child_run(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run("request_1", {"dataset": "v1"}, run_id="run_1")
    _advance_to(store, "run_1", "validating")
    store.fail_run("run_1", "expression_rejected", "unknown field")

    first = store.retry_failed("run_1", idempotency_key="retry-same")
    replay = store.retry_failed("run_1", idempotency_key="retry-same")
    assert first.run_id == "run_1"
    assert replay.run_id == "run_1"
    assert replay.idempotent_replay is True
    assert store.get_run("run_1")["retry_count"] == 1
    assert [item["attempt"] for item in store.stage_attempts("run_1") if item["stage"] == "validation"] == [1, 2]
    with pytest.raises(ValueError, match="different retry inputs"):
        store.retry_failed("run_1", idempotency_key="retry-same", inputs={"dataset": "v2"})

    store.fail_run("run_1", "expression_rejected", "still invalid")
    child = store.retry_failed("run_1", idempotency_key="retry-new-input", inputs={"dataset": "v2"})
    assert child.created_child is True
    assert child.run_id != "run_1"
    assert child.resumed_stage == "draft"
    assert store.get_run(child.run_id)["parent_run_id"] == "run_1"
    assert store.get_run(child.run_id)["status"] == "draft"
    assert store.get_run(child.run_id)["artifacts"] == {}
    assert store.get_run("run_1")["inputs"] == {"dataset": "v1"}


def test_candidate_failure_allows_partial_completion(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run("request_1", {}, run_id="run_1")
    _advance_to(store, "run_1", "summarizing")
    store.upsert_candidate("run_1", "candidate_ok", "completed", artifact={"report": "ok.json"})
    store.upsert_candidate(
        "run_1",
        "candidate_bad",
        "failed",
        error_code="timeout",
        message="candidate backtest timed out",
    )

    run = store.finalize_from_candidates("run_1")

    assert run["status"] == "partial_completed"
    assert run["incomplete"] is True
    assert {item["status"] for item in store.list_candidates("run_1")} == {"completed", "failed"}


def test_stable_error_codes_distinguish_failure_classes(tmp_path):
    assert {"timeout", "data_error", "expression_rejected", "system_error"} <= ERROR_CODES
    assert set(ERROR_MESSAGES) == ERROR_CODES
    store = RunStore(tmp_path / "runs.sqlite3")
    store.create_run("request_1", {}, run_id="run_1")
    failed = store.fail_run("run_1", "pit_error", "ann_date exceeds factor date")
    assert failed["error_code"] == "pit_error"
    with pytest.raises(ValueError, match="unsupported error code"):
        store.create_run("request_2", {}, run_id="run_2")
        store.fail_run("run_2", "misc", "not stable")
