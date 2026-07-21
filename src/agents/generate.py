from __future__ import annotations

from src.agents.json_utils import factor_from_json, parse_llm_json
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.llm.prompts import GENERATE_FACTORS_PROMPT, GENERATE_FACTORS_SYSTEM


def _parse_json_array(raw: str) -> list:
    data = parse_llm_json(raw)
    if not isinstance(data, list):
        raise ValueError("LLM factor proposal must be a JSON array")
    return data


def propose_factors(existing_factors, field_dict, n: int = 5, client: LLMClient | None = None) -> list[FactorExpr]:
    client = client or LLMClient()
    prompt = GENERATE_FACTORS_PROMPT.format(existing_factors=existing_factors, field_dict=field_dict, n=n)
    last_error: Exception | None = None
    data = []
    for attempt in range(3):
        retry_note = "" if attempt == 0 else "\nPrevious output was invalid. Return JSON array only."
        raw = client.generate(prompt + retry_note, system=GENERATE_FACTORS_SYSTEM)
        try:
            data = _parse_json_array(raw)
            break
        except Exception as exc:
            last_error = exc
    else:
        raise ValueError(f"LLM factor proposal could not be parsed: {last_error}")
    factors = []
    for item in data[:n]:
        factors.append(factor_from_json(item))
    return factors
