from __future__ import annotations

import pandas as pd
import pytest

from scripts.export_panel_data import (
    apply_adjustment_factors,
    next_trading_days,
    sanitize_factor_payload,
)


def test_adjustment_events_are_expanded_backward_asof() -> None:
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2021-06-30", "2021-07-01", "2021-07-02"]),
            "code": ["000001.SZ"] * 3,
            "open": [10.0, 5.0, 5.5],
            "high": [10.0, 5.0, 5.5],
            "low": [10.0, 5.0, 5.5],
            "close": [10.0, 5.0, 5.5],
            "vol": [100, 100, 100],
        }
    )
    factors = pd.DataFrame(
        {
            "code": ["000001.SZ"],
            "ex_date": pd.to_datetime(["2021-07-01"]),
            "adj_factor": [2.0],
        }
    )

    result = apply_adjustment_factors(prices, factors).sort_values("date")

    assert result["close"].tolist() == [10.0, 10.0, 11.0]
    assert result["ret"].iloc[1] == pytest.approx(0.0)
    assert result["ret"].iloc[2] == pytest.approx(0.1)


def test_usable_from_is_next_trading_day_not_next_calendar_day() -> None:
    trading_days = pd.DatetimeIndex(pd.to_datetime(["2021-01-22", "2021-01-25"]))
    publications = pd.Series(pd.to_datetime(["2021-01-22", "2021-01-23"]))

    result = next_trading_days(publications, trading_days)

    assert result.dt.strftime("%Y-%m-%d").tolist() == ["2021-01-25", "2021-01-25"]
    assert (result > publications).all()


def test_factor_export_rejects_redacted_fields() -> None:
    with pytest.raises(AssertionError, match="redacted factor fields"):
        sanitize_factor_payload(
            {"id": "baseline", "category": "价值", "expression": "secret"}
        )


def test_factor_export_keeps_only_public_fields() -> None:
    result = sanitize_factor_payload(
        {"id": "baseline", "category": "价值", "ic_series": [], "internal_note": "drop"}
    )
    assert result == {"id": "baseline", "category": "价值", "ic_series": []}


def test_factor_export_rejects_tuned_weights() -> None:
    with pytest.raises(AssertionError, match="redacted factor fields"):
        sanitize_factor_payload({"id": "baseline", "weights": [0.2, 0.8]})
