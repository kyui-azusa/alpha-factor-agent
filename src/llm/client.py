from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import UTC, datetime
from typing import Any

from src.config import CONFIG, Config


class LLMClient:
    def __init__(self, cfg: Config = CONFIG, backend: str | None = None):
        self.cfg = cfg
        self.backend = backend or cfg.llm_backend
        self.cache_dir = cfg.cache_dir / "llm"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.last_generation_record: dict[str, Any] | None = None

    def generate(self, prompt: str, system: str | None = None) -> str:
        key = self._cache_key(prompt, system)
        path = self.cache_dir / f"{key}.txt"
        record_path = self.cache_dir / f"{key}.json"
        if path.exists():
            response = path.read_text(encoding="utf-8")
            record = self._load_or_create_record(record_path, key, prompt, system, response)
            record["cache_hit"] = True
            self._atomic_write(record_path, json.dumps(record, ensure_ascii=False, indent=2))
            self.last_generation_record = dict(record)
            return response
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
        record = self._generation_record(key, prompt, system, response, cache_hit=False)
        self._atomic_write(path, response)
        self._atomic_write(record_path, json.dumps(record, ensure_ascii=False, indent=2))
        self.last_generation_record = dict(record)
        return response

    def generation_record(self) -> dict[str, Any] | None:
        return dict(self.last_generation_record) if self.last_generation_record is not None else None

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

    def _generation_record(
        self,
        key: str,
        prompt: str,
        system: str | None,
        response: str,
        *,
        cache_hit: bool,
        created_at_utc: str | None = None,
    ) -> dict[str, Any]:
        prompt_payload = json.dumps({"system": system, "prompt": prompt}, sort_keys=True, ensure_ascii=False)
        return {
            "schema_version": "1.0",
            "generation_record_id": f"gen_{key[:24]}",
            "cache_key": key,
            "prompt_hash": hashlib.sha256(prompt_payload.encode("utf-8")).hexdigest(),
            "output_hash": hashlib.sha256(response.encode("utf-8")).hexdigest(),
            "backend": self.backend,
            "model": self.cfg.llm_model,
            "max_tokens": self.cfg.llm_max_tokens,
            "temperature": self.cfg.llm_temperature,
            "created_at_utc": created_at_utc or datetime.now(UTC).isoformat(),
            "cache_hit": cache_hit,
        }

    def _load_or_create_record(
        self, record_path: Path, key: str, prompt: str, system: str | None, response: str
    ) -> dict[str, Any]:
        if record_path.exists():
            record = json.loads(record_path.read_text(encoding="utf-8"))
            expected_hash = hashlib.sha256(response.encode("utf-8")).hexdigest()
            if record.get("cache_key") != key or record.get("output_hash") != expected_hash:
                raise ValueError(f"LLM cache integrity check failed for {key}")
            return record
        created_at = datetime.fromtimestamp(record_path.with_suffix(".txt").stat().st_mtime, UTC).isoformat()
        return self._generation_record(key, prompt, system, response, cache_hit=True, created_at_utc=created_at)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
                temporary_path = handle.name
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _mock_response(self, prompt: str) -> str:
        if "duplicate" in prompt.lower():
            return '{"duplicate": false, "reason": "mock semantic validator does not see duplication"}'
        if "return null" in prompt.lower():
            return "null"
        return json.dumps(
            [
                {
                    "name": "llm_mock_cashflow_improvement",
                    "expression": "rank(delta(safe_div(operating_cash_flow, total_assets), 1))",
                    "economic_rationale": "经营现金流资产收益率改善可能比静态盈利水平更早反映盈利质量变化。",
                    "fields_used": ["operating_cash_flow", "total_assets"],
                    "metadata": {
                        "category": "quality",
                        "seed_factors": ["operating_cash_flow_yield", "quality_roe"],
                        "generation_method": "seed_factor_blend",
                        "alpha_target": "cash-flow quality improvement",
                        "economic_mechanism": "improvement in cash return on assets may reveal quality changes beyond static levels",
                        "field_sources": {"operating_cash_flow": "fundamentals", "total_assets": "fundamentals"},
                        "a_share_mapping": "PIT-merged disclosed fundamentals; no future returns used",
                        "direction": "higher is better",
                        "scope": "single-stock cross-section",
                        "backtestable_status": "currently_backtestable",
                        "status_reason": "all fields exist in the PIT panel",
                        "knowledge_citations": ["juyuan-core-market-data"],
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
                        "knowledge_citations": ["juyuan-core-market-data"],
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
