"""跑 5 个基线因子,输出训练段/样本外两段指标,作为论文第五章的对照组。"""

from __future__ import annotations

import json

import pandas as pd

from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import CONFIG
from src.factors.baseline import BASELINE_FACTORS
from src.utils.data_loader import build_panel, get_forward_returns, load_prices


COLUMNS = ["name", "segment", "start_date", "end_date", "observations", "ic_mean", "ic_ir", "long_short_mean", "turnover_mean", "net_long_short_mean"]


def main() -> None:
    cfg = CONFIG
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=True)
    fwd_ret = get_forward_returns(load_prices(cfg), periods=(5,))
    print(f"panel rows={len(panel)} columns={len(panel.columns)}")

    rows: list[dict] = []
    for expr in BASELINE_FACTORS:
        result = backtest(expr, panel, fwd_ret, cfg=cfg)
        to_report(result, cfg.report_dir / expr.name)
        rows.append(result["train_summary"])
        rows.append(result["summary"])
        train, oos = result["train_summary"], result["summary"]
        print(
            f"{expr.name:32s} train IC={train['ic_mean']:+.4f} ICIR={train['ic_ir']:+.3f} | "
            f"oos IC={oos['ic_mean']:+.4f} ICIR={oos['ic_ir']:+.3f}"
        )

    frame = pd.DataFrame(rows)[COLUMNS]
    out_csv = cfg.results_dir / "baseline_summary.csv"
    out_json = cfg.results_dir / "baseline_summary.json"
    frame.to_csv(out_csv, index=False)
    out_json.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsaved -> {out_csv}\nsaved -> {out_json}")


if __name__ == "__main__":
    main()
