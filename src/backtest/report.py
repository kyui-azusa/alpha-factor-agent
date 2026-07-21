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


def to_report(result: dict, path: str | Path | None = None) -> Path:
    report_dir = Path(path) if path is not None else CONFIG.report_dir / result["summary"]["name"]
    report_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "expr": result["expr"],
        "summary": result["summary"],
        "rank_ic": _series_records(result["rank_ic"]),
        "quantile_returns": _frame_records(result["quantile_returns"]),
        "long_short": _series_records(result["long_short"]),
        "turnover": _series_records(result["turnover"]),
        "net_long_short": _series_records(result["net_long_short"]),
    }
    json_path = report_dir / "report.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")

    _plot_report(result, report_dir)
    return report_dir


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
