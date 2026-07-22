from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.metrics import ic_ir, long_short_return, long_short_weights, quantile_returns, rank_ic, turnover
from src.backtest.robustness import FORWARD_COLUMN_GRID, robustness_policy, robustness_summary
from src.config import CONFIG, Config
from src.factors.engine import FactorExpr, evaluate, expression_names
from src.utils.field_availability import validate_field_availability


RAW_TABLES = ("prices", "fundamentals", "universe")
ADV_WINDOW = 20
ADV_MIN_PERIODS = 1
MIN_ADV_NOTIONAL = 1_000_000.0
PORTFOLIO_VALUE = 100_000_000.0
MAX_PARTICIPATION_RATE = 0.10
IMPACT_BPS_PER_10PCT_ADV = 5.0


def _ic_inference(ic: pd.Series) -> dict:
    clean = ic.dropna()
    count = int(clean.shape[0])
    std = float(clean.std(ddof=1)) if count > 1 else float("nan")
    mean = float(clean.mean()) if count else float("nan")
    if count > 1 and not pd.isna(std) and std > 0:
        stderr = std / math.sqrt(count)
        t_stat = mean / stderr
        pvalue = math.erfc(abs(t_stat) / math.sqrt(2.0))
    else:
        stderr = float("nan")
        t_stat = float("nan")
        pvalue = float("nan")
    return {
        "ic_count": count,
        "ic_std": std,
        "ic_stderr": float(stderr),
        "ic_t_stat": float(t_stat),
        "ic_pvalue_normal_approx": float(pvalue),
        "ic_inference_note": "ICIR is descriptive; t-stat and p-value use a normal approximation and should be read with walk-forward stability.",
    }


def _metrics_for_slice(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    segment: str,
) -> dict:
    ic = rank_ic(factor, returns)
    qret = quantile_returns(factor, returns, n=n_quantiles)
    ls = long_short_return(qret)
    turn = turnover(factor, n=n_quantiles).reindex(ls.index).fillna(0.0)
    net = ls - turn * (cfg.cost_bps / 10000.0)
    net.name = "net_long_short"

    sel_dates = factor.index.get_level_values("date")
    observations = int(pd.concat([factor.rename("factor"), returns.rename("fwd_ret")], axis=1).dropna().shape[0])
    summary = {
        "name": name,
        "segment": segment,
        "start_date": str(sel_dates.min().date()) if len(factor) else None,
        "end_date": str(sel_dates.max().date()) if len(factor) else None,
        "train_end": cfg.train_end,
        "ic_mean": float(ic.mean()) if not ic.empty else float("nan"),
        "ic_ir": ic_ir(ic),
        "long_short_mean": float(ls.mean()) if not ls.empty else float("nan"),
        "turnover_mean": float(turn.mean()) if not turn.empty else float("nan"),
        "net_long_short_mean": float(net.mean()) if not net.empty else float("nan"),
        "observations": observations,
        "cost_bps": cfg.cost_bps,
    }
    summary.update(_ic_inference(ic))
    return {
        "summary": summary,
        "rank_ic": ic,
        "quantile_returns": qret,
        "long_short": ls,
        "turnover": turn,
        "net_long_short": net,
    }


def _segment_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    segment: str,
) -> dict:
    factor_dates = factor.index.get_level_values("date")
    return_dates = returns.index.get_level_values("date")
    if segment == "train":
        sel_factor = factor.loc[factor_dates <= train_end]
        sel_returns = returns.loc[return_dates <= train_end]
    else:
        sel_factor = factor.loc[factor_dates > train_end]
        sel_returns = returns.loc[return_dates > train_end]
    return _metrics_for_slice(name, sel_factor, sel_returns, cfg, n_quantiles, train_end, segment)


def _walk_forward_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    *,
    window_days: int = 63,
    step_days: int = 63,
) -> dict:
    dates = pd.Index(factor.index.get_level_values("date").unique()).sort_values()
    oos_dates = dates[dates > train_end]
    windows: list[dict] = []
    for start_idx in range(0, len(oos_dates), step_days):
        window_dates = oos_dates[start_idx : start_idx + window_days]
        if len(window_dates) < max(5, min(window_days, 20)):
            continue
        start = window_dates[0]
        end = window_dates[-1]
        factor_dates = factor.index.get_level_values("date")
        return_dates = returns.index.get_level_values("date")
        sel_factor = factor.loc[(factor_dates >= start) & (factor_dates <= end)]
        sel_returns = returns.loc[(return_dates >= start) & (return_dates <= end)]
        window = _metrics_for_slice(name, sel_factor, sel_returns, cfg, n_quantiles, train_end, "walk_forward")["summary"]
        window["window_index"] = len(windows)
        windows.append(window)

    usable = [window for window in windows if not pd.isna(window.get("ic_mean"))]
    positive = sum(1 for window in usable if window.get("ic_mean", 0.0) > 0)
    negative = sum(1 for window in usable if window.get("ic_mean", 0.0) < 0)
    if len(usable) < 2:
        status = "insufficient_oos_windows"
    elif positive == len(usable):
        status = "consistent_positive_ic"
    elif negative == len(usable):
        status = "consistent_negative_ic"
    else:
        status = "mixed_regime_ic"
    return {
        "window_days": window_days,
        "step_days": step_days,
        "status": status,
        "windows": windows,
        "positive_ic_windows": positive,
        "negative_ic_windows": negative,
        "usable_windows": len(usable),
    }


def _horizon_sensitivity_metrics(
    name: str,
    factor: pd.Series,
    fwd_ret: pd.DataFrame | pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    default_forward_column: str,
) -> dict:
    if not isinstance(fwd_ret, pd.DataFrame):
        return {
            "status": "not_tested_requires_forward_return_dataframe",
            "windows": [],
            "missing_forward_columns": FORWARD_COLUMN_GRID,
        }

    windows: list[dict] = []
    missing: list[str] = []
    for column in FORWARD_COLUMN_GRID:
        if column not in fwd_ret.columns:
            missing.append(column)
            continue
        returns = fwd_ret[column].sort_index()
        summary = _segment_metrics(name, factor, returns, cfg, n_quantiles, train_end, f"oos_{column}")["summary"]
        summary["forward_column"] = column
        summary["is_default_forward_column"] = column == default_forward_column
        windows.append(summary)

    usable = [window for window in windows if not pd.isna(window.get("ic_mean"))]
    signs = {1 if window["ic_mean"] > 0 else -1 if window["ic_mean"] < 0 else 0 for window in usable}
    if len(usable) < 2:
        status = "insufficient_forward_horizons"
    elif len(signs - {0}) > 1:
        status = "mixed_horizon_ic"
    else:
        status = "directionally_stable_horizons"
    return {
        "status": status,
        "windows": windows,
        "missing_forward_columns": missing,
        "usable_horizons": len(usable),
    }


def _stability_from_summaries(summaries: list[dict[str, Any]], *, minimum_slices: int = 2) -> str:
    usable = [item for item in summaries if not pd.isna(item.get("ic_mean")) and int(item.get("observations", 0) or 0) > 0]
    if len(usable) < minimum_slices:
        return "insufficient_slices"
    signs = {1 if item["ic_mean"] > 0 else -1 if item["ic_mean"] < 0 else 0 for item in usable}
    if len(signs - {0}) > 1:
        return "unstable_mixed_signs"
    magnitudes = [abs(float(item["ic_mean"])) for item in usable]
    if magnitudes and min(magnitudes) < max(magnitudes) * 0.25:
        return "partially_stable_weak_slice"
    return "stable_directional_slices"


def _slice_summary(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    segment: str,
) -> dict[str, Any]:
    summary = _metrics_for_slice(name, factor, returns, cfg, n_quantiles, train_end, segment)["summary"]
    return summary


def _date_level(series: pd.Series) -> pd.Index:
    return series.index.get_level_values("date")


def _market_regime_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
) -> dict[str, Any]:
    oos_returns = returns.loc[_date_level(returns) > train_end].dropna()
    if oos_returns.empty:
        return {"status": "insufficient_oos_returns", "slices": []}
    market = oos_returns.groupby(level="date").mean().sort_index()
    if market.shape[0] < 10 or market.nunique() < 3:
        return {"status": "insufficient_market_state_variation", "slices": []}
    low = market.quantile(1.0 / 3.0)
    high = market.quantile(2.0 / 3.0)
    labels = pd.Series("sideways", index=market.index, dtype="object")
    labels.loc[market <= low] = "bear"
    labels.loc[market >= high] = "bull"

    slices: list[dict[str, Any]] = []
    factor_dates = _date_level(factor)
    return_dates = _date_level(returns)
    for label in ("bear", "sideways", "bull"):
        dates = labels.index[labels == label]
        if dates.empty:
            continue
        selected_factor = factor.loc[factor_dates.isin(dates)]
        selected_returns = returns.loc[return_dates.isin(dates)]
        summary = _slice_summary(name, selected_factor, selected_returns, cfg, n_quantiles, train_end, f"market_regime_{label}")
        summary["regime"] = label
        summary["market_return_mean"] = float(market.loc[dates].mean())
        slices.append(summary)
    return {
        "status": _stability_from_summaries(slices),
        "method": "oos_cross_sectional_forward_return_terciles_for_evaluation_slicing",
        "slices": slices,
    }


def _categorical_slice_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    panel: pd.DataFrame,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    *,
    column: str,
    label_key: str,
    max_slices: int = 12,
) -> dict[str, Any]:
    if column not in panel.columns:
        return {"status": f"not_tested_requires_{column}_field", "slices": []}
    aligned = pd.concat(
        [factor.rename("factor"), returns.rename("fwd_ret"), panel[column].rename(column)],
        axis=1,
    ).dropna(subset=["factor", "fwd_ret", column])
    aligned = aligned.loc[aligned.index.get_level_values("date") > train_end]
    if aligned.empty:
        return {"status": "insufficient_oos_observations", "slices": []}
    counts = aligned[column].astype(str).value_counts().head(max_slices)
    slices: list[dict[str, Any]] = []
    for value in counts.index:
        selected = aligned.loc[aligned[column].astype(str) == value]
        summary = _slice_summary(name, selected["factor"], selected["fwd_ret"], cfg, n_quantiles, train_end, f"{column}_{value}")
        summary[label_key] = value
        slices.append(summary)
    return {"status": _stability_from_summaries(slices), "slices": slices}


def _cross_sectional_bucket_series(values: pd.Series, labels: tuple[str, str, str]) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")

    def one_day(group: pd.Series) -> pd.Series:
        clean = group.dropna()
        out = pd.Series(np.nan, index=group.index, dtype="object")
        if clean.nunique() < 3 or clean.shape[0] < 3:
            return out
        try:
            bucketed = pd.qcut(clean.rank(method="first"), q=3, labels=labels).astype("object")
        except ValueError:
            return out
        out.loc[bucketed.index] = bucketed
        return out

    bucket = numeric.groupby(level="date", group_keys=False).apply(one_day)
    bucket.name = values.name
    return bucket


def _bucket_slice_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    panel: pd.DataFrame,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    *,
    column: str,
    labels: tuple[str, str, str],
    segment_name: str,
) -> dict[str, Any]:
    if column not in panel.columns:
        return {"status": f"not_tested_requires_{column}_field", "slices": []}
    buckets = _cross_sectional_bucket_series(panel[column].rename(segment_name), labels)
    aligned = pd.concat([factor.rename("factor"), returns.rename("fwd_ret"), buckets.rename("bucket")], axis=1).dropna()
    aligned = aligned.loc[aligned.index.get_level_values("date") > train_end]
    if aligned.empty:
        return {"status": "insufficient_oos_observations", "slices": []}
    slices: list[dict[str, Any]] = []
    for label in labels:
        selected = aligned.loc[aligned["bucket"] == label]
        if selected.empty:
            continue
        summary = _slice_summary(name, selected["factor"], selected["fwd_ret"], cfg, n_quantiles, train_end, f"{segment_name}_{label}")
        summary[segment_name] = label
        slices.append(summary)
    return {"status": _stability_from_summaries(slices), "slices": slices}


def _rebalance_frequency_metrics(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    *,
    frequencies: tuple[int, ...] = (1, 5, 20),
) -> dict[str, Any]:
    dates = pd.Index(factor.index.get_level_values("date").unique()).sort_values()
    oos_dates = dates[dates > train_end]
    summaries: list[dict[str, Any]] = []
    for frequency in frequencies:
        rebalance_dates = set(oos_dates[::frequency])
        factor_dates = _date_level(factor)
        sampled_factor = factor.where(factor_dates.isin(rebalance_dates))
        summary = _segment_metrics(name, sampled_factor, returns, cfg, n_quantiles, train_end, f"oos_rebalance_{frequency}d")["summary"]
        summary["rebalance_frequency_days"] = int(frequency)
        summaries.append(summary)
    return {"status": _stability_from_summaries(summaries), "slices": summaries}


def _robustness_layers(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    panel: pd.DataFrame,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
) -> dict[str, Any]:
    industry = _categorical_slice_metrics(
        name,
        factor,
        returns,
        panel,
        cfg,
        n_quantiles,
        train_end,
        column="industry",
        label_key="industry",
    )
    size = _bucket_slice_metrics(
        name,
        factor,
        returns,
        panel,
        cfg,
        n_quantiles,
        train_end,
        column="mktcap",
        labels=("small", "mid", "large"),
        segment_name="size_bucket",
    )
    liquidity = _bucket_slice_metrics(
        name,
        factor,
        returns,
        panel,
        cfg,
        n_quantiles,
        train_end,
        column="amount",
        labels=("low_liquidity", "mid_liquidity", "high_liquidity"),
        segment_name="liquidity_bucket",
    )
    return {
        "market_regime": _market_regime_metrics(name, factor, returns, cfg, n_quantiles, train_end),
        "industry": industry,
        "style": {
            "size": size,
            "liquidity": liquidity,
        },
        "universe": liquidity,
        "rebalance_frequency": _rebalance_frequency_metrics(name, factor, returns, cfg, n_quantiles, train_end),
    }


def _raw_table_presence(cfg: Config) -> dict[str, bool]:
    return {
        table: any((cfg.raw_dir / f"{table}.{suffix}").exists() for suffix in ("parquet", "csv", "pkl"))
        for table in RAW_TABLES
    }


def _data_metadata(panel: pd.DataFrame, cfg: Config, forward_column: str, n_quantiles: int) -> dict:
    raw_presence = _raw_table_presence(cfg)
    if "synthetic" in cfg.universe or not any(raw_presence.values()):
        mode = "synthetic"
    elif all(raw_presence.values()):
        mode = "real"
    else:
        mode = "mixed"
    dates = panel.index.get_level_values("date")
    return {
        "data_mode": mode,
        "raw_tables_present": raw_presence,
        "universe": cfg.universe,
        "start_date": str(dates.min().date()) if len(panel) else None,
        "end_date": str(dates.max().date()) if len(panel) else None,
        "train_end": cfg.train_end,
        "forward_column": forward_column,
        "n_quantiles": n_quantiles,
        "cost_bps": cfg.cost_bps,
        "oos_split": "date_ordered_train_end_exclusive",
        "robustness_policy": robustness_policy(cfg.cost_bps, n_quantiles, forward_column),
    }


def _tradability_mask(panel: pd.DataFrame) -> tuple[pd.Series, list[str], list[str]]:
    mask = pd.Series(True, index=panel.index)
    constraints: list[str] = []
    missing: list[str] = []
    if "amount" in panel.columns:
        amount = pd.to_numeric(panel["amount"], errors="coerce")
        mask &= amount > 0
        constraints.append("amount_positive")
    else:
        missing.append("amount")
    for column, constraint in (
        ("is_suspended", "not_suspended"),
        ("limit_up", "not_limit_up"),
        ("limit_down", "not_limit_down"),
    ):
        if column in panel.columns:
            blocked = panel[column].reindex(panel.index).eq(True)
            mask &= ~blocked
            constraints.append(constraint)
        else:
            missing.append(column)
    return mask, constraints, missing


def _shifted_adv(amount: pd.Series, *, window: int = ADV_WINDOW, min_periods: int = ADV_MIN_PERIODS) -> pd.Series:
    numeric = pd.to_numeric(amount, errors="coerce").sort_index()
    adv = numeric.groupby(level="code", group_keys=False).transform(
        lambda item: item.rolling(window=window, min_periods=min_periods).mean().shift(1)
    )
    adv.name = "adv"
    return adv.sort_index()


def _bool_column(panel: pd.DataFrame, column: str, index: pd.Index) -> pd.Series:
    if column not in panel.columns:
        return pd.Series(False, index=index)
    return panel[column].reindex(index).eq(True)


def _execution_review(
    factor: pd.Series,
    returns: pd.Series,
    panel: pd.DataFrame,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
) -> dict[str, Any]:
    target_weights = long_short_weights(factor, n=n_quantiles)
    if target_weights.empty:
        return {
            "order_constraints": [],
            "portfolio_value": PORTFOLIO_VALUE,
            "max_participation_rate": MAX_PARTICIPATION_RATE,
            "adv_window": ADV_WINDOW,
            "min_adv_notional": MIN_ADV_NOTIONAL,
            "impact_bps_per_10pct_adv": IMPACT_BPS_PER_10PCT_ADV,
            "submitted_notional": 0.0,
            "executed_notional": 0.0,
            "blocked_buy_notional": 0.0,
            "blocked_sell_notional": 0.0,
            "liquidity_blocked_notional": 0.0,
            "partial_fill_notional": 0.0,
            "fill_rate_mean": float("nan"),
            "impact_cost_mean": float("nan"),
            "execution_turnover_mean": float("nan"),
            "executable_long_short_mean": float("nan"),
            "executable_net_long_short_mean": float("nan"),
            "executable_long_short": pd.Series(dtype=float, name="executable_long_short"),
            "executable_net_long_short": pd.Series(dtype=float, name="executable_net_long_short"),
        }

    constraints = ["directional_limit_checks", "suspended_orders_blocked"]
    missing: list[str] = []
    if "amount" in panel.columns:
        amount = pd.to_numeric(panel["amount"], errors="coerce")
        adv = _shifted_adv(amount)
        constraints.extend(["amount_positive", "shifted_adv_capacity", "max_participation_rate", "partial_fills", "impact_cost"])
    else:
        amount = pd.Series(np.nan, index=panel.index)
        adv = pd.Series(np.nan, index=panel.index, name="adv")
        missing.append("amount")

    records: list[dict[str, Any]] = []
    gross_returns: dict[pd.Timestamp, float] = {}
    net_returns: dict[pd.Timestamp, float] = {}
    previous = pd.Series(dtype=float)
    dates = pd.Index(target_weights.index.get_level_values("date").unique()).sort_values()
    dates = dates[dates > train_end]
    return_dates = returns.index.get_level_values("date")

    for date in dates:
        target = target_weights.xs(date, level="date")
        universe = previous.index.union(target.index)
        submitted = target.reindex(universe, fill_value=0.0).sub(previous.reindex(universe, fill_value=0.0))
        multi_index = pd.MultiIndex.from_product([[date], universe], names=["date", "code"])
        suspended = _bool_column(panel, "is_suspended", multi_index).droplevel("date")
        limit_up = _bool_column(panel, "limit_up", multi_index).droplevel("date")
        limit_down = _bool_column(panel, "limit_down", multi_index).droplevel("date")
        today_amount = amount.reindex(multi_index).droplevel("date")
        today_adv = adv.reindex(multi_index).droplevel("date")
        capacity_base = pd.concat([today_amount.rename("amount"), today_adv.rename("adv")], axis=1).min(axis=1)

        buy = submitted > 0
        sell = submitted < 0
        direction_blocked = suspended | (buy & limit_up) | (sell & limit_down)
        after_direction = submitted.where(~direction_blocked, 0.0)
        has_liquidity = (today_amount > 0) & (today_adv >= MIN_ADV_NOTIONAL) & (capacity_base > 0)
        if "amount" not in panel.columns:
            has_liquidity = pd.Series(True, index=universe)
            cap_weight = pd.Series(np.inf, index=universe)
        else:
            cap_weight = (capacity_base * MAX_PARTICIPATION_RATE / PORTFOLIO_VALUE).fillna(0.0)
        after_liquidity = after_direction.where(has_liquidity, 0.0)
        executable_abs = pd.concat([after_liquidity.abs().rename("order"), cap_weight.rename("cap")], axis=1).min(axis=1)
        executed = np.sign(after_liquidity) * executable_abs
        executed = executed.fillna(0.0)
        current = previous.reindex(universe, fill_value=0.0).add(executed, fill_value=0.0)

        date_returns = returns.loc[return_dates == date].droplevel("date").reindex(universe).fillna(0.0)
        gross = float(current.mul(date_returns, fill_value=0.0).sum())
        brokerage_cost = float(executed.abs().sum() * cfg.cost_bps / 10000.0)
        if "amount" in panel.columns:
            participation_base = capacity_base.reindex(universe).replace(0.0, np.nan)
            participation = executed.abs().mul(PORTFOLIO_VALUE).div(participation_base).replace([np.inf, -np.inf], np.nan).fillna(0.0)
            impact_bps = participation / MAX_PARTICIPATION_RATE * IMPACT_BPS_PER_10PCT_ADV
            impact_cost = float(executed.abs().mul(impact_bps).sum() / 10000.0)
        else:
            impact_cost = 0.0
        net = gross - brokerage_cost - impact_cost

        submitted_abs = float(submitted.abs().sum() * PORTFOLIO_VALUE)
        executed_abs_notional = float(executed.abs().sum() * PORTFOLIO_VALUE)
        records.append(
            {
                "date": pd.Timestamp(date),
                "submitted_notional": submitted_abs,
                "executed_notional": executed_abs_notional,
                "blocked_buy_notional": float(submitted.where(buy & direction_blocked, 0.0).abs().sum() * PORTFOLIO_VALUE),
                "blocked_sell_notional": float(submitted.where(sell & direction_blocked, 0.0).abs().sum() * PORTFOLIO_VALUE),
                "liquidity_blocked_notional": float(after_direction.where(~has_liquidity, 0.0).abs().sum() * PORTFOLIO_VALUE),
                "partial_fill_notional": float(after_liquidity.abs().sub(executed.abs()).clip(lower=0.0).sum() * PORTFOLIO_VALUE),
                "fill_rate": executed_abs_notional / submitted_abs if submitted_abs > 0 else float("nan"),
                "impact_cost": impact_cost,
                "execution_turnover": float(executed.abs().sum()),
            }
        )
        gross_returns[pd.Timestamp(date)] = gross
        net_returns[pd.Timestamp(date)] = net
        previous = current.loc[current.abs() > 1e-12]

    daily = pd.DataFrame(records).set_index("date") if records else pd.DataFrame()
    oos_daily = daily.loc[daily.index > train_end] if not daily.empty else daily
    executable_long_short = pd.Series(gross_returns, name="executable_long_short").sort_index()
    executable_net_long_short = pd.Series(net_returns, name="executable_net_long_short").sort_index()
    executable_long_short = executable_long_short.loc[executable_long_short.index > train_end]
    executable_net_long_short = executable_net_long_short.loc[executable_net_long_short.index > train_end]
    return {
        "order_constraints": constraints,
        "execution_missing_optional_fields": missing,
        "portfolio_value": PORTFOLIO_VALUE,
        "max_participation_rate": MAX_PARTICIPATION_RATE,
        "adv_window": ADV_WINDOW,
        "min_adv_notional": MIN_ADV_NOTIONAL,
        "impact_bps_per_10pct_adv": IMPACT_BPS_PER_10PCT_ADV,
        "submitted_notional": float(oos_daily["submitted_notional"].sum()) if not oos_daily.empty else 0.0,
        "executed_notional": float(oos_daily["executed_notional"].sum()) if not oos_daily.empty else 0.0,
        "blocked_buy_notional": float(oos_daily["blocked_buy_notional"].sum()) if not oos_daily.empty else 0.0,
        "blocked_sell_notional": float(oos_daily["blocked_sell_notional"].sum()) if not oos_daily.empty else 0.0,
        "liquidity_blocked_notional": float(oos_daily["liquidity_blocked_notional"].sum()) if not oos_daily.empty else 0.0,
        "partial_fill_notional": float(oos_daily["partial_fill_notional"].sum()) if not oos_daily.empty else 0.0,
        "fill_rate_mean": float(oos_daily["fill_rate"].mean()) if not oos_daily.empty else float("nan"),
        "impact_cost_mean": float(oos_daily["impact_cost"].mean()) if not oos_daily.empty else float("nan"),
        "execution_turnover_mean": float(oos_daily["execution_turnover"].mean()) if not oos_daily.empty else float("nan"),
        "executable_long_short_mean": float(executable_long_short.mean()) if not executable_long_short.empty else float("nan"),
        "executable_net_long_short_mean": float(executable_net_long_short.mean()) if not executable_net_long_short.empty else float("nan"),
        "daily_execution": oos_daily.reset_index().to_dict(orient="records") if not oos_daily.empty else [],
        "executable_long_short": executable_long_short,
        "executable_net_long_short": executable_net_long_short,
    }


def _tradability_review(
    name: str,
    factor: pd.Series,
    returns: pd.Series,
    panel: pd.DataFrame,
    cfg: Config,
    n_quantiles: int,
    train_end: pd.Timestamp,
    ideal_summary: dict,
) -> dict:
    mask, constraints, missing = _tradability_mask(panel)
    tradable_factor = factor.where(mask.reindex(factor.index).fillna(False))
    tradable = _segment_metrics(name, tradable_factor, returns, cfg, n_quantiles, train_end, "oos_tradable")
    execution = _execution_review(factor, returns, panel, cfg, n_quantiles, train_end)
    oos_dates = factor.index.get_level_values("date") > train_end
    aligned = pd.concat(
        [factor.loc[oos_dates].rename("factor"), returns.loc[returns.index.get_level_values("date") > train_end].rename("fwd_ret")],
        axis=1,
    ).dropna()
    eligible = aligned.index[mask.reindex(aligned.index).fillna(False)]
    review = {
        "enabled": bool(constraints),
        "constraints": constraints,
        "missing_optional_fields": missing,
        "eligible_observations": int(len(eligible)),
        "dropped_observations": int(max(len(aligned) - len(eligible), 0)),
        "ideal_net_long_short_mean": ideal_summary.get("net_long_short_mean"),
        "tradable_net_long_short_mean": tradable["summary"].get("net_long_short_mean"),
        "tradable_summary": tradable["summary"],
    }
    review.update(execution)
    if execution.get("execution_missing_optional_fields"):
        review["missing_optional_fields"] = sorted(set(missing) | set(execution["execution_missing_optional_fields"]))
    return review


def backtest(
    expr: FactorExpr,
    panel: pd.DataFrame,
    fwd_ret: pd.DataFrame | pd.Series,
    cfg: Config = CONFIG,
    forward_column: str = "fwd_ret_5",
    n_quantiles: int = 5,
) -> dict:
    ok, reason = validate_field_availability(expression_names(expr.expression) | set(expr.fields_used), panel)
    if not ok:
        raise ValueError(f"factor field availability check failed: {reason}")
    factor = evaluate(expr, panel)
    if isinstance(fwd_ret, pd.DataFrame):
        returns = fwd_ret[forward_column]
    else:
        returns = fwd_ret
    returns = returns.sort_index()

    train_end = pd.Timestamp(cfg.train_end)
    train = _segment_metrics(expr.name, factor, returns, cfg, n_quantiles, train_end, "train")
    oos = _segment_metrics(expr.name, factor, returns, cfg, n_quantiles, train_end, "oos")
    walk_forward = _walk_forward_metrics(expr.name, factor, returns, cfg, n_quantiles, train_end)
    tradability = _tradability_review(expr.name, factor, returns, panel, cfg, n_quantiles, train_end, oos["summary"])
    robustness_layers = _robustness_layers(expr.name, factor, returns, panel, cfg, n_quantiles, train_end)
    horizon_sensitivity = _horizon_sensitivity_metrics(
        expr.name,
        factor,
        fwd_ret,
        cfg,
        n_quantiles,
        train_end,
        forward_column,
    )
    novelty = expr.metadata.get("validation", {}).get("novelty", {}) if isinstance(expr.metadata, dict) else {}
    robustness = robustness_summary(
        summary=oos["summary"],
        train_summary=train["summary"],
        walk_forward=walk_forward,
        tradability=tradability,
        rank_ic_series=oos["rank_ic"],
        novelty=novelty,
        horizon_sensitivity=horizon_sensitivity,
        robustness_layers=robustness_layers,
    )

    return {
        "expr": expr.to_dict(),
        "summary": oos["summary"],
        "train_summary": train["summary"],
        "data": _data_metadata(panel, cfg, forward_column, n_quantiles),
        "walk_forward": walk_forward,
        "tradability": tradability,
        "robustness_layers": robustness_layers,
        "robustness": robustness,
        "factor": factor,
        "rank_ic": oos["rank_ic"],
        "quantile_returns": oos["quantile_returns"],
        "long_short": oos["long_short"],
        "turnover": oos["turnover"],
        "net_long_short": oos["net_long_short"],
        "train_rank_ic": train["rank_ic"],
        "train_quantile_returns": train["quantile_returns"],
        "train_long_short": train["long_short"],
        "train_turnover": train["turnover"],
        "train_net_long_short": train["net_long_short"],
    }
