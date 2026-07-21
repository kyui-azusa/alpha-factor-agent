from __future__ import annotations

import numpy as np
import pandas as pd


def _aligned_frame(factor: pd.Series, fwd_ret: pd.Series) -> pd.DataFrame:
    data = pd.concat([factor.rename("factor"), fwd_ret.rename("fwd_ret")], axis=1).dropna()
    if not isinstance(data.index, pd.MultiIndex) or "date" not in data.index.names:
        raise ValueError("factor and fwd_ret must use MultiIndex with a date level")
    return data.sort_index()


def rank_ic(factor: pd.Series, fwd_ret: pd.Series) -> pd.Series:
    data = _aligned_frame(factor, fwd_ret)

    def one_day(group: pd.DataFrame) -> float:
        if group["factor"].nunique() < 2 or group["fwd_ret"].nunique() < 2:
            return np.nan
        return group["factor"].rank().corr(group["fwd_ret"].rank())

    ic = data.groupby(level="date").apply(one_day)
    ic.name = "rank_ic"
    return ic.dropna()


def ic_ir(ic_series: pd.Series) -> float:
    clean = ic_series.dropna()
    std = clean.std(ddof=1)
    if clean.empty or pd.isna(std) or std == 0:
        return float("nan")
    return float(clean.mean() / std)


def _quantile_labels(group: pd.DataFrame, n: int) -> pd.Series:
    labels = pd.Series(np.nan, index=group.index, dtype=float)
    clean = group["factor"].dropna()
    unique_count = clean.nunique()
    bins = min(n, unique_count, len(clean))
    if bins < 2:
        return labels
    try:
        labels.loc[clean.index] = pd.qcut(clean.rank(method="first"), q=bins, labels=range(1, bins + 1)).astype(float)
    except ValueError:
        return labels
    return labels


def quantile_returns(factor: pd.Series, fwd_ret: pd.Series, n: int = 10) -> pd.DataFrame:
    data = _aligned_frame(factor, fwd_ret)
    data["quantile"] = data.groupby(level="date", group_keys=False).apply(lambda g: _quantile_labels(g, n))
    result = data.dropna(subset=["quantile"]).groupby([data.dropna(subset=["quantile"]).index.get_level_values("date"), "quantile"])[
        "fwd_ret"
    ].mean()
    table = result.unstack("quantile").sort_index()
    table.columns = [f"q{int(column)}" for column in table.columns]
    return table


def long_short_return(quantile_ret: pd.DataFrame) -> pd.Series:
    if quantile_ret.empty:
        return pd.Series(dtype=float, name="long_short")
    first = quantile_ret.columns[0]
    last = quantile_ret.columns[-1]
    ls = quantile_ret[last] - quantile_ret[first]
    ls.name = "long_short"
    return ls


def turnover(factor: pd.Series, n: int = 10) -> pd.Series:
    data = factor.rename("factor").dropna().to_frame().sort_index()
    if data.empty:
        return pd.Series(dtype=float, name="turnover")
    data["quantile"] = data.groupby(level="date", group_keys=False).apply(lambda g: _quantile_labels(g, n))
    weights_by_date: dict[pd.Timestamp, pd.Series] = {}
    for date, group in data.dropna(subset=["quantile"]).groupby(level="date"):
        low = group["quantile"].min()
        high = group["quantile"].max()
        holdings = pd.Series(0.0, index=group.index.get_level_values("code"))
        long_codes = group.loc[group["quantile"] == high].index.get_level_values("code")
        short_codes = group.loc[group["quantile"] == low].index.get_level_values("code")
        if len(long_codes) > 0:
            holdings.loc[long_codes] = 1.0 / len(long_codes)
        if len(short_codes) > 0:
            holdings.loc[short_codes] -= 1.0 / len(short_codes)
        weights_by_date[pd.Timestamp(date)] = holdings

    turns: list[tuple[pd.Timestamp, float]] = []
    previous: pd.Series | None = None
    for date in sorted(weights_by_date):
        current = weights_by_date[date]
        if previous is None:
            turns.append((date, float(current.abs().sum())))
        else:
            aligned = pd.concat([previous.rename("prev"), current.rename("curr")], axis=1).fillna(0.0)
            turns.append((date, float(aligned["curr"].sub(aligned["prev"]).abs().sum())))
        previous = current
    series = pd.Series(dict(turns)).sort_index()
    series.name = "turnover"
    return series
