import pytest
from pathlib import Path

from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import MAX_TIME_WINDOW, FactorExpr, evaluate
from src.utils.data_loader import build_panel


def _small_panel():
    from src.config import Config

    cfg = Config(
        data_dir=Path("/tmp/alpha_factor_agent_pytest_synthetic"),
        start_date="2020-01-01",
        end_date="2020-09-30",
        train_end="2020-06-30",
    )
    return build_panel(cfg, save=False)


def test_baseline_factors_evaluate_non_empty():
    panel = _small_panel()
    for expr in BASELINE_FACTORS:
        values = evaluate(expr, panel)
        assert not values.dropna().empty, expr.name


def test_expression_engine_rejects_arbitrary_code():
    panel = _small_panel()
    expr = FactorExpr(
        name="bad",
        expression="__import__('os').system('echo nope')",
        economic_rationale="bad",
        fields_used=[],
    )
    with pytest.raises(ValueError):
        evaluate(expr, panel)


def test_safe_div_accepts_scalar_denominator():
    panel = _small_panel()
    expr = FactorExpr(
        name="half_eps",
        expression="safe_div(eps, 2)",
        economic_rationale="test scalar denominator support",
        fields_used=["eps"],
    )

    values = evaluate(expr, panel)

    assert not values.dropna().empty


def test_expression_engine_rejects_large_time_window():
    panel = _small_panel()
    expr = FactorExpr(
        name="too_long",
        expression=f"ts_mean(close, {MAX_TIME_WINDOW + 1})",
        economic_rationale="window too large",
        fields_used=["close"],
    )

    with pytest.raises(ValueError, match="too large"):
        evaluate(expr, panel)


def test_expression_engine_rejects_non_constant_time_window():
    panel = _small_panel()
    expr = FactorExpr(
        name="dynamic_window",
        expression="ts_mean(close, amount)",
        economic_rationale="dynamic window is unsafe",
        fields_used=["close", "amount"],
    )

    with pytest.raises(ValueError, match="numeric constant"):
        evaluate(expr, panel)


def test_expression_engine_rejects_deeply_nested_expression():
    panel = _small_panel()
    nested = "close"
    for _ in range(20):
        nested = f"rank({nested})"
    expr = FactorExpr(
        name="too_deep",
        expression=nested,
        economic_rationale="too deeply nested",
        fields_used=["close"],
    )

    with pytest.raises(ValueError, match="deeply nested|too complex"):
        evaluate(expr, panel)
