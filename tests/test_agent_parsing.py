import json

from src.agents.feedback import refine
from src.agents.generate import propose_factors
from src.agents.json_utils import parse_llm_json
from src.factors.engine import FactorExpr


class StubClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls += 1
        return self.response


def test_parse_llm_json_accepts_fenced_json():
    raw = '```json\n[{"name": "factor"}]\n```'
    assert parse_llm_json(raw) == [{"name": "factor"}]


def test_propose_factors_accepts_json_with_intro_text():
    payload = [
        {
            "name": "cashflow_quality",
            "expression": "rank(safe_div(operating_cash_flow, total_equity))",
            "economic_rationale": "现金流质量更扎实。",
            "fields_used": ["operating_cash_flow", "total_equity"],
        }
    ]
    client = StubClient("Here is the JSON:\n" + json.dumps(payload, ensure_ascii=False))

    factors = propose_factors([], {"operating_cash_flow": "float64", "total_equity": "float64"}, n=1, client=client)

    assert factors[0].name == "cashflow_quality"
    assert client.calls == 1


def test_refine_accepts_fenced_factor_object():
    payload = {
        "name": "profitability_value_blend",
        "expression": "rank(safe_div(net_income, total_assets))",
        "economic_rationale": "资产盈利能力更高。",
        "fields_used": ["net_income", "total_assets"],
    }
    client = StubClient("```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```")
    expr = FactorExpr("old", "rank(eps)", "old", ["eps"])

    refined = refine(expr, {"summary": {"ic_mean": 0.01}}, client=client)

    assert refined is not None
    assert refined.name == "profitability_value_blend"
