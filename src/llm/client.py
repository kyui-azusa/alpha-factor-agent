from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from src.config import CONFIG, Config


class LLMClient:
    def __init__(self, cfg: Config = CONFIG, backend: str | None = None):
        self.cfg = cfg
        self.backend = backend or cfg.llm_backend
        self.cache_dir = cfg.cache_dir / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0

    def generate(self, prompt: str, system: str | None = None) -> str:
        key = self._cache_key(prompt, system)
        path = self.cache_dir / f"{key}.txt"
        if path.exists():
            return path.read_text(encoding="utf-8")
        self.calls += 1
        if self.backend == "mock":
            response = self._mock_response(prompt)
        elif self.backend == "api":
            response = self._api_response(prompt, system, base_url=os.getenv("OPENAI_BASE_URL"), api_key=os.getenv("OPENAI_API_KEY"))
        elif self.backend == "local":
            response = self._api_response(
                prompt,
                system,
                base_url=os.getenv("ALPHA_AGENT_LOCAL_BASE_URL", "http://localhost:8000/v1"),
                api_key=os.getenv("ALPHA_AGENT_LOCAL_API_KEY", "EMPTY"),
            )
        else:
            raise ValueError(f"Unknown LLM backend: {self.backend}")
        path.write_text(response, encoding="utf-8")
        return response

    def generation_params(self) -> dict:
        return {
            "backend": self.backend,
            "model": self.cfg.llm_model,
            "max_tokens": self.cfg.llm_max_tokens,
            "temperature": self.cfg.llm_temperature,
        }

    def _cache_key(self, prompt: str, system: str | None) -> str:
        payload = json.dumps(
            {"system": system, "prompt": prompt, "generation_params": self.generation_params()},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _mock_response(self, prompt: str) -> str:
        if "duplicate" in prompt.lower():
            return '{"duplicate": false, "reason": "mock semantic validator does not see duplication"}'
        if "return null" in prompt.lower():
            return "null"
        return json.dumps(
            [
                {
                    "name": "llm_mock_cashflow_quality",
                    "expression": "rank(safe_div(operating_cash_flow, total_equity))",
                    "economic_rationale": "经营现金流相对权益更高可能表示盈利质量更扎实。",
                    "fields_used": ["operating_cash_flow", "total_equity"],
                    "metadata": {
                        "category": "quality",
                        "seed_factors": ["operating_cash_flow_yield", "quality_roe"],
                        "generation_method": "seed_factor_blend",
                        "alpha_target": "cash-backed quality premium",
                        "economic_mechanism": "cash flow relative to book equity may filter accounting-only profits",
                        "field_sources": {"operating_cash_flow": "fundamentals", "total_equity": "fundamentals"},
                        "a_share_mapping": "PIT-merged disclosed fundamentals; no future returns used",
                        "direction": "higher is better",
                        "scope": "single-stock cross-section",
                        "backtestable_status": "currently_backtestable",
                        "status_reason": "all fields exist in the PIT panel",
                        "risk_exposures": ["industry", "size", "working-capital seasonality"],
                        "validation_notes": "requires novelty and OOS validation before promotion",
                    },
                },
                {
                    "name": "llm_mock_value_profit_blend",
                    "expression": "0.5 * rank(safe_div(eps, close)) + 0.5 * rank(safe_div(net_income, total_assets))",
                    "economic_rationale": "估值便宜且资产盈利能力较好的公司可能更有安全边际。",
                    "fields_used": ["eps", "close", "net_income", "total_assets"],
                    "metadata": {
                        "category": "value_quality",
                        "seed_factors": ["value_ep_bp", "quality_roe"],
                        "generation_method": "seed_factor_blend",
                        "alpha_target": "explainable value-quality alpha",
                        "economic_mechanism": "valuation and asset profitability jointly screen for cheap profitable firms",
                        "field_sources": {"eps": "fundamentals", "close": "prices", "net_income": "fundamentals", "total_assets": "fundamentals"},
                        "a_share_mapping": "price uses same-day market data; fundamentals are PIT merged by ann_date",
                        "direction": "higher is better",
                        "scope": "single-stock cross-section",
                        "backtestable_status": "currently_backtestable",
                        "status_reason": "all fields exist in the PIT panel",
                        "risk_exposures": ["industry", "size", "value trap"],
                        "validation_notes": "ICIR alone is descriptive; check t-stat, novelty and walk-forward stability",
                    },
                },
            ],
            ensure_ascii=False,
        )

    def _api_response(self, prompt: str, system: str | None, base_url: str | None, api_key: str | None) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model=self.cfg.llm_model,
            messages=messages,
            max_tokens=self.cfg.llm_max_tokens,
            temperature=self.cfg.llm_temperature,
        )
        return response.choices[0].message.content or ""
