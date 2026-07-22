from __future__ import annotations

import math

import pandas as pd

from src.backtest.metrics import ic_ir, long_short_return, quantile_returns, rank_ic, turnover
from src.backtest.robustness import FORWARD_COLUMN_GRID, robustness_policy, robustness_summary
from src.config import CONFIG, Config
from src.factors.engine import FactorExpr, evaluate, expression_names
from src.utils.field_availability import validate_field_availability


RAW_TABLES = ("prices", "fundamentals", "universe")


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
            mask &= ~panel[column].fillna(False).astype(bool)
            constraints.append(constraint)
        else:
            missing.append(column)
    return mask, constraints, missing


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
    oos_dates = factor.index.get_level_values("date") > train_end
    aligned = pd.concat(
        [factor.loc[oos_dates].rename("factor"), returns.loc[returns.index.get_level_values("date") > train_end].rename("fwd_ret")],
        axis=1,
    ).dropna()
    eligible = aligned.index[mask.reindex(aligned.index).fillna(False)]
    return {
        "enabled": bool(constraints),
        "constraints": constraints,
        "missing_optional_fields": missing,
        "eligible_observations": int(len(eligible)),
        "dropped_observations": int(max(len(aligned) - len(eligible), 0)),
        "ideal_net_long_short_mean": ideal_summary.get("net_long_short_mean"),
        "tradable_net_long_short_mean": tradable["summary"].get("net_long_short_mean"),
        "tradable_summary": tradable["summary"],
    }


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
    )

    return {
        "expr": expr.to_dict(),
        "summary": oos["summary"],
        "train_summary": train["summary"],
        "data": _data_metadata(panel, cfg, forward_column, n_quantiles),
        "walk_forward": walk_forward,
        "tradability": tradability,
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
