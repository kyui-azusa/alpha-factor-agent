"""申万一级行业分类的点时间(PIT)展开。

`data/raw/industry.csv` 存的是**变更记录**而非快照:每行一次分类生效,
`info_publ_date` 起生效,`cancel_date` 起失效(空表示至今有效)。

为什么必须 PIT:2021 年申万改版把"采掘"拆成"煤炭/石油石化"、"化工"改名"基础化工"。
拿改版后的标签去中性化 2016 年的横截面,等于提前知道了分类结果 —— 这是一种隐蔽的
look-ahead。验证方式见 tests:同一只股票在 2020-06-01 应为「化工」,2021-12-01 应为
「基础化工」。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import CONFIG, Config


def load_industry_changes(cfg: Config = CONFIG) -> pd.DataFrame:
    """读取行业变更记录。列:code, info_publ_date, cancel_date, industry。"""
    path = cfg.raw_dir / "industry.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} 不存在。先跑:python scripts/mssql_tool.py --env-file config/mssql.env "
            f"export --sql-file sql/export_industry.sql --output data/raw/industry.csv"
        )
    chg = pd.read_csv(path)
    chg["info_publ_date"] = pd.to_datetime(chg["info_publ_date"])
    chg["cancel_date"] = pd.to_datetime(chg["cancel_date"])
    return chg


def expand_industry_pit(dates: pd.DatetimeIndex, cfg: Config = CONFIG) -> pd.Series:
    """把变更记录展开成 MultiIndex(date, code) -> industry。

    只有 date 落在 [info_publ_date, cancel_date) 内才赋值;区间外为缺失,
    **不做前向填充到生效日之前**(那会让分类提前可见)。
    """
    chg = load_industry_changes(cfg)
    frames = []
    for code, grp in chg.groupby("code", sort=False):
        grp = grp.sort_values("info_publ_date")
        for start, end, ind in grp[["info_publ_date", "cancel_date", "industry"]].itertuples(index=False):
            lo = dates.searchsorted(start, side="left")
            hi = len(dates) if pd.isna(end) else dates.searchsorted(end, side="left")
            if hi > lo:
                frames.append(pd.DataFrame({"date": dates[lo:hi], "code": code, "industry": ind}))
    if not frames:
        return pd.Series(dtype=object, name="industry")
    out = pd.concat(frames, ignore_index=True)
    # 区间若有重叠(数据源偶见),取最后生效的一条
    out = out.drop_duplicates(subset=["date", "code"], keep="last")
    return out.set_index(["date", "code"])["industry"].sort_index()
