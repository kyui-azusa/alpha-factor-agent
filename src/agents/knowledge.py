from __future__ import annotations

from typing import Any

from src.agents.knowledge_base import field_index, load_knowledge_base
from src.utils.field_availability import get_field_availability


SEED_FACTORS: list[dict[str, Any]] = [
    {
        "name": "value_ep_bp",
        "category": "value",
        "rationale": "盈利收益率和账面市值比提供估值安全边际。",
        "expression_template": "rank(safe_div(eps, close)) / rank(safe_div(book_value_per_share, close))",
        "fields": ["eps", "book_value_per_share", "close"],
        "direction": "higher is cheaper/value-tilted",
        "risks": ["行业估值差异", "低价陷阱", "财报滞后"],
        "status": "currently_backtestable",
    },
    {
        "name": "quality_roe",
        "category": "quality",
        "rationale": "权益盈利能力较高的公司通常具备更强资本使用效率。",
        "expression_template": "rank(safe_div(net_income, total_equity))",
        "fields": ["net_income", "total_equity"],
        "direction": "higher is better quality",
        "risks": ["杠杆放大", "一次性损益", "行业资本结构差异"],
        "status": "currently_backtestable",
    },
    {
        "name": "deleveraged_roe",
        "category": "quality",
        "rationale": "在 ROE 中扣除资产负债率影响,奖励真实盈利能力并惩罚杠杆驱动收益。",
        "expression_template": "rank(safe_div(net_income, total_equity)) - rank(1 - safe_div(total_equity, total_assets))",
        "fields": ["net_income", "total_equity", "total_assets"],
        "direction": "higher is better quality after leverage penalty",
        "risks": ["金融行业杠杆结构不可直接比较", "资产重估和会计口径差异"],
        "status": "currently_backtestable",
    },
    {
        "name": "operating_cash_flow_yield",
        "category": "cashflow_value",
        "rationale": "经营现金流相对市值更高,可能比会计利润更能反映可兑现的价值。",
        "expression_template": "rank(safe_div(operating_cash_flow, mktcap))",
        "fields": ["operating_cash_flow", "mktcap"],
        "direction": "higher is cheaper cash-flow yield",
        "risks": ["经营现金流季节性", "资本开支未扣除", "市值口径差异"],
        "status": "currently_backtestable",
    },
    {
        "name": "momentum_20d",
        "category": "price_behavior",
        "rationale": "短期趋势延续可能反映信息逐步扩散或资金行为惯性。",
        "expression_template": "rank(safe_div(delay(close, 1), delay(close, 21)) - 1)",
        "fields": ["close"],
        "direction": "higher is stronger prior momentum",
        "risks": ["反转风险", "事件冲击", "拥挤交易"],
        "status": "currently_backtestable",
    },
]


A_SHARE_PRIORS = [
    "财务字段必须通过 ann_date 做点时间合并; report_period 不能替代公告日。",
    "生成阶段不得读取真实历史数值、个股轨迹、未来收益或样本外回测结果。",
    "广义 Alpha 假设必须标注是否当前可回测; 缺字段或需外部数据的想法不能伪装成已回测因子。",
    "盈利质量、估值、动量、波动率、流动性等方向需说明经济机制和常见风险暴露。",
    "独立 Alpha 需要在行业、市值等风险中性化后再验证; 本阶段报告只给确定性基础指标。",
]


SYNTHESIS_METHODS: list[dict[str, str]] = [
    {
        "name": "complementary_blend",
        "description": "Blend two economically different seed signals, such as value plus quality, when the mechanism is additive.",
    },
    {
        "name": "conditional_gate",
        "description": "Use where() with an audited binary regime field to switch between two fixed signals; the regime definition is deterministic and lagged.",
    },
    {
        "name": "risk_adjustment",
        "description": "Keep the alpha mechanism but subtract a known risk exposure such as leverage, volatility, or crowding.",
    },
    {
        "name": "industry_relative",
        "description": "State that a mechanism should be compared within industry; only emit currently backtestable expressions when fields support it.",
    },
    {
        "name": "proxy_substitution",
        "description": "Replace an unavailable concept with a documented field proxy and mark mapping risk explicitly.",
    },
    {
        "name": "time_confirmation",
        "description": "Require a signal to persist through PIT-safe delays or rolling windows before ranking it.",
    },
    {
        "name": "reversal_trigger",
        "description": "Turn a seed signal into a contrarian candidate only when the economic rationale explains why reversal is expected.",
    },
]


def seed_factor_lineage() -> list[dict[str, Any]]:
    return [
        {
            "name": item["name"],
            "category": item["category"],
            "mechanism": item["rationale"],
            "fields": item["fields"],
            "expression_template": item["expression_template"],
        }
        for item in SEED_FACTORS
    ]


def field_catalog(panel) -> list[dict[str, Any]]:
    knowledge_fields = field_index()
    availability = get_field_availability(panel)
    catalog: list[dict[str, Any]] = []
    for column, dtype in panel.dtypes.items():
        record = knowledge_fields.get(column)
        if record is None or not record["backtestable"]:
            continue
        meta = availability.get(column, {})
        catalog.append(
            {
                "field": column,
                "label": record["label"],
                "dtype": str(dtype),
                "source": meta.get("source", record["source_id"]),
                "knowledge_source_id": record["source_id"],
                "source_table": record["source_table"],
                "available_date": meta.get("available_date", "unknown"),
                "pit_rule": meta.get("rule", "metadata missing"),
                "pit_protected": bool(meta.get("pit_protected", False)),
                "missing_policy": _missing_policy(column, meta),
                "usage_boundary": record["usage_boundary"],
                "risks": record["risks"],
            }
        )
    return catalog


def _missing_policy(column: str, meta: dict[str, Any]) -> str:
    source = meta.get("source")
    if source == "fundamentals":
        return "missing before first disclosed report or when vendor field is unavailable; do not infer future reports"
    if column in {"amount", "vol"}:
        return "missing or non-positive values fail tradability checks when those checks are enabled"
    if source == "derived":
        return "missing whenever any PIT-safe input is missing"
    return "drop missing values during deterministic evaluation; do not ask the LLM for raw NaN counts"


def generation_context(panel) -> dict[str, Any]:
    knowledge = load_knowledge_base()
    return {
        "knowledge_version": knowledge["knowledge_version"],
        "knowledge_scope": knowledge["scope"],
        "knowledge_sources": knowledge["sources"],
        "field_catalog": field_catalog(panel),
        "factor_priors": knowledge["factor_priors"],
        "institution_rules": knowledge["institution_rules"],
        "seed_factors": SEED_FACTORS,
        "seed_factor_lineage": seed_factor_lineage(),
        "synthesis_methods": SYNTHESIS_METHODS,
        "a_share_priors": A_SHARE_PRIORS,
        "allowed_statuses": [
            "theoretical_explainable",
            "fields_exist",
            "pit_available",
            "currently_backtestable",
            "requires_external_data",
            "field_missing",
            "mapping_unstable",
            "validation_needed",
        ],
    }
