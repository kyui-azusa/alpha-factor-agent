# Factor Cards

## llm_mock_value_profit_blend

- Expression: `0.5 * rank(safe_div(eps, close)) + 0.5 * rank(safe_div(net_income, total_assets))`
- IC: `-0.004518972787969978`
- ICIR: `-0.05358870480836535`
- Turnover: `0.08919111197007502`
- Net long-short: `-0.00208635394505542`
- Max abs baseline corr: `0.8949433410890545`
- Economic rationale: 估值便宜且资产盈利能力较好的公司可能更有安全边际。

## llm_mock_cashflow_quality

- Expression: `rank(safe_div(operating_cash_flow, total_equity))`
- IC: `-0.0043238572820550585`
- ICIR: `-0.06772977375824783`
- Turnover: `0.11868614121947012`
- Net long-short: `-0.0006424850128760388`
- Max abs baseline corr: `0.3652612637949234`
- Economic rationale: 经营现金流相对权益更高可能表示盈利质量更扎实。
