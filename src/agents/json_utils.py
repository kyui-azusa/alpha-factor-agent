from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.factors.engine import FactorExpr


def parse_llm_json(raw: str) -> Any:
    """Parse JSON from common LLM response shapes without accepting broken JSON."""
    text = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    starts = [idx for idx, char in enumerate(text) if char in "[{"]
    for start in starts:
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        return value
    raise ValueError("No valid JSON object or array found in LLM response")


def factor_from_json(item: dict[str, Any]) -> "FactorExpr":
    from src.factors.engine import FactorExpr

    required = {"name", "expression", "economic_rationale", "fields_used"}
    missing = required - set(item)
    if missing:
        raise ValueError(f"factor JSON missing keys: {sorted(missing)}")
    if not isinstance(item["fields_used"], list) or not all(isinstance(field, str) for field in item["fields_used"]):
        raise ValueError("factor JSON fields_used must be a list of strings")
    return FactorExpr(
        name=str(item["name"]),
        expression=str(item["expression"]),
        economic_rationale=str(item["economic_rationale"]),
        fields_used=list(item["fields_used"]),
    )
