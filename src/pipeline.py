from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.agents.loop import run_loop
from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import CONFIG, Config
from src.factors.baseline import BASELINE_FACTORS
from src.report_factors import export_summary
from src.research.preflight import ExecutionPermit, validate_execution_permit
from src.utils.data_loader import build_panel, get_forward_returns, load_prices


def run_baselines(cfg: Config = CONFIG, n_quantiles: int = 5) -> pd.DataFrame:
    panel = build_panel(cfg, save=True)
    fwd_ret = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))
    rows: list[dict] = []
    for expr in BASELINE_FACTORS:
        result = backtest(expr, panel, fwd_ret, cfg=cfg, n_quantiles=n_quantiles)
        to_report(result, cfg.report_dir / "baselines" / expr.name)
        rows.append(result["summary"])
    frame = pd.DataFrame(rows)
    path = cfg.report_dir / "baseline_summary.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    return frame


def run_project(
    cfg: Config = CONFIG,
    rounds: int = 1,
    per_round: int = 2,
    n_quantiles: int = 5,
    include_agent: bool = False,
    execution_permit: ExecutionPermit | None = None,
) -> dict:
    if include_agent:
        execution_permit = validate_execution_permit(execution_permit)
    cfg.ensure_dirs()
    baseline_summary = run_baselines(cfg, n_quantiles=n_quantiles)
    agent_results = (
        run_loop(
            rounds=rounds,
            per_round=per_round,
            cfg=cfg,
            execution_permit=execution_permit,
        )
        if include_agent
        else []
    )
    factor_summary, factor_summary_path = export_summary(cfg=cfg)
    manifest = {
        "baseline_count": int(len(baseline_summary)),
        "agent_factor_count": int(len(agent_results)),
        "factor_summary_rows": int(len(factor_summary)),
        "factor_summary_path": factor_summary_path,
        "reports_dir": str(cfg.report_dir),
        "factors_dir": str(cfg.factor_dir),
    }
    manifest_path = cfg.results_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the alpha-factor-agent reproducible pipeline.")
    parser.add_argument("--rounds", type=int, default=1, help="Agent loop rounds.")
    parser.add_argument("--per-round", type=int, default=2, help="Candidate factors per round.")
    parser.add_argument("--n-quantiles", type=int, default=5, help="Backtest quantile bucket count.")
    args = parser.parse_args(argv)
    manifest = run_project(
        CONFIG,
        rounds=args.rounds,
        per_round=args.per_round,
        n_quantiles=args.n_quantiles,
        include_agent=False,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
