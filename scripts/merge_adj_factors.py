"""把复权因子事件记录展开并合并进日行情 → data/raw/prices.pkl。

前置:
  python scripts/mssql_tool.py --env-file config/mssql.env \
      export --sql-file sql/export_prices.sql      --output data/raw/prices_raw.pkl
  python scripts/mssql_tool.py --env-file config/mssql.env \
      export --sql-file sql/export_adj_factors.sql --output data/raw/adj_factors.csv

复权因子表是**事件记录**(每次除权除息一行,自 ex_date 起生效),用
merge_asof(direction="backward") 取每个交易日之前最近一次的因子。ex_date 早于样本
起点的股票没有匹配,填 1.0。

**不要试图在 SQL 里用 OUTER APPLY 关联日行情取最近一条因子** —— 实测 580 万行跑 16 分钟
未出结果(关联列无合适索引),而因子表仅 3.8 万行、单独导出 4 秒。见 sql/export_prices.sql。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import CONFIG  # noqa: E402


def main() -> None:
    raw = CONFIG.raw_dir
    prices = pd.read_pickle(raw / "prices_raw.pkl")
    prices["date"] = pd.to_datetime(prices["date"])
    print(f"[行情] {prices.shape}  {prices.date.min().date()} ~ {prices.date.max().date()}")

    adj = pd.read_csv(raw / "adj_factors.csv")
    adj["ex_date"] = pd.to_datetime(adj["ex_date"])
    adj = adj.dropna(subset=["adj_factor"]).sort_values(["code", "ex_date"])
    print(f"[复权] {adj.shape}  覆盖 {adj.code.nunique()} 只股票")

    merged = pd.merge_asof(
        prices.sort_values("date"),
        adj.sort_values("ex_date")[["code", "ex_date", "adj_factor"]],
        left_on="date", right_on="ex_date", by="code", direction="backward",
    )
    merged["adj_factor"] = merged["adj_factor"].fillna(1.0)
    merged = merged.drop(columns=["ex_date"])

    # 量化未复权造成的污染(写进论文的局限/修正说明)
    m = merged.sort_values(["code", "date"])
    g = m.groupby("code", sort=False)
    ret_raw = g["close"].pct_change().to_numpy()
    ret_adj = g.apply(
        lambda x: (x["close"] * x["adj_factor"]).pct_change(), include_groups=False
    ).to_numpy()
    diff = pd.Series(abs(ret_adj - ret_raw))
    hit = diff > 1e-9
    print("\n=== 未复权造成的污染 ===")
    print(f"  受影响日观测 {hit.sum():,} / {len(m):,} ({hit.mean():.2%}),"
          f"涉及 {m.loc[hit.to_numpy(), 'code'].nunique():,} 只股票")
    print(f"  偏差 中位 {diff[hit].median():.4%} / 均值 {diff[hit].mean():.4%} / "
          f"90分位 {diff[hit].quantile(0.9):.4%} / 最大 {diff[hit].max():.2%}")
    print(f"  偏差超 5 个点 {int((diff > 0.05).sum()):,} 个(送转/高分红造成的假暴跌)")

    cols = ["date", "code", "open", "high", "low", "close", "vol", "amount", "adj_factor"]
    out_path = raw / "prices.pkl"
    merged[cols].to_pickle(out_path)
    print(f"\n[写出] {out_path}  {merged[cols].shape}")
    print("下一步:python -c 'from src.utils.data_loader import build_panel; build_panel()'")


if __name__ == "__main__":
    main()
