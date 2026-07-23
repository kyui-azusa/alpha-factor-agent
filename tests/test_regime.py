import pandas as pd
import pytest

from src.config import Config
from src.factors.engine import FactorExpr, evaluate
from src.factors.regime import market_regime_by_date
from src.utils.data_loader import attach_market_regimes, build_panel
from src.utils.field_availability import validate_field_availability


def _panel():
    return build_panel(
        Config(start_date="2020-01-01", end_date="2020-09-30", train_end="2020-06-30"),
        save=False,
    )


def test_market_regime_is_invariant_to_future_price_changes():
    panel = _panel()
    cutoff = pd.Timestamp("2020-06-30")
    changed = panel.drop(columns=[field for field in panel.columns if field.startswith("regime_") or field.startswith("market_")])
    changed = changed.copy()
    future = changed.index.get_level_values("date") > cutoff
    changed.loc[future, "close"] = changed.loc[future, "close"] * 100.0

    original_regime = market_regime_by_date(panel)
    changed_regime = market_regime_by_date(changed)

    pd.testing.assert_frame_equal(original_regime.loc[:cutoff], changed_regime.loc[:cutoff])


def test_market_regime_on_t_does_not_use_t_return():
    panel = _panel()
    raw = panel.drop(columns=[field for field in panel.columns if field.startswith("regime_") or field.startswith("market_")])
    event_date = pd.Timestamp("2020-05-15")
    changed = raw.copy()
    changed.loc[changed.index.get_level_values("date") == event_date, "close"] *= 50.0

    original = market_regime_by_date(raw)
    shocked = market_regime_by_date(changed)

    pd.testing.assert_series_equal(original.loc[event_date], shocked.loc[event_date])


def test_where_selects_fixed_branch_from_binary_regime():
    panel = _panel()
    expr = FactorExpr(
        "conditional_value",
        "where(regime_bull, rank(eps), -rank(eps))",
        "switch a fixed value signal direction by lagged market state",
        ["regime_bull", "eps"],
    )

    values = evaluate(expr, panel)
    ranked = evaluate(FactorExpr("ranked_eps", "rank(eps)", "control", ["eps"]), panel)
    usable = panel["regime_bull"].notna() & ranked.notna()
    bull = usable & panel["regime_bull"].eq(1)
    bear = usable & panel["regime_bull"].eq(0)

    assert bull.any() and bear.any()
    pd.testing.assert_series_equal(values[bull], ranked[bull], check_names=False)
    pd.testing.assert_series_equal(values[bear], -ranked[bear], check_names=False)


def test_where_rejects_non_binary_condition_and_comparisons():
    panel = _panel()
    non_binary = FactorExpr("bad_condition", "where(close, eps, 0)", "unsafe condition", ["close", "eps"])
    comparison = FactorExpr(
        "inline_comparison",
        "where(close > delay(close, 1), eps, 0)",
        "comparison is outside the whitelist",
        ["close", "eps"],
    )

    with pytest.raises(ValueError, match="registered regime_"):
        evaluate(non_binary, panel)
    with pytest.raises(ValueError, match="Unsupported expression syntax"):
        evaluate(comparison, panel)


def test_attached_regimes_have_recursive_pit_metadata():
    panel = _panel()
    raw = panel.drop(columns=[field for field in panel.columns if field.startswith("regime_") or field.startswith("market_")])
    attached = attach_market_regimes(raw)

    ok, reason = validate_field_availability({"regime_bull", "regime_high_vol"}, attached)

    assert ok, reason
