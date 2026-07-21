from src.agents.loop import run_loop
from src.agents.validate import validate
from src.config import Config
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.utils.data_loader import build_panel


def test_validate_blocks_future_return_field():
    panel = build_panel(save=False)
    expr = FactorExpr("leaky", "rank(fwd_ret_5)", "uses label", ["fwd_ret_5"])
    ok, reason = validate(expr, set(panel.columns) | {"fwd_ret_5"}, panel=None)
    assert not ok
    assert "forbidden" in reason


def test_validate_blocks_negative_delay():
    panel = build_panel(save=False)
    expr = FactorExpr("leaky_delay", "rank(delay(close, -1))", "uses tomorrow close", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "future" in reason


def test_validate_reports_syntax_errors_without_panel():
    panel = build_panel(save=False)
    expr = FactorExpr("bad_syntax", "rank(close", "broken expression", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "syntax" in reason


def test_agent_loop_runs_one_round_and_writes_factors(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()
    client = LLMClient(cfg)
    results = run_loop(rounds=1, per_round=1, cfg=cfg, client=client)
    assert len(results) == 1
    assert list(cfg.factor_dir.glob("*.json"))
