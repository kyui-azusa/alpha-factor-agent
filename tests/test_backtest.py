import json

import numpy as np
import pandas as pd
import pytest

from src.backtest.metrics import long_short_weights, rank_ic
from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr, evaluate
from src.utils.data_loader import build_panel, get_forward_returns, load_prices


def _small_cfg(tmp_path):
    return Config(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        start_date="2020-01-01",
        end_date="2021-12-31",
        train_end="2020-12-31",
    )


def _oos_orders(expr: FactorExpr, panel: pd.DataFrame, cfg: Config, n_quantiles: int = 3) -> list[tuple[pd.Timestamp, str, float]]:
    factor = evaluate(expr, panel)
    weights = long_short_weights(factor, n=n_quantiles)
    previous = pd.Series(dtype=float)
    orders: list[tuple[pd.Timestamp, str, float]] = []
    dates = pd.Index(weights.index.get_level_values("date").unique()).sort_values()
    for date in dates[dates > pd.Timestamp(cfg.train_end)]:
        target = weights.xs(date, level="date")
        universe = previous.index.union(target.index)
        submitted = target.reindex(universe, fill_value=0.0).sub(previous.reindex(universe, fill_value=0.0))
        for code, order in submitted.items():
            if abs(order) > 1e-12:
                orders.append((pd.Timestamp(date), str(code), float(order)))
        previous = target.loc[target.abs() > 1e-12]
    return orders


def test_future_return_sanity_check_has_rank_ic_one():
    idx = pd.MultiIndex.from_product([pd.date_range("2020-01-01", periods=4), list("ABC")], names=["date", "code"])
    fwd = pd.Series(np.tile([0.01, 0.02, 0.03], 4), index=idx, name="fwd_ret_1")
    ic = rank_ic(fwd, fwd)
    assert np.isclose(ic.mean(), 1.0)


def test_random_factor_rank_ic_near_zero():
    idx = pd.MultiIndex.from_product([pd.date_range("2020-01-01", periods=80), [f"S{i:02d}" for i in range(30)]], names=["date", "code"])
    rng = np.random.default_rng(3)
    factor = pd.Series(rng.normal(size=len(idx)), index=idx)
    fwd = pd.Series(rng.normal(size=len(idx)), index=idx)
    ic = rank_ic(factor, fwd)
    assert abs(ic.mean()) < 0.08


def test_backtest_baseline_writes_report(tmp_path):
    cfg = _small_cfg(tmp_path)
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=True)
    fwd = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))
    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)
    report_dir = to_report(result, tmp_path / "report")
    assert (report_dir / "report.json").exists()
    assert (report_dir / "factor_card.md").exists()
    assert (report_dir / "summary.png").exists()
    payload = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert payload["data"]["data_mode"] in {"synthetic", "mixed", "real"}
    assert payload["walk_forward"]["status"]
    assert "tradability" in payload
    assert "robustness" in payload
    assert "robustness_layers" in payload
    assert isinstance(payload["tradability"]["executable_long_short"], list)
    assert isinstance(payload["tradability"]["cost_ledger"], list)
    assert payload["tradability"]["cost_model_assumptions"]["stamp_duty_rule"]
    layers = payload["evaluation_layers"]
    assert set(layers) == {"factor_validity", "strategy_performance", "risk_exposure_independence"}
    assert layers["factor_validity"]["quantile_monotonicity"]
    strategy = layers["strategy_performance"]
    assert "executable_net_long_short_mean" in strategy
    assert "fill_rate_mean" in strategy
    assert "impact_cost_mean" in strategy
    assert "detailed_cost_total_mean" in strategy
    assert "impact_coverage_mean" in strategy
    assert strategy["cost_model_assumptions"]["portfolio_nav"] == 100_000_000.0
    risk = layers["risk_exposure_independence"]
    assert "market_regime_stability" in risk
    assert "style_stability" in risk
    assert "rebalance_frequency_stability" in risk
    card = (report_dir / "factor_card.md").read_text(encoding="utf-8")
    assert "## Factor Validity" in card
    assert "## Strategy Performance" in card
    assert "## Risk Exposure And Independence" in card
    assert "## Metrics" not in card
    assert "Robustness" in card
    assert result["summary"]["observations"] > 0


def test_backtest_includes_inference_walk_forward_and_tradability(tmp_path):
    cfg = _small_cfg(tmp_path)
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=False).copy()
    fwd = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))

    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)

    summary = result["summary"]
    assert summary["ic_count"] > 0
    assert "ic_t_stat" in summary
    assert "ic_pvalue_normal_approx" in summary
    assert result["data"]["oos_split"] == "date_ordered_train_end_exclusive"
    windows = result["walk_forward"]["windows"]
    assert [window["start_date"] for window in windows] == sorted(window["start_date"] for window in windows)
    assert all(pd.Timestamp(window["start_date"]) > pd.Timestamp(cfg.train_end) for window in windows)
    assert "amount_positive" in result["tradability"]["constraints"]
    assert "executable_net_long_short_mean" in result["tradability"]
    assert "fill_rate_mean" in result["tradability"]
    assert "impact_cost_mean" in result["tradability"]
    assert result["tradability"]["impact_coverage_mean"] > 0.0
    assert result["tradability"]["cost_component_means"]
    gross = result["tradability"]["executable_long_short"]
    net = result["tradability"]["executable_net_long_short"]
    ledger = result["tradability"]["cost_ledger"]
    assert np.allclose(net, gross - ledger["total_cost"])
    components = ledger[
        ["commission_cost", "stamp_duty_cost", "slippage_cost", "market_impact_cost", "short_borrow_cost"]
    ].sum(axis=1)
    assert np.allclose(ledger["total_cost"], components)
    assert {
        "directional_limit_checks",
        "shifted_adv_capacity",
        "partial_fills",
        "impact_cost",
    } <= set(result["tradability"]["order_constraints"])
    assert result["robustness"]["similarity_risk"] in {"low", "medium", "high", "unknown"}
    assert result["robustness"]["overfit_risk"] in {"low", "medium", "high", "unknown"}
    assert result["robustness"]["cost_sensitivity"] in {"low", "medium", "high", "unknown"}
    assert result["robustness"]["cost_grid_status"]
    assert any(row["cost_bps"] == 100.0 for row in result["robustness"]["cost_sensitivity_grid"])
    assert "cost_break_even_bps" in result["robustness"]
    assert result["robustness"]["horizon_sensitivity"]["usable_horizons"] >= 2
    assert {"fwd_ret_1", "fwd_ret_5", "fwd_ret_20"} <= {
        row["forward_column"] for row in result["robustness"]["horizon_sensitivity"]["windows"]
    }
    assert result["robustness"]["horizon_stability"] in {
        "stable_directional_horizons",
        "partially_stable_horizon_decay",
        "unstable_mixed_horizon_signs",
        "not_available_insufficient_horizons",
    }
    assert result["robustness"]["market_regime_stability"] in {
        "stable_directional_slices",
        "partially_stable_weak_slice",
        "unstable_mixed_signs",
        "insufficient_slices",
    }
    assert result["robustness"]["industry_stability"] != "not_tested_requires_industry_field"
    assert {"size", "liquidity"} <= set(result["robustness"]["style_stability"])
    assert result["robustness"]["rebalance_frequency_stability"] in {
        "stable_directional_slices",
        "partially_stable_weak_slice",
        "unstable_mixed_signs",
        "insufficient_slices",
    }
    assert {"market_regime", "industry", "style", "universe", "rebalance_frequency"} <= set(result["robustness_layers"])
    policy = result["data"]["robustness_policy"]
    assert policy["cost_bps_grid"] == [0.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0]
    assert policy["a_share_reality_checks"]["stamp_duty_sell_side_bps_reference"] == 10.0
    assert policy["a_share_reality_checks"]["missing_frictions"] == ["order_queue_priority"]
    assert {3, 5, 10} <= set(policy["n_quantiles_grid"])
    assert "rank" in policy["allowed_functions"]


def test_tradability_review_drops_zero_amount_oos_observations(tmp_path):
    cfg = _small_cfg(tmp_path)
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=False).copy()
    oos_index = panel.index[panel.index.get_level_values("date") > pd.Timestamp(cfg.train_end)]
    panel.loc[oos_index[:50], "amount"] = 0.0
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))

    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)

    assert result["tradability"]["dropped_observations"] > 0


def test_execution_review_blocks_directional_limit_orders(tmp_path):
    cfg = _small_cfg(tmp_path)
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=False).copy()
    panel["amount"] = 2_000_000_000.0
    buy_order = next(order for order in _oos_orders(BASELINE_FACTORS[0], panel, cfg) if order[2] > 0)
    sell_order = next(order for order in _oos_orders(BASELINE_FACTORS[0], panel, cfg) if order[2] < 0)
    panel.loc[(buy_order[0], buy_order[1]), "limit_up"] = True
    panel.loc[(sell_order[0], sell_order[1]), "limit_down"] = True
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))

    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)

    assert result["tradability"]["blocked_buy_notional"] > 0
    assert result["tradability"]["blocked_sell_notional"] > 0


def test_execution_review_caps_orders_by_shifted_adv_capacity(tmp_path):
    cfg = _small_cfg(tmp_path)
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=False).copy()
    panel["amount"] = 2_000_000_000.0
    date, code, _order = _oos_orders(BASELINE_FACTORS[0], panel, cfg)[0]
    panel.loc[(date, code), "amount"] = 2_000_000.0
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))

    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)

    assert result["tradability"]["partial_fill_notional"] > 0
    assert result["tradability"]["fill_rate_mean"] < 1.0


def test_backtest_does_not_need_llm(tmp_path):
    cfg = _small_cfg(tmp_path)
    expr = FactorExpr("simple", "rank(eps)", "test", ["eps"])
    panel = build_panel(cfg, save=False)
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))
    result = backtest(expr, panel, fwd, cfg=cfg, n_quantiles=3)
    assert "summary" in result


def test_backtest_rejects_unproven_fundamental_fields(tmp_path):
    cfg = _small_cfg(tmp_path)
    expr = FactorExpr("raw_quality", "rank(safe_div(net_income, total_equity))", "test", ["net_income", "total_equity"])
    panel = build_panel(cfg, save=False).copy()
    panel.attrs.clear()
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))

    with pytest.raises(ValueError, match="field availability"):
        backtest(expr, panel, fwd, cfg=cfg, n_quantiles=3)
