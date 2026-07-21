from __future__ import annotations

from src.agents.json_utils import factor_from_json, parse_llm_json
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.llm.prompts import FEEDBACK_PROMPT


def refine(expr: FactorExpr, backtest_result: dict, client: LLMClient | None = None) -> FactorExpr | None:
    client = client or LLMClient()
    raw = client.generate(FEEDBACK_PROMPT.format(factor=expr.to_dict(), summary=backtest_result.get("summary", {})))
    if raw.strip().lower() == "null":
        return None
    item = parse_llm_json(raw)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError("LLM feedback must return a factor JSON object or null")
    return factor_from_json(item)
