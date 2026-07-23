from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from src.config import CONFIG


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass
    return str(value)


def _series_records(series: pd.Series) -> list[dict[str, Any]]:
    data = series.dropna().reset_index()
    value_name = series.name or "value"
    if value_name not in data.columns:
        data = data.rename(columns={0: value_name})
    return data.to_dict(orient="records")


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return frame.reset_index().to_dict(orient="records")


def _public_json(value: Any) -> Any:
    if isinstance(value, pd.Series):
        return _series_records(value)
    if isinstance(value, pd.DataFrame):
        return _frame_records(value)
    if isinstance(value, dict):
        return {key: _public_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_public_json(item) for item in value]
    if isinstance(value, tuple):
        return [_public_json(item) for item in value]
    return value


def _factor_quality(result: dict) -> dict[str, Any]:
    factor = result.get("factor")
    if not isinstance(factor, pd.Series) or factor.empty:
        return {
            "coverage_ratio": "not_computed_requires_factor_values",
            "missing_ratio": "not_computed_requires_factor_values",
            "extreme_value_ratio": "not_computed_requires_factor_values",
        }

    data = result.get("data", {})
    train_end = data.get("train_end") or result.get("summary", {}).get("train_end")
    selected = factor
    if train_end is not None and isinstance(factor.index, pd.MultiIndex) and "date" in factor.index.names:
        dates = factor.index.get_level_values("date")
        selected = factor.loc[dates > pd.Timestamp(train_end)]

    total = int(selected.shape[0])
    if total == 0:
        return {
            "coverage_ratio": "not_available_empty_oos_slice",
            "missing_ratio": "not_available_empty_oos_slice",
            "extreme_value_ratio": "not_available_empty_oos_slice",
        }

    clean = pd.to_numeric(selected, errors="coerce")
    valid = clean.dropna()
    coverage = float(valid.shape[0] / total)
    missing = float(1.0 - coverage)
    if valid.empty:
        extreme = float("nan")
    else:
        median = valid.median()
        mad = (valid - median).abs().median()
        if pd.isna(mad) or mad == 0:
            extreme = 0.0
        else:
            robust_z = (valid - median).abs() / (1.4826 * mad)
            extreme = float((robust_z > 5.0).mean())
    return {
        "coverage_ratio": coverage,
        "missing_ratio": missing,
        "extreme_value_ratio": extreme,
    }


def _quantile_monotonicity(quantile_returns: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(quantile_returns, pd.DataFrame) or quantile_returns.empty:
        return {
            "status": "not_available_empty_quantile_returns",
            "mean_by_quantile": {},
            "spread_mean": float("nan"),
        }
    means = quantile_returns.mean().dropna()
    if means.shape[0] < 2:
        return {
            "status": "not_available_insufficient_quantiles",
            "mean_by_quantile": means.to_dict(),
            "spread_mean": float("nan"),
        }
    diffs = means.diff().dropna()
    increasing = bool((diffs >= 0).all())
    decreasing = bool((diffs <= 0).all())
    if increasing:
        status = "monotonic_increasing"
    elif decreasing:
        status = "monotonic_decreasing"
    else:
        status = "non_monotonic"
    return {
        "status": status,
        "mean_by_quantile": means.to_dict(),
        "spread_mean": float(means.iloc[-1] - means.iloc[0]),
    }


def _positive_rate(series: pd.Series) -> float:
    clean = series.dropna()
    if clean.empty:
        return float("nan")
    return float((clean > 0).mean())


def _evaluation_layers(result: dict) -> dict[str, Any]:
    summary = result.get("summary", {})
    train = result.get("train_summary", {})
    data = result.get("data", {})
    tradability = result.get("tradability", {})
    robustness = result.get("robustness", {})
    metadata = result.get("expr", {}).get("metadata", {}) or {}
    tradable_summary = tradability.get("tradable_summary", {}) if isinstance(tradability, dict) else {}
    qmono = _quantile_monotonicity(result.get("quantile_returns", pd.DataFrame()))
    quality = _factor_quality(result)
    rank_ic_series = result.get("rank_ic", pd.Series(dtype=float))

    factor_validity = {
        "train_rank_ic_mean": train.get("ic_mean"),
        "oos_rank_ic_mean": summary.get("ic_mean"),
        "oos_rank_ic_std": summary.get("ic_std"),
        "oos_icir": summary.get("ic_ir"),
        "oos_ic_positive_rate": _positive_rate(rank_ic_series),
        "oos_ic_t_stat": summary.get("ic_t_stat"),
        "oos_ic_pvalue_normal_approx": summary.get("ic_pvalue_normal_approx"),
        "oos_ic_observation_days": summary.get("ic_count"),
        "oos_observation_rows": summary.get("observations"),
        "quantile_monotonicity": qmono["status"],
        "quantile_mean_returns": qmono["mean_by_quantile"],
        "quantile_spread_mean": qmono["spread_mean"],
        "long_short_mean": summary.get("long_short_mean"),
        "turnover_mean": summary.get("turnover_mean"),
        **quality,
        "inference_note": summary.get("ic_inference_note"),
    }

    strategy_performance = {
        "gross_long_short_mean": summary.get("long_short_mean"),
        "net_long_short_mean": summary.get("net_long_short_mean"),
        "turnover_mean": summary.get("turnover_mean"),
        "cost_bps": data.get("cost_bps", summary.get("cost_bps")),
        "cost_convention": data.get("robustness_policy", {}).get("cost_convention") if isinstance(data, dict) else None,
        "a_share_cost_reality_checks": data.get("robustness_policy", {}).get("a_share_reality_checks") if isinstance(data, dict) else None,
        "tradable_net_long_short_mean": tradable_summary.get("net_long_short_mean"),
        "executable_long_short_mean": tradability.get("executable_long_short_mean") if isinstance(tradability, dict) else None,
        "executable_net_long_short_mean": tradability.get("executable_net_long_short_mean") if isinstance(tradability, dict) else None,
        "fill_rate_mean": tradability.get("fill_rate_mean") if isinstance(tradability, dict) else None,
        "impact_cost_mean": tradability.get("impact_cost_mean") if isinstance(tradability, dict) else None,
        "impact_coverage_mean": tradability.get("impact_coverage_mean") if isinstance(tradability, dict) else None,
        "detailed_cost_total_mean": tradability.get("cost_total_mean") if isinstance(tradability, dict) else None,
        "detailed_cost_component_means": tradability.get("cost_component_means") if isinstance(tradability, dict) else None,
        "detailed_cost_component_totals": tradability.get("cost_component_totals") if isinstance(tradability, dict) else None,
        "cost_model_assumptions": tradability.get("cost_model_assumptions") if isinstance(tradability, dict) else None,
        "blocked_buy_notional": tradability.get("blocked_buy_notional") if isinstance(tradability, dict) else None,
        "blocked_sell_notional": tradability.get("blocked_sell_notional") if isinstance(tradability, dict) else None,
        "partial_fill_notional": tradability.get("partial_fill_notional") if isinstance(tradability, dict) else None,
        "dropped_observations": tradability.get("dropped_observations") if isinstance(tradability, dict) else None,
        "annualized_return": "not_computed_requires_portfolio_equity_curve",
        "excess_return": "not_computed_requires_benchmark_returns",
        "annualized_volatility": "not_computed_requires_portfolio_equity_curve",
        "max_drawdown": "not_computed_requires_portfolio_equity_curve",
        "sharpe_ratio": "not_computed_requires_portfolio_equity_curve",
        "information_ratio": "not_computed_requires_benchmark_returns",
        "calmar_ratio": "not_computed_requires_portfolio_equity_curve",
    }

    risk_exposure_independence = {
        "declared_risk_exposures": metadata.get("risk_exposures", []),
        "similarity_risk": robustness.get("similarity_risk") if isinstance(robustness, dict) else None,
        "nearest_factor": robustness.get("nearest_factor") if isinstance(robustness, dict) else None,
        "max_abs_existing_corr": robustness.get("max_abs_existing_corr") if isinstance(robustness, dict) else None,
        "regime_dependency": robustness.get("regime_dependency") if isinstance(robustness, dict) else None,
        "market_regime_stability": robustness.get("market_regime_stability") if isinstance(robustness, dict) else None,
        "universe_stability": robustness.get("universe_stability") if isinstance(robustness, dict) else None,
        "industry_stability": robustness.get("industry_stability") if isinstance(robustness, dict) else None,
        "style_stability": robustness.get("style_stability") if isinstance(robustness, dict) else None,
        "rebalance_frequency_stability": robustness.get("rebalance_frequency_stability") if isinstance(robustness, dict) else None,
        "market_beta_exposure": "not_computed_requires_benchmark_returns",
        "size_style_exposure": "not_computed_requires_style_factor_panel",
        "industry_exposure": "not_computed_requires_industry_field",
        "neutralized_rank_ic_delta": "not_computed_requires_neutralization_run",
        "neutralized_long_short_delta": "not_computed_requires_neutralization_run",
    }
    return {
        "factor_validity": factor_validity,
        "strategy_performance": strategy_performance,
        "risk_exposure_independence": risk_exposure_independence,
    }


def to_report(result: dict, path: str | Path | None = None) -> Path:
    report_dir = Path(path) if path is not None else CONFIG.report_dir / result["summary"]["name"]
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "expr": _public_json(result["expr"]),
        "summary": _public_json(result["summary"]),
        "train_summary": _public_json(result.get("train_summary", {})),
        "data": _public_json(result.get("data", {})),
        "walk_forward": _public_json(result.get("walk_forward", {})),
        "tradability": _public_json(result.get("tradability", {})),
        "robustness_layers": _public_json(result.get("robustness_layers", {})),
        "robustness": _public_json(result.get("robustness", {})),
        "evaluation_layers": _public_json(_evaluation_layers(result)),
        "rank_ic": _series_records(result["rank_ic"]),
        "quantile_returns": _frame_records(result["quantile_returns"]),
        "long_short": _series_records(result["long_short"]),
        "turnover": _series_records(result["turnover"]),
        "net_long_short": _series_records(result["net_long_short"]),
    }
    json_path = report_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    _plot_report(result, report_dir)
    _write_factor_card(result, report_dir)
    return report_dir


def _format_metric(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "n/a" if value is None else str(value)
    if pd.isna(numeric):
        return "n/a"
    return f"{numeric:.6g}"


def _metadata_value(metadata: dict[str, Any], key: str) -> str:
    value = metadata.get(key)
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "n/a"
    return "n/a" if value in (None, "") else str(value)


def _write_factor_card(result: dict, report_dir: Path) -> None:
    expr = result["expr"]
    metadata = expr.get("metadata", {}) or {}
    summary = result.get("summary", {})
    train = result.get("train_summary", {})
    data = result.get("data", {})
    walk_forward = result.get("walk_forward", {})
    tradability = result.get("tradability", {})
    robustness = result.get("robustness", {})
    tradable_summary = tradability.get("tradable_summary", {}) if isinstance(tradability, dict) else {}
    layers = _evaluation_layers(result)
    factor_validity = layers["factor_validity"]
    strategy = layers["strategy_performance"]
    risk = layers["risk_exposure_independence"]
    fields = expr.get("fields_used", [])

    lines = [
        f"# {expr.get('name', 'factor')}",
        "",
        f"- Expression: `{expr.get('expression', '')}`",
        f"- Fields: `{', '.join(fields)}`",
        f"- Economic rationale: {expr.get('economic_rationale', 'n/a')}",
        f"- Alpha target: {_metadata_value(metadata, 'alpha_target')}",
        f"- Economic mechanism: {_metadata_value(metadata, 'economic_mechanism')}",
        f"- Risk exposures: {_metadata_value(metadata, 'risk_exposures')}",
        f"- Backtestable status: {_metadata_value(metadata, 'backtestable_status')}",
        f"- Status reason: {_metadata_value(metadata, 'status_reason')}",
        f"- Validation notes: {_metadata_value(metadata, 'validation_notes')}",
        "",
        "## Data",
        "",
        f"- Mode: `{data.get('data_mode', 'unknown')}`",
        f"- Date range: `{data.get('start_date', 'n/a')}` to `{data.get('end_date', 'n/a')}`",
        f"- Train end: `{data.get('train_end', summary.get('train_end', 'n/a'))}`",
        f"- Universe: `{data.get('universe', 'n/a')}`",
        f"- Forward return: `{data.get('forward_column', 'n/a')}`",
        f"- Cost bps: `{data.get('cost_bps', summary.get('cost_bps', 'n/a'))}`",
        "",
        "## Factor Validity",
        "",
        f"- Train Rank IC mean: `{_format_metric(factor_validity.get('train_rank_ic_mean'))}`",
        f"- OOS Rank IC mean: `{_format_metric(factor_validity.get('oos_rank_ic_mean'))}`",
        f"- OOS Rank IC std: `{_format_metric(factor_validity.get('oos_rank_ic_std'))}`",
        f"- OOS ICIR: `{_format_metric(factor_validity.get('oos_icir'))}`",
        f"- OOS IC positive rate: `{_format_metric(factor_validity.get('oos_ic_positive_rate'))}`",
        f"- OOS IC t-stat: `{_format_metric(factor_validity.get('oos_ic_t_stat'))}`",
        f"- OOS IC p-value normal approx: `{_format_metric(factor_validity.get('oos_ic_pvalue_normal_approx'))}`",
        f"- OOS IC observations: `{factor_validity.get('oos_ic_observation_days', 'n/a')}` days, `{factor_validity.get('oos_observation_rows', 'n/a')}` rows",
        f"- Quantile monotonicity: `{factor_validity.get('quantile_monotonicity', 'n/a')}`",
        f"- Quantile spread mean: `{_format_metric(factor_validity.get('quantile_spread_mean'))}`",
        f"- Long-short mean: `{_format_metric(factor_validity.get('long_short_mean'))}`",
        f"- Coverage ratio: `{_format_metric(factor_validity.get('coverage_ratio'))}`",
        f"- Missing ratio: `{_format_metric(factor_validity.get('missing_ratio'))}`",
        f"- Extreme value ratio: `{_format_metric(factor_validity.get('extreme_value_ratio'))}`",
        f"- Turnover mean: `{_format_metric(factor_validity.get('turnover_mean'))}`",
        f"- IC inference note: {factor_validity.get('inference_note', 'n/a')}",
        "",
        "## Strategy Performance",
        "",
        f"- Gross long-short mean: `{_format_metric(strategy.get('gross_long_short_mean'))}`",
        f"- Net long-short mean: `{_format_metric(strategy.get('net_long_short_mean'))}`",
        f"- Turnover mean: `{_format_metric(strategy.get('turnover_mean'))}`",
        f"- Cost bps: `{strategy.get('cost_bps', 'n/a')}`",
        f"- Cost convention: {strategy.get('cost_convention', 'n/a')}",
        f"- Tradable net long-short mean: `{_format_metric(strategy.get('tradable_net_long_short_mean'))}`",
        f"- Executable net long-short mean: `{_format_metric(strategy.get('executable_net_long_short_mean'))}`",
        f"- Fill rate mean: `{_format_metric(strategy.get('fill_rate_mean'))}`",
        f"- Impact cost mean: `{_format_metric(strategy.get('impact_cost_mean'))}`",
        f"- Detailed total cost mean: `{_format_metric(strategy.get('detailed_cost_total_mean'))}`",
        f"- Impact coverage mean: `{_format_metric(strategy.get('impact_coverage_mean'))}`",
        f"- Detailed cost component means: `{strategy.get('detailed_cost_component_means', 'n/a')}`",
        f"- Cost model assumptions: `{strategy.get('cost_model_assumptions', 'n/a')}`",
        f"- Blocked buy notional: `{_format_metric(strategy.get('blocked_buy_notional'))}`",
        f"- Blocked sell notional: `{_format_metric(strategy.get('blocked_sell_notional'))}`",
        f"- Partial fill notional: `{_format_metric(strategy.get('partial_fill_notional'))}`",
        f"- Dropped observations: `{strategy.get('dropped_observations', 'n/a')}`",
        f"- Annualized return: `{strategy.get('annualized_return', 'n/a')}`",
        f"- Excess return: `{strategy.get('excess_return', 'n/a')}`",
        f"- Max drawdown: `{strategy.get('max_drawdown', 'n/a')}`",
        f"- Sharpe ratio: `{strategy.get('sharpe_ratio', 'n/a')}`",
        f"- Information ratio: `{strategy.get('information_ratio', 'n/a')}`",
        "",
        "## Risk Exposure And Independence",
        "",
        f"- Declared risk exposures: `{_metadata_value({'risk_exposures': risk.get('declared_risk_exposures')}, 'risk_exposures')}`",
        f"- Similarity risk: `{risk.get('similarity_risk', 'n/a')}`",
        f"- Nearest factor: `{risk.get('nearest_factor', 'n/a')}`",
        f"- Max abs existing correlation: `{_format_metric(risk.get('max_abs_existing_corr'))}`",
        f"- Regime dependency: `{risk.get('regime_dependency', 'n/a')}`",
        f"- Market regime stability: `{risk.get('market_regime_stability', 'n/a')}`",
        f"- Universe stability: `{risk.get('universe_stability', 'n/a')}`",
        f"- Industry stability: `{risk.get('industry_stability', 'n/a')}`",
        f"- Style stability: `{risk.get('style_stability', 'n/a')}`",
        f"- Rebalance frequency stability: `{risk.get('rebalance_frequency_stability', 'n/a')}`",
        f"- Market beta exposure: `{risk.get('market_beta_exposure', 'n/a')}`",
        f"- Size/style exposure: `{risk.get('size_style_exposure', 'n/a')}`",
        f"- Neutralized Rank IC delta: `{risk.get('neutralized_rank_ic_delta', 'n/a')}`",
        "",
        "## Walk Forward",
        "",
        f"- Status: `{walk_forward.get('status', 'n/a')}`",
        f"- Usable windows: `{walk_forward.get('usable_windows', 'n/a')}`",
        f"- Positive IC windows: `{walk_forward.get('positive_ic_windows', 'n/a')}`",
        f"- Negative IC windows: `{walk_forward.get('negative_ic_windows', 'n/a')}`",
        "",
        "## Robustness",
        "",
        f"- Summary: {robustness.get('robustness_summary', 'n/a') if isinstance(robustness, dict) else 'n/a'}",
        f"- Similarity risk: `{robustness.get('similarity_risk', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Overfit risk: `{robustness.get('overfit_risk', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Walk-forward stability: `{robustness.get('walk_forward_stability', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Regime dependency: `{robustness.get('regime_dependency', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Market regime stability: `{robustness.get('market_regime_stability', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Industry stability: `{robustness.get('industry_stability', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Rebalance frequency stability: `{robustness.get('rebalance_frequency_stability', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Cost sensitivity: `{robustness.get('cost_sensitivity', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        f"- Horizon stability: `{robustness.get('horizon_stability', 'n/a') if isinstance(robustness, dict) else 'n/a'}`",
        "",
        "## Tradability",
        "",
        f"- Constraints: `{', '.join(tradability.get('constraints', [])) if isinstance(tradability, dict) else 'n/a'}`",
        f"- Dropped observations: `{tradability.get('dropped_observations', 'n/a') if isinstance(tradability, dict) else 'n/a'}`",
        f"- Ideal net long-short mean: `{_format_metric(tradability.get('ideal_net_long_short_mean') if isinstance(tradability, dict) else None)}`",
        f"- Tradable net long-short mean: `{_format_metric(tradable_summary.get('net_long_short_mean'))}`",
        f"- Executable net long-short mean: `{_format_metric(tradability.get('executable_net_long_short_mean') if isinstance(tradability, dict) else None)}`",
        f"- Fill rate mean: `{_format_metric(tradability.get('fill_rate_mean') if isinstance(tradability, dict) else None)}`",
        f"- Impact cost mean: `{_format_metric(tradability.get('impact_cost_mean') if isinstance(tradability, dict) else None)}`",
        f"- Detailed total cost mean: `{_format_metric(tradability.get('cost_total_mean') if isinstance(tradability, dict) else None)}`",
        f"- Impact coverage mean: `{_format_metric(tradability.get('impact_coverage_mean') if isinstance(tradability, dict) else None)}`",
        "",
    ]
    (report_dir / "factor_card.md").write_text("\n".join(lines), encoding="utf-8")


def _plot_report(result: dict, report_dir: Path) -> None:
    ic = result["rank_ic"]
    qret = result["quantile_returns"]
    net = result["net_long_short"]

    fig, axes = plt.subplots(3, 1, figsize=(9, 10), constrained_layout=True)
    if not ic.empty:
        ic.cumsum().plot(ax=axes[0], title="Cumulative Rank IC")
    axes[0].axhline(0, color="black", linewidth=0.8)

    if not qret.empty:
        qret.mean().plot(kind="bar", ax=axes[1], title="Mean Forward Return by Quantile")
    axes[1].axhline(0, color="black", linewidth=0.8)

    if not net.empty:
        (1 + net.fillna(0)).cumprod().plot(ax=axes[2], title="Net Long-Short Equity Curve")
    axes[2].axhline(1, color="black", linewidth=0.8)

    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.savefig(report_dir / "summary.png", dpi=160)
    plt.close(fig)
