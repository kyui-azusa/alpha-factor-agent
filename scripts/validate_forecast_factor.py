"""业绩预告"幅度"因子的确定性验证 —— 增量检验的**对照组**(ADR-0022)。

本脚本只用聚源已公开的结构化字段(EGrowthRateFloor/Ceiling)构造因子,不调用任何 LLM。
它给出的是 baseline;文本语义因子的增量应相对本结果衡量。

四档对照,逐步加修正,用于展示每一步裁决的影响:
  A 未复权              —— 旧口径,复现修正前的数字
  B 复权                —— 只加复权
  C 复权 + 市值中性
  D 复权 + 市值 + 行业中性 —— 完整口径,论文采用

用法:
  python scripts/validate_forecast_factor.py --events data/raw/forecasts.pkl

事件文件由下列 SQL 导出(列名见 load_events):
  SELECT f.CompanyCode, s.SecuCode, s.SecuMarket, f.InfoPublDate, f.EndDate, f.ForcastType,
         f.EGrowthRateFloor, f.EGrowthRateCeiling, f.EProfitFloor, f.EProfitCeiling,
         f.LastProfit, f.NPYOYConsistentForecast, CAST(f.ForcastContent AS varchar(max)) AS ForcastContent
  FROM JYDB.dbo.LC_PerformanceForecast f
  JOIN JYDB.dbo.SecuMain s ON s.CompanyCode = f.CompanyCode
  WHERE s.SecuCategory = 1 AND s.SecuMarket IN (83, 90)

统计口径:持有期与前向收益重叠会让朴素 t 值高估三到四倍,**必须看 Newey-West 修正值**。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.metrics import ic_ir, quantile_returns, rank_ic  # noqa: E402
from src.config import CONFIG  # noqa: E402
from src.utils.align import neutralize, winsorize  # noqa: E402
from src.utils.industry import expand_industry_pit  # noqa: E402


def load_events(path: Path, trading_days: pd.DatetimeIndex) -> pd.DataFrame:
    fc = pd.read_pickle(path) if path.suffix == ".pkl" else pd.read_csv(path)
    fc["InfoPublDate"] = pd.to_datetime(fc["InfoPublDate"])
    fc["EndDate"] = pd.to_datetime(fc["EndDate"])
    fc["code"] = fc["SecuCode"].astype(str).str.zfill(6) + fc["SecuMarket"].map({90: ".SZ", 83: ".SH"})
    fc = fc.drop_duplicates(subset=["code", "InfoPublDate", "EndDate", "EGrowthRateFloor",
                                    "EGrowthRateCeiling", "EProfitFloor"])
    # 同一天对多个报告期发预告时只留最近报告期,避免把下一年度指引当作当期业绩
    fc = fc.sort_values(["code", "InfoPublDate", "EndDate"]).groupby(
        ["code", "InfoPublDate"], as_index=False).first()
    fc["growth_mid"] = (fc["EGrowthRateFloor"] + fc["EGrowthRateCeiling"]) / 2.0
    fc = fc.dropna(subset=["growth_mid"])

    # PIT:披露日的**下一个交易日**才可用。披露时间粒度不一致(部分记录无时刻),
    # 故取保守规则,不假设盘中可用。
    pos = trading_days.searchsorted(fc["InfoPublDate"].to_numpy(), side="right")
    keep = pos < len(trading_days)
    fc = fc.loc[keep].copy()
    fc["eff_date"] = trading_days[pos[keep]]
    assert (fc["eff_date"] > fc["InfoPublDate"]).all(), "生效日必须严格晚于披露日"
    return fc


def expand_events(fc: pd.DataFrame, trading_days: pd.DatetimeIndex, hold: int) -> pd.Series:
    """事件展开成面板:自生效日起持有 hold 个交易日,期内若有新预告以最新一条为准。"""
    day_idx = {d: i for i, d in enumerate(trading_days)}
    rows = []
    for code, publ, eff, g in fc[["code", "InfoPublDate", "eff_date", "growth_mid"]].itertuples(index=False):
        i0 = day_idx[eff]
        for d in trading_days[i0: i0 + hold]:
            rows.append((d, code, g, publ))
    exp = pd.DataFrame(rows, columns=["date", "code", "growth_mid", "publ"])
    exp = exp.sort_values(["date", "code", "publ"]).groupby(["date", "code"], as_index=False).last()
    f = exp.set_index(["date", "code"])["growth_mid"].sort_index()
    return f.groupby(level="date").transform(lambda s: winsorize(s, 0.01, 0.99))


def newey_west_t(ic: pd.Series, lag: int) -> float:
    """重叠样本下的 t 值。lag 取前向收益期数。"""
    x = ic.to_numpy() - ic.mean()
    n = len(x)
    var = (x @ x) / n
    for k in range(1, lag + 1):
        var += 2 * (1.0 - k / (lag + 1)) * (x[k:] @ x[:-k]) / n
    return float(ic.mean() / np.sqrt(var / n))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True, help="业绩预告导出文件(.pkl 或 .csv)")
    ap.add_argument("--hold", type=int, default=60, help="持有交易日数")
    ap.add_argument("--horizon", type=int, default=20, help="前向收益期数")
    ap.add_argument("--min-width", type=int, default=30, help="计入 IC 的最小横截面")
    ap.add_argument("--out", default="results/forecast_baseline.json")
    args = ap.parse_args()

    panel = pd.read_pickle(CONFIG.processed_dir / "panel.pkl")
    trading_days = pd.DatetimeIndex(sorted(panel.index.get_level_values("date").unique()))
    print(f"[panel] {panel.shape}  {trading_days[0].date()} ~ {trading_days[-1].date()}")

    px = panel[["close", "adj_factor", "mktcap"]].reset_index().sort_values(["code", "date"])
    px["adj_close"] = px["close"] * px["adj_factor"]
    g = px.groupby("code", sort=False)
    px["fwd_raw"] = g["close"].shift(-args.horizon).to_numpy() / px["close"].to_numpy() - 1.0
    px["fwd_adj"] = g["adj_close"].shift(-args.horizon).to_numpy() / px["adj_close"].to_numpy() - 1.0
    px = px.set_index(["date", "code"]).sort_index()

    fc = load_events(Path(args.events), trading_days)
    print(f"[事件] {len(fc)} 条,{fc['code'].nunique()} 只,"
          f"{fc.InfoPublDate.min().date()} ~ {fc.InfoPublDate.max().date()}")

    factor = expand_events(fc, trading_days, args.hold)
    industry = expand_industry_pit(trading_days).reindex(factor.index)
    mktcap = px["mktcap"].reindex(factor.index)
    print(f"[面板] 观测 {len(factor):,},行业标签覆盖 {industry.notna().mean():.1%}")

    def neu(use_ind: bool, use_mc: bool) -> pd.Series:
        out = factor.groupby(level="date").apply(
            lambda s: neutralize(
                s.droplevel("date"),
                industry=industry.loc[s.index].droplevel("date") if use_ind else None,
                mktcap=mktcap.loc[s.index].droplevel("date") if use_mc else None,
            )
        )
        out.index.names = ["date", "code"]
        return out.sort_index()

    def run(name: str, f: pd.Series, ret: pd.Series) -> dict:
        ic = rank_ic(f, ret)
        width = f.groupby(level="date").size()
        ic = ic[width.reindex(ic.index).fillna(0) >= args.min_width]
        rec = {
            "name": name,
            "ic_mean": float(ic.mean()),
            "icir": float(ic_ir(ic)),
            "t_naive": float(ic.mean() / (ic.std() / np.sqrt(len(ic)))),
            "t_newey_west": newey_west_t(ic, args.horizon),
            "n_days": int(len(ic)),
            "ic_by_year": {str(k): float(v) for k, v in ic.groupby(ic.index.year).mean().items()},
        }
        print(f"  {name:<24} IC {rec['ic_mean']:+.4f}  ICIR {rec['icir']:+.3f}  "
              f"t朴素 {rec['t_naive']:5.2f}  t(NW) {rec['t_newey_west']:5.2f}  日 {rec['n_days']}")
        return rec

    print(f"\n{'=' * 92}\n业绩预告幅度因子 · 持有 {args.hold} 日 · 前向 {args.horizon} 日\n{'=' * 92}")
    results = [
        run("A 未复权", factor, px["fwd_raw"]),
        run("B 复权", factor, px["fwd_adj"]),
        run("C 复权+市值中性", neu(False, True), px["fwd_adj"]),
        run("D 复权+市值+行业中性", neu(True, True), px["fwd_adj"]),
    ]

    q = quantile_returns(neu(True, True), px["fwd_adj"], n=5).mean()
    print(f"\n--- D 口径 五分组 fwd_ret_{args.horizon} ---\n{q.to_string()}")
    print(f"  多空(Q5-Q1): {q.iloc[-1] - q.iloc[0]:.4%}")

    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": {"hold": args.hold, "horizon": args.horizon, "min_width": args.min_width,
                   "events": str(args.events), "n_events": int(len(fc)),
                   "event_range": [str(fc.InfoPublDate.min().date()), str(fc.InfoPublDate.max().date())],
                   "panel_range": [str(trading_days[0].date()), str(trading_days[-1].date())]},
        "results": results,
        "quantile_returns": {k: float(v) for k, v in q.items()},
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[写出] {out_path}")


if __name__ == "__main__":
    main()
