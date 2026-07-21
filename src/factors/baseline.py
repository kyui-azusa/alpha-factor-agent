from __future__ import annotations

from src.factors.engine import FactorExpr


BASELINE_FACTORS: list[FactorExpr] = [
    FactorExpr(
        name="baseline_value_ep_bp",
        expression="0.5 * rank(safe_div(eps, close)) + 0.5 * rank(safe_div(book_value_per_share, close))",
        economic_rationale="盈利收益率和账面市值比更高的公司可能包含价值溢价。",
        fields_used=["eps", "book_value_per_share", "close"],
    ),
    FactorExpr(
        name="baseline_quality_roe",
        expression="rank(safe_div(net_income, total_equity))",
        economic_rationale="ROE 更高的公司通常具有更强盈利质量和资本使用效率。",
        fields_used=["net_income", "total_equity"],
    ),
    FactorExpr(
        name="baseline_momentum_20d",
        expression="rank(safe_div(delay(close, 1), delay(close, 21)) - 1)",
        economic_rationale="过去一个月表现更强的股票可能延续短期趋势。",
        fields_used=["close"],
    ),
    FactorExpr(
        name="baseline_low_volatility_20d",
        expression="rank(-ts_std(safe_div(delay(close, 1), delay(close, 2)) - 1, 20))",
        economic_rationale="低波动股票可能有更稳定的风险调整收益。",
        fields_used=["close"],
    ),
    FactorExpr(
        name="baseline_liquidity_turnover",
        expression="rank(-safe_div(delay(amount, 1), delay(mktcap, 1)))",
        economic_rationale="成交额占市值较低可近似表示交易拥挤度较低或流动性风险补偿。",
        fields_used=["amount", "mktcap"],
    ),
]


BASELINE_BY_NAME = {factor.name: factor for factor in BASELINE_FACTORS}
