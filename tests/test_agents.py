from pathlib import Path

from src.agents.feedback import feedback_summary
from src.agents.generate import propose_factors
from src.agents.json_utils import factor_from_json
from src.agents.knowledge import generation_context, seed_factor_lineage
from src.agents.loop import run_loop
from src.agents.validate import validate
from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import MAX_TIME_WINDOW
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.utils.data_loader import build_panel


def _small_cfg(**overrides):
    values = {
        "data_dir": Path("/tmp/alpha_factor_agent_pytest_synthetic"),
        "start_date": "2020-01-01",
        "end_date": "2020-09-30",
        "train_end": "2020-06-30",
    }
    values.update(overrides)
    return Config(**values)


def _small_panel():
    return build_panel(_small_cfg(), save=False)


def test_factor_from_json_preserves_metadata_and_extra_keys():
    expr = factor_from_json(
        {
            "name": "cashflow_yield",
            "expression": "rank(safe_div(operating_cash_flow, mktcap))",
            "formula": "OCF / market cap",
            "economic_rationale": "cash flow yield",
            "fields_used": ["operating_cash_flow", "mktcap"],
            "metadata": {"category": "cashflow_value"},
            "alpha_target": "explainable value alpha",
        }
    )

    assert expr.formula == "OCF / market cap"
    assert expr.metadata["category"] == "cashflow_value"
    assert expr.metadata["alpha_target"] == "explainable value alpha"


def test_generation_context_contains_seed_catalog_and_no_raw_arrays():
    panel = _small_panel()
    context = generation_context(panel)

    assert context["seed_factors"]
    assert context["seed_factor_lineage"] == seed_factor_lineage()
    assert {item["name"] for item in context["synthesis_methods"]} >= {"complementary_blend", "risk_adjustment"}
    assert {item["field"] for item in context["field_catalog"]} >= {"close", "eps", "operating_cash_flow"}
    assert any(item["missing_policy"] for item in context["field_catalog"])
    assert "raw_values" not in context
    assert "rows" not in context


def test_propose_factors_records_generation_params(tmp_path):
    cfg = Config(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        llm_backend="mock",
        llm_temperature=0.7,
    )
    cfg.ensure_dirs()
    client = LLMClient(cfg)

    factors = propose_factors([factor.to_dict() for factor in BASELINE_FACTORS], {"field_catalog": []}, n=1, client=client)

    params = factors[0].metadata["generation"]["params"]
    assert params["temperature"] == 0.7
    assert params["max_tokens"] == cfg.llm_max_tokens
    assert factors[0].metadata["generation"]["proposal_rank"] == 1
    assert factors[0].metadata["generation"]["generated_at_utc"]
    assert "source_seed_factors" in factors[0].metadata
    assert "synthesis_method" in factors[0].metadata
    assert "lineage" in factors[0].metadata


def test_feedback_summary_only_exposes_train_segment():
    payload = {
        "train_summary": {"segment": "train", "ic_mean": 0.03, "net_long_short_mean": 0.001, "observations": 120},
        "summary": {"segment": "oos", "ic_mean": -0.2, "net_long_short_mean": -0.01},
        "walk_forward": {"status": "mixed_regime_ic"},
        "tradability": {"dropped_observations": 10},
        "data": {"data_mode": "synthetic"},
    }

    summary = feedback_summary(payload)

    assert summary["segment"] == "train"
    assert summary["ic_mean"] == 0.03
    assert summary["feedback_data_boundary"] == "train_segment_only_no_oos_metrics"
    assert "walk_forward" not in summary
    assert "tradability" not in summary
    assert "data" not in summary


def test_validate_blocks_future_return_field():
    panel = _small_panel()
    expr = FactorExpr("leaky", "rank(fwd_ret_5)", "uses label", ["fwd_ret_5"])
    ok, reason = validate(expr, set(panel.columns) | {"fwd_ret_5"}, panel=None)
    assert not ok
    assert "forbidden" in reason


def test_validate_blocks_negative_delay():
    panel = _small_panel()
    expr = FactorExpr("leaky_delay", "rank(delay(close, -1))", "uses tomorrow close", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "future" in reason


def test_validate_reports_syntax_errors_without_panel():
    panel = _small_panel()
    expr = FactorExpr("bad_syntax", "rank(close", "broken expression", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "syntax" in reason


def test_validate_rejects_oversized_time_window():
    panel = _small_panel()
    expr = FactorExpr("too_long", f"rank(ts_mean(close, {MAX_TIME_WINDOW + 1}))", "too long", ["close"])

    ok, reason = validate(expr, set(panel.columns), panel=None)

    assert not ok
    assert "exceeds max" in reason


def test_validate_rejects_non_constant_time_window():
    panel = _small_panel()
    expr = FactorExpr("dynamic", "rank(ts_mean(close, amount))", "dynamic window", ["close", "amount"])

    ok, reason = validate(expr, set(panel.columns), panel=None)

    assert not ok
    assert "numeric constant" in reason


def test_validate_rejects_duplicate_expression_by_fingerprint():
    panel = _small_panel()
    expr = FactorExpr("copy", BASELINE_FACTORS[0].expression, "copy", BASELINE_FACTORS[0].fields_used)

    ok, reason = validate(expr, set(panel.columns), panel=panel, existing_factors=[BASELINE_FACTORS[0]], client=LLMClient())

    assert not ok
    assert "deterministic duplicate" in reason


def test_agent_loop_runs_one_round_and_writes_factors(tmp_path):
    cfg = _small_cfg(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()
    client = LLMClient(cfg)
    results = run_loop(rounds=1, per_round=1, cfg=cfg, client=client)
    assert len(results) == 1
    assert list(cfg.factor_dir.glob("*.json"))
