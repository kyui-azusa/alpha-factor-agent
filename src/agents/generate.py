from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from src.agents.json_utils import factor_from_json, parse_llm_json
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.llm.prompts import GENERATE_FACTORS_PROMPT, GENERATE_FACTORS_SYSTEM


def _parse_json_array(raw: str) -> list:
    data = parse_llm_json(raw)
    if not isinstance(data, list):
        raise ValueError("LLM factor proposal must be a JSON array")
    return data


def _generation_params(client: Any) -> dict[str, Any]:
    params = getattr(client, "generation_params", None)
    if callable(params):
        return dict(params())
    return {"backend": "unknown"}


def _stamp_generation_metadata(factor: FactorExpr, proposal_rank: int, client: Any) -> None:
    metadata = factor.metadata
    generation = metadata.setdefault("generation", {})
    generation["params"] = _generation_params(client)
    generation["proposal_rank"] = proposal_rank
    record_getter = getattr(client, "generation_record", None)
    record = record_getter() if callable(record_getter) else None
    if record:
        generation["record"] = record
        generation["generation_record_id"] = record["generation_record_id"]
        generation["generated_at_utc"] = record["created_at_utc"]
        candidate_payload = json.dumps(
            {
                "generation_record_id": record["generation_record_id"],
                "proposal_rank": proposal_rank,
                "name": factor.name,
                "expression": factor.expression,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        generation["candidate_id"] = f"cand_{hashlib.sha256(candidate_payload.encode('utf-8')).hexdigest()[:24]}"
    else:
        generation.setdefault("generated_at_utc", datetime.now(UTC).isoformat())

    metadata.setdefault("source_seed_factors", metadata.get("seed_factors", []))
    metadata.setdefault("synthesis_method", metadata.get("generation_method", "unspecified"))
    metadata.setdefault("mechanism_change", "unspecified")
    metadata.setdefault("expression_version", "v1")
    metadata.setdefault(
        "lineage",
        {
            "source_seed_factors": metadata.get("source_seed_factors", []),
            "synthesis_method": metadata.get("synthesis_method", "unspecified"),
            "mechanism_change": metadata.get("mechanism_change", "unspecified"),
            "expression_version": metadata.get("expression_version", "v1"),
        },
    )


def propose_factors(existing_factors, field_dict, n: int = 5, client: LLMClient | None = None) -> list[FactorExpr]:
    client = client or LLMClient()
    prompt = GENERATE_FACTORS_PROMPT.format(existing_factors=existing_factors, generation_context=field_dict, n=n)
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
    for proposal_rank, item in enumerate(data[:n], start=1):
        factor = factor_from_json(item)
        _stamp_generation_metadata(factor, proposal_rank, client)
        factors.append(factor)
    return factors
