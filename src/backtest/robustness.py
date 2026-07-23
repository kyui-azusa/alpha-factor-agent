from __future__ import annotations

from typing import Any

import pandas as pd

from src.factors.engine import FACTOR_FUNCTIONS, MAX_AST_DEPTH, MAX_AST_NODES, MAX_TIME_WINDOW


COST_BPS_GRID = [0.0, 5.0, 10.0, 20.0, 30.0, 50.0, 100.0]
FORWARD_COLUMN_GRID = ["fwd_ret_1", "fwd_ret_5", "fwd_ret_20"]


def robustness_policy(cost_bps: float, n_quantiles: int, forward_column: str) -> dict[str, Any]:
    return {
        "default_cost_bps": cost_bps,
        "default_n_quantiles": n_quantiles,
        "default_forward_column": forward_column,
        "cost_convention": "net_long_short = long_short - turnover * cost_bps / 10000; cost_bps is a scenario parameter, not a full broker-fee, tax, or market-impact model.",
        "cost_bps_grid": COST_BPS_GRID,
        "a_share_reality_checks": {
            "stamp_duty_sell_side_bps_reference": 100.0,
            "high_cost_scenarios_included": True,
            "missing_frictions": ["market_impact", "borrow_cost", "slippage", "order_queue_priority"],
        },
        "n_quantiles_grid": [3, 5, 10],
        "forward_column_grid": FORWARD_COLUMN_GRID,
        "expression_limits": {
            "max_ast_nodes": MAX_AST_NODES,
            "max_ast_depth": MAX_AST_DEPTH,
            "max_time_window": MAX_TIME_WINDOW,
        },
        "allowed_functions": sorted(FACTOR_FUNCTIONS),
        "note": "This deterministic policy declares robustness dimensions to sweep outside the LLM path; high-cost A-share scenarios should be read as sensitivity checks until a richer execution-cost model is added.",
    }


def _risk_level(value: float, low: float, high: float) -> str:
    if pd.isna(value):
        return "unknown"
    if value >= high:
        return "high"
    if value >= low:
        return "medium"
    return "low"


def _walk_forward_risk(walk_forward: dict[str, Any]) -> str:
    usable = walk_forward.get("usable_windows", 0)
    if usable < 2:
        return "unknown"
    positive = walk_forward.get("positive_ic_windows", 0)
    negative = walk_forward.get("negative_ic_windows", 0)
    dominant = max(positive, negative) / usable if usable else 0.0
    if dominant >= 0.8:
        return "low"
    if dominant >= 0.6:
        return "medium"
    return "high"


def _cost_sensitivity(summary: dict[str, Any], turnover_mean: float | None = None) -> str:
    gross = summary.get("long_short_mean")
    net = summary.get("net_long_short_mean")
    turnover_value = summary.get("turnover_mean") if turnover_mean is None else turnover_mean
    if pd.isna(gross) or pd.isna(net):
        return "unknown"
    gross = float(gross)
    net = float(net)
    turnover_value = float(turnover_value or 0.0)
    if abs(gross) > 0 and net * gross <= 0:
        return "high"
    drag_ratio = abs(gross - net) / max(abs(gross), 1e-12)
    if drag_ratio >= 0.5 or turnover_value >= 1.5:
        return "high"
    if drag_ratio >= 0.2 or turnover_value >= 0.8:
        return "medium"
    return "low"


def cost_sensitivity_grid(summary: dict[str, Any], cost_bps_grid: list[float] | None = None) -> dict[str, Any]:
    gross = summary.get("long_short_mean")
    turnover = summary.get("turnover_mean")
    grid = COST_BPS_GRID if cost_bps_grid is None else cost_bps_grid
    if pd.isna(gross) or pd.isna(turnover):
        return {"status": "not_available", "scenarios": [], "break_even_cost_bps": float("nan")}
    gross = float(gross)
    turnover = float(turnover or 0.0)
    scenarios = [
        {
            "cost_bps": float(cost_bps),
            "net_long_short_mean": float(gross - turnover * float(cost_bps) / 10000.0),
        }
        for cost_bps in grid
    ]
    if turnover <= 0:
        break_even = float("inf") if gross > 0 else float("nan")
    else:
        break_even = float(gross * 10000.0 / turnover)
    positive = [item for item in scenarios if item["net_long_short_mean"] > 0]
    status = "positive_all_scenarios" if len(positive) == len(scenarios) else "cost_sensitive"
    if not positive:
        status = "non_positive_all_scenarios"
    return {"status": status, "scenarios": scenarios, "break_even_cost_bps": break_even}


def _horizon_stability(horizon_sensitivity: dict[str, Any] | None) -> str:
    if not isinstance(horizon_sensitivity, dict):
        return "not_tested_requires_forward_column_grid_run"
    rows = horizon_sensitivity.get("windows", [])
    usable = [row for row in rows if not pd.isna(row.get("ic_mean"))]
    if len(usable) < 2:
        return "not_available_insufficient_horizons"
    signs = {1 if row["ic_mean"] > 0 else -1 if row["ic_mean"] < 0 else 0 for row in usable}
    if len(signs - {0}) > 1:
        return "unstable_mixed_horizon_signs"
    magnitudes = [abs(float(row["ic_mean"])) for row in usable]
    if min(magnitudes) < max(magnitudes) * 0.25:
        return "partially_stable_horizon_decay"
    return "stable_directional_horizons"


def regime_split_summary(rank_ic_series: pd.Series) -> dict[str, Any]:
    clean = rank_ic_series.dropna().sort_index()
    if clean.empty:
        return {"status": "insufficient_data", "windows": []}
    midpoint = len(clean) // 2
    chunks = [("early_oos", clean.iloc[:midpoint]), ("late_oos", clean.iloc[midpoint:])] if midpoint else [("all_oos", clean)]
    windows = [
        {
            "label": label,
            "ic_mean": float(chunk.mean()) if not chunk.empty else float("nan"),
            "ic_count": int(chunk.shape[0]),
        }
        for label, chunk in chunks
        if not chunk.empty
    ]
    signs = {1 if item["ic_mean"] > 0 else -1 if item["ic_mean"] < 0 else 0 for item in windows}
    if len(windows) < 2:
        status = "insufficient_regime_slices"
    elif len(signs - {0}) > 1:
        status = "regime_dependent"
    else:
        status = "directionally_stable"
    return {"status": status, "windows": windows}


def robustness_summary(
    *,
    summary: dict[str, Any],
    train_summary: dict[str, Any],
    walk_forward: dict[str, Any],
    tradability: dict[str, Any],
    rank_ic_series: pd.Series,
    novelty: dict[str, Any] | None = None,
    horizon_sensitivity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    novelty = novelty or {}
    max_corr = float(novelty.get("max_abs_existing_corr", 0.0) or 0.0)
    train_ic = train_summary.get("ic_mean")
    oos_ic = summary.get("ic_mean")
    if pd.isna(train_ic) or pd.isna(oos_ic):
        overfit_risk = "unknown"
    else:
        train_ic = float(train_ic)
        oos_ic = float(oos_ic)
        if train_ic * oos_ic < 0 or abs(oos_ic) < abs(train_ic) * 0.25:
            overfit_risk = "high"
        elif abs(oos_ic) < abs(train_ic) * 0.5:
            overfit_risk = "medium"
        else:
            overfit_risk = "low"
    regime = regime_split_summary(rank_ic_series)
    cost = _cost_sensitivity(summary)
    cost_grid = cost_sensitivity_grid(summary)
    tradable_net = tradability.get("tradable_net_long_short_mean") if isinstance(tradability, dict) else None
    if tradable_net is not None and not pd.isna(tradable_net) and not pd.isna(summary.get("net_long_short_mean")):
        ideal = float(summary.get("net_long_short_mean"))
        tradable = float(tradable_net)
        if ideal * tradable <= 0 and abs(ideal) > 0:
            cost = "high"
    report = {
        "similarity_risk": _risk_level(max_corr, 0.65, 0.90),
        "nearest_factor": novelty.get("nearest_factor"),
        "max_abs_existing_corr": max_corr,
        "overfit_risk": overfit_risk,
        "walk_forward_stability": _walk_forward_risk(walk_forward),
        "regime_dependency": regime["status"],
        "regime_slices": regime["windows"],
        "universe_stability": "not_tested_requires_multiple_universes",
        "industry_stability": "not_tested_requires_industry_field",
        "horizon_stability": _horizon_stability(horizon_sensitivity),
        "horizon_sensitivity": horizon_sensitivity or {"status": "not_tested_requires_forward_column_grid_run", "windows": []},
        "cost_sensitivity": cost,
        "cost_sensitivity_grid": cost_grid["scenarios"],
        "cost_grid_status": cost_grid["status"],
        "cost_break_even_bps": cost_grid["break_even_cost_bps"],
    }
    report["robustness_summary"] = (
        f"similarity={report['similarity_risk']}; overfit={report['overfit_risk']}; "
        f"walk_forward={report['walk_forward_stability']}; regime={report['regime_dependency']}; cost={report['cost_sensitivity']}"
    )
    return report
