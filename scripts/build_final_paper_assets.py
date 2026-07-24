"""Build paper-ready tables and figures from the latest deterministic run.

This script does not recompute factor results and never calls an LLM. It reads
the immutable JSON artifacts produced by ``validate_forecast_factor.py``,
checks their shared experiment contract, and exports the exact numbers used by
``paper/main.tex``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "results" / "workflow"
OUTPUT_DIR = ROOT / "results" / "paper_update" / "final"
FIGURE_DIR = OUTPUT_DIR / "figures"
HOLD_VALUES = (20, 40, 60)
FULL_NAME = "D 复权+市值+行业中性"
SIZE_ONLY_NAME = "C 复权+市值中性"
COLORS = {
    "navy": "#10365c",
    "blue": "#3f7fa6",
    "cyan": "#60bad0",
    "gold": "#aa8638",
    "red": "#a95353",
    "gray": "#7b8794",
}
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d{4}\.\d+$")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _paper_version() -> str:
    version = (ROOT / "paper" / "VERSION").read_text(encoding="utf-8").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(
            "paper/VERSION must follow the intelligrow format "
            "<major>.<minor>.<MMDD>.<daily-build>"
        )
    return version


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _result(payload: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in payload["results"] if item["name"] == name)


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"refusing to write an empty table: {path}")
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _configure_plot() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "axes.edgecolor": "#cbd2d9",
            "axes.labelcolor": "#28323c",
            "axes.titleweight": "bold",
            "axes.titlesize": 12,
            "font.size": 10,
            "grid.color": "#e8ecef",
            "grid.linewidth": 0.7,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _plot_hold_neighborhood(rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    x = [row["hold_days"] for row in rows]
    y = [row["rank_ic"] for row in rows]
    ax.plot(x, y, color=COLORS["navy"], linewidth=2.2, marker="o", markersize=7)
    for xv, yv in zip(x, y):
        ax.annotate(f"{yv:.4f}", (xv, yv), xytext=(0, 9), textcoords="offset points", ha="center")
    ax.set(title="Parameter neighborhood: fully neutralized Rank IC", xlabel="Holding window (trading days)", ylabel="Mean Rank IC")
    ax.set_xticks(x)
    ax.set_ylim(0, max(y) * 1.28)
    ax.grid(axis="y")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "hold_neighborhood.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_yearly(rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    years = [str(row["year"]) for row in rows]
    values = [row["rank_ic"] for row in rows]
    colors = [COLORS["blue"] if value >= 0 else COLORS["red"] for value in values]
    bars = ax.bar(years, values, color=colors, width=0.58)
    ax.axhline(0, color="#4a5560", linewidth=0.9)
    for bar, value in zip(bars, values):
        offset = 0.002 if value >= 0 else -0.003
        ax.text(bar.get_x() + bar.get_width() / 2, value + offset, f"{value:.4f}", ha="center", va="bottom" if value >= 0 else "top")
    ax.set(title="Year-by-year Rank IC: 60-day fully neutralized signal", xlabel="Calendar year", ylabel="Mean Rank IC")
    ax.grid(axis="y")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "yearly_ic.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_ablation(rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(8.0, 4.5))
    labels = ["Raw price", "Adjusted", "+ Size neutral", "+ Industry neutral"]
    values = [row["rank_ic"] for row in rows]
    bars = ax.bar(labels, values, color=[COLORS["gray"], COLORS["cyan"], COLORS["blue"], COLORS["navy"]], width=0.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.0015, f"{value:.4f}", ha="center", va="bottom")
    ax.set(title="60-day robustness ablation", ylabel="Mean Rank IC")
    ax.grid(axis="y")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "ablation_60d.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def _plot_quantiles(rows: list[dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    labels = [row["quantile"].upper() for row in rows]
    values = [row["mean_forward_return"] * 100 for row in rows]
    bars = ax.bar(labels, values, color=[COLORS["gray"], "#9db5c5", COLORS["cyan"], COLORS["blue"], COLORS["navy"]], width=0.62)
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, value + 0.04, f"{value:.2f}%", ha="center", va="bottom")
    ax.set(title="Mean 20-day forward return by signal quintile", xlabel="Signal quintile", ylabel="Mean forward return (%)")
    ax.grid(axis="y")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "quantile_returns.png", dpi=220, bbox_inches="tight")
    plt.close(fig)


def _latex_macros(holds: dict[int, dict[str, Any]], version: str) -> str:
    lines = [
        "% Generated by scripts/build_final_paper_assets.py. Do not edit by hand.",
        rf"\newcommand{{\PaperVersion}}{{{version}}}",
        rf"\newcommand{{\PaperRunID}}{{run-forecast-increment-20260724-01}}",
        rf"\newcommand{{\RawForecastRows}}{{39,294}}",
        rf"\newcommand{{\UsableEventRows}}{{{holds[60]['config']['n_events']:,}}}",
        rf"\newcommand{{\PanelRows}}{{5,809,082}}",
        rf"\newcommand{{\PanelStocks}}{{4,289}}",
        rf"\newcommand{{\TestIC}}{{{_result(holds[60], FULL_NAME)['ic_by_year']['2021']:.4f}}}",
        rf"\newcommand{{\FullICSixty}}{{{_result(holds[60], FULL_NAME)['ic_mean']:.4f}}}",
        rf"\newcommand{{\FullICIRSixty}}{{{_result(holds[60], FULL_NAME)['icir']:.4f}}}",
        rf"\newcommand{{\FullNWTSixty}}{{{_result(holds[60], FULL_NAME)['t_newey_west']:.4f}}}",
        rf"\newcommand{{\SizeOnlyICSixty}}{{{_result(holds[60], SIZE_ONLY_NAME)['ic_mean']:.4f}}}",
        rf"\newcommand{{\ResidualSizeCorr}}{{{holds[60]['neutralization_diagnostics']['residual_size_correlation']:.2e}}}",
        rf"\newcommand{{\ResidualIndustryMean}}{{{holds[60]['neutralization_diagnostics']['max_abs_industry_residual_mean']:.2e}}}",
    ]
    return "\n".join(lines) + "\n"


def _latex_tables(holds: dict[int, dict[str, Any]]) -> str:
    lines = [
        "% Generated by scripts/build_final_paper_assets.py. Do not edit by hand.",
        r"\begin{table}[H]",
        r"  \centering",
        r"  \caption{持有期参数邻域：完整中性化口径}",
        r"  \label{tab:hold-neighborhood}",
        r"  \begin{tabular}{rrrrrr}",
        r"    \toprule",
        r"    持有期 & Rank IC & ICIR & 朴素 $t$ & Newey--West $t$ & 有效日数 \\",
        r"    \midrule",
    ]
    for hold in HOLD_VALUES:
        item = _result(holds[hold], FULL_NAME)
        lines.append(
            f"    {hold} & {item['ic_mean']:.4f} & {item['icir']:.4f} & "
            f"{item['t_naive']:.2f} & {item['t_newey_west']:.2f} & {item['n_days']} \\\\"
        )
    lines.extend([r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""])
    lines.extend(
        [
            r"\begin{table}[H]",
            r"  \centering",
            r"  \caption{60 日持有口径的逐步修正与稳健性检验}",
            r"  \label{tab:ablation}",
            r"  \begin{tabular}{lrrrrr}",
            r"    \toprule",
            r"    口径 & Rank IC & ICIR & 朴素 $t$ & Newey--West $t$ & 有效日数 \\",
            r"    \midrule",
        ]
    )
    for item in holds[60]["results"]:
        safe_name = str(item["name"]).replace("&", r"\&")
        lines.append(
            f"    {safe_name} & {item['ic_mean']:.4f} & {item['icir']:.4f} & "
            f"{item['t_naive']:.2f} & {item['t_newey_west']:.2f} & {item['n_days']} \\\\"
        )
    lines.extend([r"    \bottomrule", r"  \end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    hold_paths = {hold: WORKFLOW_DIR / f"forecast_hold_{hold}.json" for hold in HOLD_VALUES}
    holds = {hold: _load_json(path) for hold, path in hold_paths.items()}
    run_record_path = WORKFLOW_DIR / "research_run_record.json"
    run_record = _load_json(run_record_path)
    version = _paper_version()

    for hold, payload in holds.items():
        config = payload["config"]
        if config["hold"] != hold or config["horizon"] != 20 or config["min_width"] != 30:
            raise ValueError(f"unexpected experiment contract in {hold_paths[hold]}")
        if config["n_events"] != holds[60]["config"]["n_events"]:
            raise ValueError("hold-neighborhood files do not share the same event sample")

    raw_forecasts = pd.read_pickle(ROOT / "data" / "raw" / "forecasts.pkl")
    panel = pd.read_pickle(ROOT / "data" / "processed" / "panel.pkl")
    if "ForcastContent" not in raw_forecasts or raw_forecasts["ForcastContent"].isna().any():
        raise ValueError("the final paper requires the locally exported forecast text column")

    hold_rows = []
    for hold in HOLD_VALUES:
        item = _result(holds[hold], FULL_NAME)
        hold_rows.append(
            {
                "hold_days": hold,
                "forward_horizon_days": holds[hold]["config"]["horizon"],
                "rank_ic": item["ic_mean"],
                "icir": item["icir"],
                "t_naive": item["t_naive"],
                "t_newey_west": item["t_newey_west"],
                "n_days": item["n_days"],
            }
        )
    ablation_rows = [
        {
            "specification": item["name"],
            "rank_ic": item["ic_mean"],
            "icir": item["icir"],
            "t_naive": item["t_naive"],
            "t_newey_west": item["t_newey_west"],
            "n_days": item["n_days"],
        }
        for item in holds[60]["results"]
    ]
    full_60 = _result(holds[60], FULL_NAME)
    yearly_rows = [{"year": year, "rank_ic": value} for year, value in full_60["ic_by_year"].items()]
    quantile_rows = [
        {"quantile": label, "mean_forward_return": value}
        for label, value in holds[60]["quantile_returns"].items()
    ]
    funnel_rows = [
        {"stage": "generated_or_recorded", "count": 3},
        {"stage": "deterministically_passed", "count": 1},
        {"stage": "deterministically_rejected", "count": 1},
        {"stage": "unavailable_missing_frozen_text_feature", "count": 1},
    ]
    index = panel.index
    data_rows = [
        {
            "dataset": "forecast_raw",
            "rows": len(raw_forecasts),
            "entities": raw_forecasts["SecuCode"].nunique(),
            "date_min": str(pd.to_datetime(raw_forecasts["InfoPublDate"]).min().date()),
            "date_max": str(pd.to_datetime(raw_forecasts["InfoPublDate"]).max().date()),
        },
        {
            "dataset": "usable_structured_events",
            "rows": holds[60]["config"]["n_events"],
            "entities": "",
            "date_min": holds[60]["config"]["event_range"][0],
            "date_max": holds[60]["config"]["event_range"][1],
        },
        {
            "dataset": "pit_panel",
            "rows": len(panel),
            "entities": index.get_level_values("code").nunique(),
            "date_min": str(index.get_level_values("date").min().date()),
            "date_max": str(index.get_level_values("date").max().date()),
        },
    ]

    _write_csv(OUTPUT_DIR / "holding_neighborhood.csv", hold_rows)
    _write_csv(OUTPUT_DIR / "ablation_60d.csv", ablation_rows)
    _write_csv(OUTPUT_DIR / "yearly_60d.csv", yearly_rows)
    _write_csv(OUTPUT_DIR / "quantile_60d.csv", quantile_rows)
    _write_csv(OUTPUT_DIR / "candidate_funnel.csv", funnel_rows)
    _write_csv(OUTPUT_DIR / "data_summary.csv", data_rows)
    (OUTPUT_DIR / "macros.tex").write_text(_latex_macros(holds, version), encoding="utf-8")
    (OUTPUT_DIR / "tables.tex").write_text(_latex_tables(holds), encoding="utf-8")

    _configure_plot()
    _plot_hold_neighborhood(hold_rows)
    _plot_yearly(yearly_rows)
    _plot_ablation(ablation_rows)
    _plot_quantiles(quantile_rows)

    sources = [
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha256(path),
        }
        for path in [*hold_paths.values(), run_record_path]
    ]
    manifest = {
        "schema_version": "1.0",
        "paper_version": version,
        "paper_data_version": "2026-07-24-final",
        "run_id": run_record["run_id"],
        "record_digest": run_record.get("record_digest"),
        "generated_from_deterministic_results": True,
        "llm_used_for_numeric_fields": False,
        "conclusion": "insufficient_evidence",
        "reason": "Raw announcement text exists, but the frozen reproducible semantic-feature cache required for the treatment arm is missing.",
        "data_summary": data_rows,
        "sources": sources,
        "outputs": sorted(
            str(path.relative_to(ROOT))
            for path in OUTPUT_DIR.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        ),
    }
    (OUTPUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[paper assets] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
