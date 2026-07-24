from __future__ import annotations

import hashlib
import json
import math
import subprocess
from typing import Any

import pandas as pd

from src.audit import EvidenceState, EvidenceStatus, ExclusionAuditRecord
from src.backtest.metrics import ic_ir, long_short_return, quantile_returns, rank_ic, turnover
from src.backtest.robustness import FORWARD_COLUMN_GRID, robustness_policy, robustness_summary
from src.config import CONFIG, Config
from src.factors.engine import FactorExpr, evaluate, expression_names
from src.utils.field_availability import get_field_availability, validate_field_availability


RAW_TABLES = ("prices", "fundamentals", "universe")
MIN_WALK_FORWARD_IC_DAYS = 20
MIN_WALK_FORWARD_OBSERVATIONS = 30


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


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


def _window_health(window: dict, n_quantiles: int) -> dict[str, Any]:
    flags: list[str] = []
    ic_count = int(window.get("ic_count") or 0)
    observations = int(window.get("observations") or 0)
    min_observations = max(MIN_WALK_FORWARD_OBSERVATIONS, n_quantiles * 10)

    if ic_count < MIN_WALK_FORWARD_IC_DAYS:
        flags.append("insufficient_ic_days")
    if observations < min_observations:
        flags.append("insufficient_observations")
    if any(flag.startswith("insufficient_") for flag in flags):
        return {"health_status": "sample_insufficient", "health_flags": flags}

    for metric in ("ic_mean", "ic_ir", "net_long_short_mean", "turnover_mean"):
        if not _is_finite_number(window.get(metric)):
            flags.append(f"{metric}_not_finite")

    if flags:
        return {"health_status": "anomalous", "health_flags": flags}

    ic_mean = float(window["ic_mean"])
    ic_ir_value = float(window["ic_ir"])
    net_mean = float(window["net_long_short_mean"])
    turnover_mean = float(window["turnover_mean"])

    anomalous_flags: list[str] = []
    if abs(ic_mean) >= 0.999:
        anomalous_flags.append("suspiciously_perfect_ic_mean")
    if abs(ic_ir_value) >= 6.0:
        anomalous_flags.append("suspiciously_large_abs_ic_ir")
    if turnover_mean > 2.5:
        anomalous_flags.append("high_turnover_mean")
    if anomalous_flags:
        return {"health_status": "anomalous", "health_flags": anomalous_flags}

    weak_flags: list[str] = []
    if ic_mean <= 0.0:
        weak_flags.append("non_positive_ic_mean")
    if net_mean <= 0.0:
        weak_flags.append("non_positive_net_long_short_mean")
    if abs(ic_ir_value) < 0.05:
        weak_flags.append("low_abs_ic_ir")
    if weak_flags:
        return {"health_status": "weak", "health_flags": weak_flags}

    return {"health_status": "pass", "health_flags": []}


def _walk_forward_health_summary(windows: list[dict]) -> dict[str, Any]:
    total = len(windows)
    counts = {
        "pass": sum(1 for window in windows if window.get("health_status") == "pass"),
        "weak": sum(1 for window in windows if window.get("health_status") == "weak"),
        "anomalous": sum(1 for window in windows if window.get("health_status") == "anomalous"),
        "sample_insufficient": sum(1 for window in windows if window.get("health_status") == "sample_insufficient"),
    }
    evaluated = counts["pass"] + counts["weak"] + counts["anomalous"]
    pass_rate = float(counts["pass"] / evaluated) if evaluated else 0.0

    risk_flags: list[str] = []
    if total == 0:
        risk_flags.append("no_walk_forward_windows")
    if evaluated < 2:
        risk_flags.append("insufficient_evaluated_windows")
    if counts["weak"]:
        risk_flags.append("has_weak_windows")
    if counts["anomalous"]:
        risk_flags.append("has_anomalous_windows")
    if counts["sample_insufficient"]:
        risk_flags.append("has_sample_insufficient_windows")
    if evaluated and pass_rate < 0.60:
        risk_flags.append("low_window_pass_rate")

    directional = [
        1 if float(window["ic_mean"]) > 0 else -1 if float(window["ic_mean"]) < 0 else 0
        for window in windows
        if window.get("health_status") != "sample_insufficient" and _is_finite_number(window.get("ic_mean"))
    ]
    if len(set(directional) - {0}) > 1:
        risk_flags.append("mixed_window_ic_direction")

    if evaluated < 2:
        overall = "insufficient"
    elif counts["anomalous"] or pass_rate < 0.50:
        overall = "fail"
    elif counts["weak"] or counts["sample_insufficient"] or pass_rate < 0.80:
        overall = "review"
    else:
        overall = "pass"

    primary_risks = {
        "no_walk_forward_windows": "No OOS walk-forward windows were available for health review.",
        "insufficient_evaluated_windows": "Fewer than two sufficiently sampled OOS windows were available.",
        "has_weak_windows": "At least one sufficiently sampled window had weak IC, net spread, or ICIR behavior.",
        "has_anomalous_windows": "At least one window had non-finite metrics, unusually perfect IC, very large ICIR, or high turnover.",
        "has_sample_insufficient_windows": "At least one window was retained but marked too small for a reliable window-level read.",
        "low_window_pass_rate": "The share of sufficiently sampled windows passing deterministic health checks was below 60%.",
        "mixed_window_ic_direction": "Sufficiently sampled windows did not agree on IC direction.",
    }
    return {
        "health_status": overall,
        "total_windows": total,
        "evaluated_windows": evaluated,
        "passing_windows": counts["pass"],
        "weak_windows": counts["weak"],
        "anomalous_windows": counts["anomalous"],
        "sample_insufficient_windows": counts["sample_insufficient"],
        "pass_rate": pass_rate,
        "risk_flags": risk_flags,
        "primary_risks": [primary_risks[flag] for flag in risk_flags],
        "thresholds": {
            "min_ic_days": MIN_WALK_FORWARD_IC_DAYS,
            "min_observations": MIN_WALK_FORWARD_OBSERVATIONS,
            "min_observations_per_quantile_multiplier": 10,
            "perfect_abs_ic_mean": 0.999,
            "large_abs_ic_ir": 6.0,
            "high_turnover_mean": 2.5,
            "weak_abs_ic_ir": 0.05,
        },
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
        if len(window_dates) == 0:
            continue
        start = window_dates[0]
        end = window_dates[-1]
        factor_dates = factor.index.get_level_values("date")
        return_dates = returns.index.get_level_values("date")
        sel_factor = factor.loc[(factor_dates >= start) & (factor_dates <= end)]
        sel_returns = returns.loc[(return_dates >= start) & (return_dates <= end)]
        window = _metrics_for_slice(name, sel_factor, sel_returns, cfg, n_quantiles, train_end, "walk_forward")["summary"]
        window["window_index"] = len(windows)
        window["trading_days"] = int(len(window_dates))
        window.update(_window_health(window, n_quantiles))
        windows.append(window)

    health_summary = _walk_forward_health_summary(windows)
    usable = [
        window
        for window in windows
        if window.get("health_status") != "sample_insufficient" and not pd.isna(window.get("ic_mean"))
    ]
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
        "health_status": health_summary["health_status"],
        "health_summary": health_summary,
        "pass_rate": health_summary["pass_rate"],
        "risk_flags": health_summary["risk_flags"],
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


def _json_fingerprint(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _git_value(args: list[str]) -> str | None:
    try:
        return subprocess.check_output(args, cwd=CONFIG.data_dir.parents[0], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def _git_metadata() -> dict[str, Any]:
    commit = _git_value(["git", "rev-parse", "HEAD"])
    status = _git_value(["git", "status", "--short"])
    return {
        "commit": commit,
        "worktree_dirty": bool(status),
        "status_available": status is not None,
    }


def _experiment_lock(
    expr: FactorExpr,
    panel: pd.DataFrame,
    cfg: Config,
    data: dict,
    forward_column: str,
    n_quantiles: int,
) -> dict[str, Any]:
    field_metadata = get_field_availability(panel)
    git = _git_metadata()
    lock = {
        "code": git,
        "config": {
            "freq": cfg.freq,
            "universe": cfg.universe,
            "start_date": cfg.start_date,
            "end_date": cfg.end_date,
            "train_end": cfg.train_end,
            "cost_bps": cfg.cost_bps,
            "forward_column": forward_column,
            "n_quantiles": n_quantiles,
        },
        "data": {
            "data_mode": data.get("data_mode"),
            "raw_tables_present": data.get("raw_tables_present"),
            "data_dir": str(cfg.data_dir),
            "field_catalog_hash": _json_fingerprint(field_metadata) if field_metadata else None,
            "panel_index_start": data.get("start_date"),
            "panel_index_end": data.get("end_date"),
        },
        "factor": {
            "name": expr.name,
            "expression_hash": _json_fingerprint(expr.expression),
            "fields_used": sorted(expr.fields_used),
        },
        "llm": {
            "backend": cfg.llm_backend,
            "model": cfg.llm_model,
            "max_tokens": cfg.llm_max_tokens,
            "temperature": cfg.llm_temperature,
            "cache_key": "not_applicable_backtest_does_not_call_llm",
            "backtest_calls_llm": False,
        },
    }
    warnings: list[str] = []
    if not git["commit"]:
        warnings.append("git_commit_unavailable")
    if git["worktree_dirty"]:
        warnings.append("git_worktree_dirty")
    if not field_metadata:
        warnings.append("field_catalog_metadata_missing")
    if data.get("data_mode") in {None, "mixed"}:
        warnings.append("data_mode_not_fully_locked")
    lock["warnings"] = warnings
    lock["lock_hash"] = _json_fingerprint(lock)
    return lock


def _field_lineage(expr: FactorExpr, panel: pd.DataFrame) -> dict[str, Any]:
    metadata = get_field_availability(panel)
    rows = []
    missing = []
    for field in sorted(set(expr.fields_used) | expression_names(expr.expression)):
        item = metadata.get(field)
        if item is None:
            missing.append(field)
            rows.append({"field": field, "status": "untested", "reason_code": "field_lineage_missing"})
        else:
            row = dict(item)
            row["status"] = "verified"
            row["reason_code"] = "field_lineage_present"
            rows.append(row)
    state = EvidenceState(
        status=EvidenceStatus.VERIFIED if not missing else EvidenceStatus.UNTESTED,
        evidence=[row["field"] for row in rows if row.get("status") == "verified"],
        reason_code="field_lineage_present" if not missing else "field_lineage_missing",
        message="All factor input fields have availability metadata." if not missing else "Some factor input fields lack availability metadata.",
    )
    return {"status": state.to_dict(), "fields": rows, "missing_fields": missing}


def _audit_summary(expr: FactorExpr, panel: pd.DataFrame, data: dict, tradability: dict, field_lineage: dict) -> dict[str, Any]:
    field_state = field_lineage["status"]
    metadata = get_field_availability(panel)
    evidence_states = {
        "field_lineage": field_state,
        "pit_availability": EvidenceState(
            status=EvidenceStatus.VERIFIED,
            evidence=sorted(metadata),
            reason_code="pit_metadata_present",
            message="PIT-sensitive fields are guarded by field availability metadata.",
        ).to_dict(),
        "data_mode_label": EvidenceState(
            status=EvidenceStatus.FIXED_THIS_RUN,
            evidence=[str(data.get("data_mode"))] if data.get("data_mode") else [],
            reason_code="data_mode_recorded",
            message="Synthetic, real, or mixed data mode is fixed in this run.",
        ).to_dict(),
        "tradability_constraints": EvidenceState(
            status=EvidenceStatus.VERIFIED if tradability.get("constraints") else EvidenceStatus.UNTESTED,
            evidence=tradability.get("constraints", []),
            reason_code="tradability_constraints_present" if tradability.get("constraints") else "tradability_constraints_missing",
            message="Optional tradability constraints were applied when source fields existed.",
        ).to_dict(),
        "unimplemented_metrics": EvidenceState(
            status=EvidenceStatus.UNTESTED,
            evidence=["annualized_return_requires_portfolio_equity_curve"],
            reason_code="metric_not_implemented",
            message="Unsupported dimensions remain fail-closed as untested.",
        ).to_dict(),
    }
    exclusions = [
        ExclusionAuditRecord(
            decision="exclude" if tradability.get("dropped_observations", 0) else "accept",
            reason_code="tradability_filter",
            message="Rows failing deterministic tradability checks are excluded from tradable review.",
            rule_version="audit-v1",
            decided_by="deterministic_rule",
            affected_count=int(tradability.get("dropped_observations", 0) or 0),
            adjustable=True,
        ).to_dict()
    ]
    for field in tradability.get("missing_optional_fields", []):
        exclusions.append(
            ExclusionAuditRecord(
                decision="untested",
                reason_code=f"missing_optional_tradability_field:{field}",
                message=f"Optional tradability field {field} is missing, so that constraint is untested.",
                rule_version="audit-v1",
                decided_by="deterministic_rule",
                affected_count=0,
                adjustable=False,
            ).to_dict()
        )
    return {
        "evidence_states": evidence_states,
        "exclusion_audit": exclusions,
        "rule_version": "audit-v1",
        "candidate": {
            "name": expr.name,
            "fields_used": sorted(expr.fields_used),
            "validation_metadata": expr.metadata.get("validation", {}) if isinstance(expr.metadata, dict) else {},
        },
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
    data = _data_metadata(panel, cfg, forward_column, n_quantiles)
    walk_forward = _walk_forward_metrics(expr.name, factor, returns, cfg, n_quantiles, train_end)
    tradability = _tradability_review(expr.name, factor, returns, panel, cfg, n_quantiles, train_end, oos["summary"])
    field_lineage = _field_lineage(expr, panel)
    audit = _audit_summary(expr, panel, data, tradability, field_lineage)
    experiment_lock = _experiment_lock(expr, panel, cfg, data, forward_column, n_quantiles)
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
        "data": data,
        "experiment_lock": experiment_lock,
        "field_lineage": field_lineage,
        "audit": audit,
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
