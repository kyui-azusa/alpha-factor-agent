from __future__ import annotations

import numpy as np
import pandas as pd


def make_synthetic_data(
    start: str = "2020-01-01",
    end: str = "2021-12-31",
    codes: tuple[str, ...] = ("000001.SZ", "000002.SZ", "600000.SH", "600519.SH", "300001.SZ", "300750.SZ"),
    seed: int = 7,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create deterministic sample data for engineering validation only."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, end)
    industries = ["bank", "real_estate", "bank", "consumer", "tech", "tech"]

    price_rows: list[dict] = []
    for i, code in enumerate(codes):
        base = 15 + i * 6
        drift = 0.00015 + i * 0.00004
        noise = rng.normal(drift, 0.018 + i * 0.001, len(dates))
        close = base * np.exp(np.cumsum(noise))
        open_ = close * (1 + rng.normal(0, 0.004, len(dates)))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.018, len(dates)))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.018, len(dates)))
        vol = rng.lognormal(15.5 + i * 0.08, 0.25, len(dates))
        amount = vol * close
        shares = 8e8 + i * 1.5e8
        for j, date in enumerate(dates):
            price_rows.append(
                {
                    "date": date,
                    "code": code,
                    "open": open_[j],
                    "high": high[j],
                    "low": low[j],
                    "close": close[j],
                    "vol": vol[j],
                    "amount": amount[j],
                    "adj_factor": 1.0,
                    "mktcap": close[j] * shares,
                    "industry": industries[i % len(industries)],
                }
            )

    periods = pd.date_range("2019-12-31", end, freq="QE")
    fundamental_rows: list[dict] = []
    for i, code in enumerate(codes):
        shares = 8e8 + i * 1.5e8
        equity_base = 6e9 + i * 1.2e9
        for k, period in enumerate(periods):
            ann_date = period + pd.Timedelta(days=42 + (i % 4) * 3)
            growth = 1 + 0.018 * k + i * 0.006
            total_equity = equity_base * growth
            net_income = total_equity * (0.018 + i * 0.0015 + rng.normal(0, 0.001))
            revenue = total_equity * (0.16 + i * 0.012 + rng.normal(0, 0.004))
            total_assets = total_equity * (1.8 + i * 0.08)
            ocf = net_income * (0.8 + rng.normal(0, 0.08))
            fundamental_rows.append(
                {
                    "code": code,
                    "report_period": period,
                    "ann_date": ann_date,
                    "total_assets": total_assets,
                    "total_equity": total_equity,
                    "net_income": net_income,
                    "revenue": revenue,
                    "operating_cash_flow": ocf,
                    "shares_outstanding": shares,
                    "book_value_per_share": total_equity / shares,
                    "eps": net_income / shares,
                }
            )

    universe = pd.MultiIndex.from_product([dates, codes], names=["date", "code"]).to_frame(index=False)
    universe["weight"] = 1.0 / len(codes)
    return pd.DataFrame(price_rows), pd.DataFrame(fundamental_rows), universe
