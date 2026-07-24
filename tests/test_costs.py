import numpy as np
import pandas as pd

from src.backtest.costs import AShareCostModel, apply_execution_costs, execution_cost_ledger, stamp_duty_bps


def _weights() -> pd.Series:
    index = pd.MultiIndex.from_tuples(
        [
            ("2021-01-04", "A"),
            ("2021-01-04", "B"),
            ("2021-01-05", "A"),
            ("2021-01-05", "B"),
        ],
        names=["date", "code"],
    )
    index = index.set_levels(pd.to_datetime(index.levels[0]), level="date")
    return pd.Series([1.0, -1.0, -1.0, 1.0], index=index, name="weight")


def test_stamp_duty_uses_correct_basis_point_conversion_and_date_rule():
    rates = stamp_duty_bps(pd.to_datetime(["2023-08-27", "2023-08-28"]))

    assert rates.tolist() == [10.0, 5.0]


def test_execution_cost_ledger_charges_stamp_duty_only_on_sells():
    ledger = execution_cost_ledger(
        _weights(),
        model=AShareCostModel(
            commission_bps=0.0,
            slippage_bps=0.0,
            impact_bps_at_full_participation=0.0,
            annual_short_borrow_bps=0.0,
        ),
    )

    assert np.isclose(ledger.iloc[0]["buy_turnover"], 1.0)
    assert np.isclose(ledger.iloc[0]["sell_turnover"], 1.0)
    assert np.isclose(ledger.iloc[0]["stamp_duty_cost"], 0.001)
    assert np.isclose(ledger.iloc[1]["sell_turnover"], 2.0)
    assert np.isclose(ledger.iloc[1]["stamp_duty_cost"], 0.002)


def test_market_impact_is_nonlinear_in_participation_and_reports_coverage():
    weights = _weights().loc[pd.IndexSlice[[pd.Timestamp("2021-01-04")], :]]
    amounts = pd.Series([100_000_000.0, 1_000_000.0], index=weights.index)
    model = AShareCostModel(
        commission_bps=0.0,
        slippage_bps=0.0,
        annual_short_borrow_bps=0.0,
        portfolio_nav=1_000_000.0,
        impact_bps_at_full_participation=100.0,
    )

    ledger = execution_cost_ledger(weights, model=model, daily_amount=amounts)

    expected = (1.0 * 100.0 * np.sqrt(0.01) + 1.0 * 100.0 * np.sqrt(1.0)) / 10_000.0
    assert np.isclose(ledger.iloc[0]["market_impact_cost"], expected)
    assert ledger.iloc[0]["impact_coverage"] == 1.0


def test_missing_amount_charges_zero_impact_and_reports_zero_coverage():
    ledger = execution_cost_ledger(
        _weights(),
        model=AShareCostModel(impact_bps_at_full_participation=100.0),
    )

    assert np.allclose(ledger["market_impact_cost"], 0.0)
    assert np.allclose(ledger["impact_coverage"], 0.0)


def test_impact_coverage_is_weighted_by_traded_notional():
    weights = _weights().loc[pd.IndexSlice[[pd.Timestamp("2021-01-04")], :]]
    amounts = pd.Series([100_000_000.0, np.nan], index=weights.index)

    ledger = execution_cost_ledger(weights, daily_amount=amounts)

    assert np.isclose(ledger.iloc[0]["impact_coverage"], 0.5)


def test_borrow_cost_is_accrued_from_short_exposure_and_components_reconcile():
    model = AShareCostModel(
        commission_bps=3.0,
        slippage_bps=5.0,
        impact_bps_at_full_participation=0.0,
        annual_short_borrow_bps=252.0,
    )
    ledger = execution_cost_ledger(_weights(), model=model)
    components = ledger[
        ["commission_cost", "stamp_duty_cost", "slippage_cost", "market_impact_cost", "short_borrow_cost"]
    ].sum(axis=1)

    assert np.allclose(ledger["short_borrow_cost"], 0.0001)
    assert np.allclose(ledger["total_cost"], components)


def test_apply_execution_costs_subtracts_the_audited_total():
    gross = pd.Series([0.01, 0.02], index=pd.to_datetime(["2021-01-04", "2021-01-05"]), name="long_short")
    net, ledger = apply_execution_costs(gross, _weights(), model=AShareCostModel(impact_bps_at_full_participation=0.0))

    assert np.allclose(net, gross - ledger["total_cost"])
