from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


TRADING_DAYS_PER_YEAR = 252


@dataclass(frozen=True)
class AShareCostModel:
    """Auditable A-share execution-cost assumptions, expressed in basis points."""

    commission_bps: float = 3.0
    slippage_bps: float = 5.0
    impact_bps_at_full_participation: float = 50.0
    annual_short_borrow_bps: float = 600.0
    portfolio_nav: float = 10_000_000.0
    stamp_duty_bps_override: float | None = None

    def to_dict(self) -> dict[str, float | None | str]:
        return {
            **asdict(self),
            "stamp_duty_rule": (
                "override"
                if self.stamp_duty_bps_override is not None
                else "sell-side 10 bps through 2023-08-27; 5 bps from 2023-08-28"
            ),
            "cost_unit": "portfolio return",
            "turnover_convention": "sum(abs(target_weight - previous_weight)); long-short gross exposure is 2",
        }


def stamp_duty_bps(dates: pd.Index, override: float | None = None) -> pd.Series:
    """Return the statutory sell-side stamp-duty rate for each trade date."""

    index = pd.DatetimeIndex(pd.to_datetime(dates))
    if override is not None:
        values = np.full(len(index), float(override))
    else:
        values = np.where(index >= pd.Timestamp("2023-08-28"), 5.0, 10.0)
    return pd.Series(values, index=index, name="stamp_duty_bps", dtype=float)


def weight_changes(target_weights: pd.Series) -> pd.DataFrame:
    """Convert target long-short weights into signed trades for every rebalance."""

    if not isinstance(target_weights.index, pd.MultiIndex) or list(target_weights.index.names)[:2] != ["date", "code"]:
        raise ValueError("target_weights must use MultiIndex[date, code]")
    weights = pd.to_numeric(target_weights, errors="coerce").fillna(0.0).sort_index()
    rows: list[pd.DataFrame] = []
    previous = pd.Series(dtype=float)
    for date, group in weights.groupby(level="date"):
        current = group.droplevel("date")
        aligned = pd.concat([previous.rename("previous_weight"), current.rename("target_weight")], axis=1).fillna(0.0)
        aligned["trade_weight"] = aligned["target_weight"] - aligned["previous_weight"]
        aligned["date"] = pd.Timestamp(date)
        aligned["code"] = aligned.index.astype(str)
        rows.append(aligned.reset_index(drop=True).set_index(["date", "code"]))
        previous = current
    if not rows:
        index = pd.MultiIndex.from_arrays([[], []], names=["date", "code"])
        return pd.DataFrame(columns=["previous_weight", "target_weight", "trade_weight"], index=index, dtype=float)
    return pd.concat(rows).sort_index()


def execution_cost_ledger(
    target_weights: pd.Series,
    model: AShareCostModel = AShareCostModel(),
    daily_amount: pd.Series | None = None,
) -> pd.DataFrame:
    """Calculate deterministic daily costs and expose every component.

    ``daily_amount`` is the market's daily traded amount in currency units. When it
    is absent, impact is reported as unavailable and charged as zero rather than
    silently inventing liquidity.
    """

    trades = weight_changes(target_weights)
    columns = [
        "buy_turnover",
        "sell_turnover",
        "gross_turnover",
        "commission_cost",
        "stamp_duty_cost",
        "slippage_cost",
        "market_impact_cost",
        "short_borrow_cost",
        "total_cost",
        "impact_coverage",
    ]
    if trades.empty:
        return pd.DataFrame(columns=columns, dtype=float)

    trade = trades["trade_weight"]
    trades["buy_weight"] = trade.clip(lower=0.0)
    trades["sell_weight"] = (-trade).clip(lower=0.0)
    trades["abs_trade_weight"] = trade.abs()
    trades["commission_cost"] = trades["abs_trade_weight"] * model.commission_bps / 10_000.0
    trades["slippage_cost"] = trades["abs_trade_weight"] * model.slippage_bps / 10_000.0

    duty = stamp_duty_bps(
        trades.index.get_level_values("date").unique(),
        override=model.stamp_duty_bps_override,
    )
    trades["stamp_duty_cost"] = trades["sell_weight"] * duty.reindex(
        trades.index.get_level_values("date")
    ).to_numpy() / 10_000.0

    if daily_amount is None:
        trades["market_impact_cost"] = 0.0
        trades["impact_available"] = False
    else:
        amount = pd.to_numeric(daily_amount, errors="coerce").reindex(trades.index)
        valid = amount > 0
        participation = (trades["abs_trade_weight"] * model.portfolio_nav / amount.where(valid)).clip(lower=0.0)
        impact_bps = model.impact_bps_at_full_participation * np.sqrt(participation)
        trades["market_impact_cost"] = (trades["abs_trade_weight"] * impact_bps / 10_000.0).where(valid, 0.0)
        trades["impact_available"] = valid
    trades["impact_covered_turnover"] = trades["abs_trade_weight"].where(trades["impact_available"], 0.0)

    trades["short_borrow_cost"] = (
        (-trades["target_weight"].clip(upper=0.0))
        * model.annual_short_borrow_bps
        / 10_000.0
        / TRADING_DAYS_PER_YEAR
    )
    daily = trades.groupby(level="date").agg(
        buy_turnover=("buy_weight", "sum"),
        sell_turnover=("sell_weight", "sum"),
        gross_turnover=("abs_trade_weight", "sum"),
        commission_cost=("commission_cost", "sum"),
        stamp_duty_cost=("stamp_duty_cost", "sum"),
        slippage_cost=("slippage_cost", "sum"),
        market_impact_cost=("market_impact_cost", "sum"),
        short_borrow_cost=("short_borrow_cost", "sum"),
        impact_covered_turnover=("impact_covered_turnover", "sum"),
    )
    daily["impact_coverage"] = daily["impact_covered_turnover"].div(daily["gross_turnover"].replace(0.0, np.nan))
    daily = daily.drop(columns="impact_covered_turnover")
    components = [
        "commission_cost",
        "stamp_duty_cost",
        "slippage_cost",
        "market_impact_cost",
        "short_borrow_cost",
    ]
    daily["total_cost"] = daily[components].sum(axis=1)
    return daily[columns]


def apply_execution_costs(
    gross_return: pd.Series,
    target_weights: pd.Series,
    model: AShareCostModel = AShareCostModel(),
    daily_amount: pd.Series | None = None,
) -> tuple[pd.Series, pd.DataFrame]:
    ledger = execution_cost_ledger(target_weights, model=model, daily_amount=daily_amount)
    costs = ledger["total_cost"].reindex(gross_return.index).fillna(0.0)
    net = pd.to_numeric(gross_return, errors="coerce") - costs
    net.name = "net_long_short"
    return net, ledger
