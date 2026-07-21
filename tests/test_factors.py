import pytest

from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr, evaluate
from src.utils.data_loader import build_panel


def test_baseline_factors_evaluate_non_empty():
    panel = build_panel(save=False)
    for expr in BASELINE_FACTORS:
        values = evaluate(expr, panel)
        assert not values.dropna().empty, expr.name


def test_expression_engine_rejects_arbitrary_code():
    panel = build_panel(save=False)
    expr = FactorExpr(
        name="bad",
        expression="__import__('os').system('echo nope')",
        economic_rationale="bad",
        fields_used=[],
    )
    with pytest.raises(ValueError):
        evaluate(expr, panel)


def test_safe_div_accepts_scalar_denominator():
    panel = build_panel(save=False)
    expr = FactorExpr(
        name="half_eps",
        expression="safe_div(eps, 2)",
        economic_rationale="test scalar denominator support",
        fields_used=["eps"],
    )

    values = evaluate(expr, panel)

    assert not values.dropna().empty
