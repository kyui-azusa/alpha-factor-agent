from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.field_availability import attach_field_availability, build_pit_merge_metadata


PIT_AVAILABILITY_AUDIT_ATTR = "pit_availability_audit"
PIT_AVAILABILITY_RULE_VERSION = "2026.07.23.1"
MARKET_OPEN_TIME = pd.Timedelta(hours=9, minutes=30)
MARKET_CLOSE_TIME = pd.Timedelta(hours=15)


def _as_datetime(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def _require_naive_timestamps(values: pd.Series, name: str) -> None:
    if isinstance(values.dtype, pd.DatetimeTZDtype):
        raise ValueError(f"{name} must use timezone-naive Asia/Shanghai local timestamps")


def _signal_times(price_data: pd.DataFrame, signal_time: str | pd.Series) -> pd.Series:
    if isinstance(signal_time, str) and signal_time in price_data.columns:
        values = pd.to_datetime(price_data[signal_time], errors="raise")
    elif isinstance(signal_time, str):
        try:
            offset = pd.to_timedelta(signal_time)
        except ValueError as exc:
            raise ValueError("signal_time must be a prices column or a local time such as '15:00:00'") from exc
        if offset < pd.Timedelta(0) or offset >= pd.Timedelta(days=1):
            raise ValueError("signal_time local-time offset must be within one day")
        values = price_data["date"].dt.normalize() + offset
    elif isinstance(signal_time, pd.Series):
        if len(signal_time) != len(price_data):
            raise ValueError("signal_time series must have one value per prices row")
        values = pd.to_datetime(signal_time.reset_index(drop=True), errors="raise")
    else:
        raise TypeError("signal_time must be a prices column, local time string, or pandas Series")

    _require_naive_timestamps(values, "signal_time")
    if values.isna().any():
        raise ValueError("signal_time cannot contain missing values")
    if not values.dt.normalize().equals(price_data["date"].dt.normalize()):
        raise ValueError("each signal_time must fall on its corresponding prices date")
    return values


def _next_trading_dates(announcement_dates: pd.Series, trading_dates: pd.DatetimeIndex) -> pd.Series:
    positions = trading_dates.searchsorted(announcement_dates.to_numpy(), side="right")
    result = pd.Series(pd.NaT, index=announcement_dates.index, dtype="datetime64[ns]")
    resolvable = positions < len(trading_dates)
    if resolvable.any():
        result.loc[resolvable] = trading_dates.take(positions[resolvable]).to_numpy()
    return result


def _publication_status(exact_time: pd.Timestamp, trading_dates: set[pd.Timestamp]) -> str:
    publication_date = exact_time.normalize()
    if publication_date not in trading_dates:
        return "exact_non_trading_day"
    time_of_day = exact_time - publication_date
    if time_of_day < MARKET_OPEN_TIME:
        return "exact_pre_market"
    if time_of_day <= MARKET_CLOSE_TIME:
        return "exact_trading_session"
    return "exact_after_market"


def _prepare_availability(
    fundamentals: pd.DataFrame,
    trading_dates: pd.DatetimeIndex,
    availability_time_col: str | None,
) -> pd.DataFrame:
    out = fundamentals.copy()
    reserved = {"information_available_at", "publication_time_status"}
    conflicts = reserved & set(out.columns)
    if conflicts:
        raise ValueError(f"fundamentals contains reserved PIT columns: {sorted(conflicts)}")

    ann_dates = out["ann_date"].dt.normalize()
    if ann_dates.isna().any():
        raise ValueError("ann_date cannot contain missing values")
    if availability_time_col is None:
        exact_times = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns]")
    else:
        if availability_time_col not in out.columns:
            raise ValueError(f"fundamentals missing availability time column: {availability_time_col}")
        exact_times = pd.to_datetime(out[availability_time_col], errors="raise")
        _require_naive_timestamps(exact_times, availability_time_col)

    time_of_day = exact_times - exact_times.dt.normalize()
    exact = exact_times.notna() & time_of_day.ne(pd.Timedelta(0))
    if exact.any() and not exact_times.loc[exact].dt.normalize().equals(ann_dates.loc[exact]):
        raise ValueError(f"{availability_time_col} must fall on the matching ann_date")

    available_at = exact_times.where(exact)
    available_at.loc[~exact] = _next_trading_dates(ann_dates.loc[~exact], trading_dates)
    trading_date_set = set(trading_dates)
    statuses = pd.Series("date_only", index=out.index, dtype="string")
    statuses.loc[exact] = exact_times.loc[exact].map(lambda value: _publication_status(value, trading_date_set))
    out["information_available_at"] = available_at
    out["publication_time_status"] = statuses
    return out


def get_pit_availability_audit(df: pd.DataFrame) -> dict:
    raw = df.attrs.get(PIT_AVAILABILITY_AUDIT_ATTR, {})
    return dict(raw) if isinstance(raw, dict) else {}


def pit_merge(
    prices: pd.DataFrame,
    fundamentals: pd.DataFrame,
    *,
    signal_time: str | pd.Series,
    availability_time_col: str | None,
) -> pd.DataFrame:
    """Merge the latest disclosure available at each explicit signal timestamp."""
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

    price_data = _as_datetime(prices, ("date",)).reset_index(drop=True)
    _require_naive_timestamps(price_data["date"], "date")
    price_data["_pit_signal_time"] = _signal_times(price_data, signal_time)
    price_data = price_data.sort_values(["code", "date"]).reset_index(drop=True)
    trading_dates = pd.DatetimeIndex(price_data["date"].dt.normalize().drop_duplicates().sort_values())

    fund_data = _as_datetime(fundamentals, ("ann_date", "report_period"))
    fund_data = _prepare_availability(fund_data, trading_dates, availability_time_col)
    fund_data = fund_data.sort_values(
        ["code", "information_available_at", "report_period", "ann_date"], na_position="last"
    )

    merged_parts: list[pd.DataFrame] = []
    fundamental_columns = [column for column in fund_data.columns if column != "code"]
    empty_fund = pd.DataFrame(columns=fundamental_columns)
    for code, price_group in price_data.groupby("code", sort=False):
        fund_group = fund_data.loc[fund_data["code"] == code, fundamental_columns]
        fund_group = fund_group.loc[fund_group["information_available_at"].notna()]
        if fund_group.empty:
            fund_group = empty_fund.copy()
            fund_group["information_available_at"] = pd.to_datetime(
                fund_group.get("information_available_at")
            )
        merged = pd.merge_asof(
            price_group.sort_values("_pit_signal_time"),
            fund_group.sort_values("information_available_at"),
            left_on="_pit_signal_time",
            right_on="information_available_at",
            direction="backward",
            allow_exact_matches=True,
        )
        merged_parts.append(merged)

    merged_panel = pd.concat(merged_parts, ignore_index=True).sort_values(["date", "code"]).reset_index(drop=True)
    merged_panel = merged_panel.drop(columns="_pit_signal_time")
    status_counts = fund_data["publication_time_status"].value_counts(dropna=False).sort_index()
    matched_status_counts = (
        merged_panel["publication_time_status"].dropna().value_counts().sort_index()
        if "publication_time_status" in merged_panel
        else pd.Series(dtype="int64")
    )
    audit = {
        "rule_version": PIT_AVAILABILITY_RULE_VERSION,
        "signal_time": signal_time if isinstance(signal_time, str) else "per_row_series",
        "availability_time_column": availability_time_col,
        "total_announcement_records": int(len(fund_data)),
        "publication_status_counts": {str(key): int(value) for key, value in status_counts.items()},
        "conservative_delay_count": int((fund_data["publication_time_status"] == "date_only").sum()),
        "unresolved_date_only_count": int(
            (
                (fund_data["publication_time_status"] == "date_only")
                & fund_data["information_available_at"].isna()
            ).sum()
        ),
        "matched_panel_rows": int(merged_panel["information_available_at"].notna().sum()),
        "matched_panel_rows_by_publication_status": {
            str(key): int(value) for key, value in matched_status_counts.items()
        },
    }
    merged_panel = merged_panel.drop(columns=["information_available_at", "publication_time_status"])
    factor_fundamental_columns = [
        column
        for column in fundamental_columns
        if column not in {"information_available_at", "publication_time_status"}
    ]
    metadata = build_pit_merge_metadata(list(prices.columns), factor_fundamental_columns)
    merged_panel = attach_field_availability(merged_panel, metadata)
    merged_panel.attrs[PIT_AVAILABILITY_AUDIT_ATTR] = audit
    return merged_panel


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
