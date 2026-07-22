from __future__ import annotations

import pandas as pd


REGIME_FIELDS = (
    "market_return_20d_lagged",
    "market_volatility_20d_lagged",
    "regime_bull",
    "regime_high_vol",
)


def market_regime_by_date(
    panel: pd.DataFrame,
    *,
    trend_window: int = 20,
    volatility_window: int = 20,
    volatility_baseline_window: int = 60,
) -> pd.DataFrame:
    """Derive auditable market states using observations available no later than T-1."""

    if not isinstance(panel.index, pd.MultiIndex) or list(panel.index.names)[:2] != ["date", "code"]:
        raise ValueError("panel must use MultiIndex[date, code]")
    if "close" not in panel.columns:
        raise ValueError("panel must contain close to derive market regimes")
    if min(trend_window, volatility_window, volatility_baseline_window) <= 0:
        raise ValueError("market regime windows must be positive")

    close = pd.to_numeric(panel.sort_index()["close"], errors="coerce")
    stock_return = close.groupby(level="code", group_keys=False).pct_change(fill_method=None)
    market_return = stock_return.groupby(level="date").mean().sort_index()

    lagged_trend = market_return.rolling(trend_window, min_periods=trend_window).sum().shift(1)
    current_volatility = market_return.rolling(
        volatility_window,
        min_periods=volatility_window,
    ).std(ddof=0)
    lagged_volatility = current_volatility.shift(1)
    lagged_volatility_baseline = current_volatility.rolling(
        volatility_baseline_window,
        min_periods=volatility_window,
    ).mean().shift(1)

    regime = pd.DataFrame(
        {
            "market_return_20d_lagged": lagged_trend,
            "market_volatility_20d_lagged": lagged_volatility,
            "regime_bull": (lagged_trend > 0).where(lagged_trend.notna()).astype("Float64"),
            "regime_high_vol": (lagged_volatility > lagged_volatility_baseline)
            .where(lagged_volatility.notna() & lagged_volatility_baseline.notna())
            .astype("Float64"),
        }
    )
    regime.index.name = "date"
    return regime
