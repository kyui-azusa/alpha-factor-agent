from __future__ import annotations

import numpy as np
import pandas as pd


def _as_datetime(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def pit_merge(prices: pd.DataFrame, fundamentals: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time merge using only rows with ann_date <= trade date."""
    if prices.empty:
        return prices.copy()
    required_prices = {"date", "code"}
    required_fund = {"code", "ann_date"}
    missing = required_prices - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing columns: {sorted(missing)}")
    missing = required_fund - set(fundamentals.columns)
    if missing:
        raise ValueError(f"fundamentals missing columns: {sorted(missing)}")

    price_data = _as_datetime(prices, ("date",)).sort_values(["code", "date"]).reset_index(drop=True)
    fund_data = _as_datetime(fundamentals, ("ann_date", "report_period")).sort_values(
        ["code", "ann_date", "report_period"]
    )

    merged_parts: list[pd.DataFrame] = []
    fundamental_columns = [column for column in fund_data.columns if column != "code"]
    empty_fund = pd.DataFrame(columns=fundamental_columns)
    for code, price_group in price_data.groupby("code", sort=False):
        fund_group = fund_data.loc[fund_data["code"] == code, fundamental_columns]
        if fund_group.empty:
            fund_group = empty_fund.copy()
            fund_group["ann_date"] = pd.to_datetime(fund_group.get("ann_date"))
        merged = pd.merge_asof(
            price_group.sort_values("date"),
            fund_group.sort_values("ann_date"),
            left_on="date",
            right_on="ann_date",
            direction="backward",
            allow_exact_matches=True,
        )
        merged_parts.append(merged)

    return pd.concat(merged_parts, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)


def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    if s.dropna().empty:
        return s.copy()
    lo, hi = s.quantile([lower, upper])
    return s.clip(lo, hi)


def zscore(s: pd.Series) -> pd.Series:
    std = s.std(ddof=0)
    if pd.isna(std) or std == 0:
        return s * np.nan
    return (s - s.mean()) / std


def neutralize(factor: pd.Series, industry: pd.Series | None = None, mktcap: pd.Series | None = None) -> pd.Series:
    """Remove industry dummies and log market-cap exposure by cross-section."""
    data = pd.DataFrame({"factor": factor.astype(float)})
    if industry is not None:
        data["industry"] = industry
    if mktcap is not None:
        data["log_mktcap"] = np.log(pd.to_numeric(mktcap, errors="coerce").clip(lower=1.0))

    def regress(group: pd.DataFrame) -> pd.Series:
        y = group["factor"]
        valid = y.notna()
        x_parts = [pd.Series(1.0, index=group.index, name="const")]
        if "log_mktcap" in group:
            x_parts.append(group["log_mktcap"])
            valid &= group["log_mktcap"].notna()
        if "industry" in group:
            dummies = pd.get_dummies(group["industry"], prefix="industry", dtype=float)
            x_parts.append(dummies)
            valid &= group["industry"].notna()
        x = pd.concat(x_parts, axis=1)
        resid = pd.Series(np.nan, index=group.index, dtype=float)
        if valid.sum() <= 1:
            return resid
        x_valid = x.loc[valid]
        y_valid = y.loc[valid]
        beta, *_ = np.linalg.lstsq(x_valid.to_numpy(dtype=float), y_valid.to_numpy(dtype=float), rcond=None)
        resid.loc[valid] = y_valid - x_valid.to_numpy(dtype=float) @ beta
        return resid

    if isinstance(data.index, pd.MultiIndex) and "date" in data.index.names:
        return data.groupby(level="date", group_keys=False).apply(regress)
    return regress(data)
