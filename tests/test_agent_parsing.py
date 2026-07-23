import json

import pytest

from src.agents.feedback import FeedbackBoundaryError, development_feedback, refine, sealed_oos_evidence
from src.agents.generate import propose_factors
from src.agents.json_utils import parse_llm_json
from src.factors.engine import FactorExpr


class StubClient:
    def __init__(self, response: str):
        self.response = response
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, prompt: str, system: str | None = None) -> str:
        self.calls += 1
        self.prompts.append(prompt)
        return self.response


def _backtest_payload(oos_ic: float = -0.2) -> dict:
    return {
        "train_summary": {
            "long_short_mean": 0.001,
            "net_long_short_mean": 0.0008,
            "turnover_mean": 0.2,
            "observations": 120,
        },
        "summary": {"ic_mean": oos_ic, "net_long_short_mean": -0.01, "observations": 60},
        "walk_forward": {"status": "consistent_negative_ic"},
        "data": {"data_mode": "synthetic"},
    }


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
    feedback = development_feedback(expr, _backtest_payload())

    refined = refine(expr, feedback, client=client)

    assert refined is not None
    assert refined.name == "profitability_value_blend"
    assert '"source": "dev_backtest"' in client.prompts[0]
    assert "-0.2" not in client.prompts[0]
    assert "ic_mean" not in client.prompts[0]


def test_refine_rejects_oos_evidence_before_calling_llm():
    client = StubClient("null")
    expr = FactorExpr("old", "rank(eps)", "old", ["eps"])
    evidence = sealed_oos_evidence(expr, _backtest_payload())

    with pytest.raises(FeedbackBoundaryError, match="sealed"):
        refine(expr, evidence, client=client)

    assert client.calls == 0
    assert client.prompts == []
