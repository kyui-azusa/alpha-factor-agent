from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import pandas as pd

from src.agents.json_utils import factor_from_json, parse_llm_json
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.llm.prompts import FEEDBACK_PROMPT


class FeedbackBoundaryError(ValueError):
    """Raised when sealed evidence is used as a generation input."""


class FeedbackSource(str, Enum):
    PRE_GENERATION = "pre_generation"
    VALIDATION = "validation"
    DEV_BACKTEST = "dev_backtest"
    OOS_BACKTEST = "oos_backtest"


GENERATION_FEEDBACK_SOURCES = {
    FeedbackSource.PRE_GENERATION,
    FeedbackSource.VALIDATION,
    FeedbackSource.DEV_BACKTEST,
}

GENERATION_FEEDBACK_KEYS = {
    FeedbackSource.PRE_GENERATION: {
        "factor_name",
        "field_catalog",
        "field_sources",
        "economic_mechanism",
        "complexity_diagnostic",
        "generation_constraints",
    },
    FeedbackSource.VALIDATION: {
        "factor_name",
        "formula_status",
        "pit_status",
        "unknown_fields",
        "duplicate_status",
        "computability_status",
        "validation_notes",
    },
    FeedbackSource.DEV_BACKTEST: {
        "factor_name",
        "data_mode",
        "turnover_diagnostic",
        "cost_diagnostic",
        "sample_diagnostic",
        "declared_risk_exposures",
        "validation_notes",
    },
}


def _missing(value: Any) -> bool:
    return value is None or bool(pd.isna(value))


@dataclass(frozen=True)
class FeedbackRecord:
    source: FeedbackSource
    factor_name: str
    payload: dict[str, Any]
    next_generation_allowed: bool
    disposition: str

    def __post_init__(self) -> None:
        expected = self.source in GENERATION_FEEDBACK_SOURCES
        if self.next_generation_allowed != expected:
            raise FeedbackBoundaryError(
                f"feedback source {self.source.value} requires next_generation_allowed={str(expected).lower()}"
            )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        return data


def _turnover_diagnostic(value: Any) -> str:
    if _missing(value):
        return "not_available"
    value = float(value)
    if value >= 1.5:
        return "high_turnover_review_rebalance_frequency"
    if value >= 0.8:
        return "medium_turnover_review_cost_sensitivity"
    return "low_turnover"


def _cost_diagnostic(summary: dict[str, Any]) -> str:
    gross = summary.get("long_short_mean")
    net = summary.get("net_long_short_mean")
    if _missing(gross) or _missing(net):
        return "not_available"
    gross = float(gross)
    net = float(net)
    if abs(gross) <= 1e-12:
        return "not_available_zero_gross_signal"
    drag_ratio = abs(gross - net) / abs(gross)
    if net * gross <= 0 or drag_ratio >= 0.5:
        return "high_cost_decay_review_turnover_and_capacity"
    if drag_ratio >= 0.2:
        return "medium_cost_decay_review_execution_assumptions"
    return "low_cost_decay"


def development_feedback(expr: FactorExpr, backtest_result: dict[str, Any]) -> FeedbackRecord:
    """Build an allowlisted, non-OOS diagnostic record for candidate refinement."""
    train = backtest_result.get("train_summary") or {}
    metadata = expr.metadata if isinstance(expr.metadata, dict) else {}
    observations = train.get("observations")
    if _missing(observations):
        sample_diagnostic = "not_available"
    elif int(observations) <= 0:
        sample_diagnostic = "empty_development_sample"
    else:
        sample_diagnostic = "development_sample_available"
    payload = {
        "factor_name": expr.name,
        "data_mode": (backtest_result.get("data") or {}).get("data_mode", "unknown"),
        "turnover_diagnostic": _turnover_diagnostic(train.get("turnover_mean")),
        "cost_diagnostic": _cost_diagnostic(train),
        "sample_diagnostic": sample_diagnostic,
        "declared_risk_exposures": metadata.get("risk_exposures", []),
        "validation_notes": metadata.get("validation_notes", []),
    }
    return FeedbackRecord(
        source=FeedbackSource.DEV_BACKTEST,
        factor_name=expr.name,
        payload=payload,
        next_generation_allowed=True,
        disposition="bounded_diagnostic_input",
    )


def sealed_oos_evidence(expr: FactorExpr, backtest_result: dict[str, Any]) -> FeedbackRecord:
    """Record OOS results as terminal evidence that can never enter generation."""
    summary = dict(backtest_result.get("summary") or {})
    ic_mean = summary.get("ic_mean")
    net_long_short_mean = summary.get("net_long_short_mean")
    observations = summary.get("observations")
    failure_reasons: list[str] = []
    if _missing(observations) or int(observations) <= 0:
        failure_reasons.append("empty_or_missing_oos_sample")
    if _missing(ic_mean):
        failure_reasons.append("oos_ic_not_available")
    elif float(ic_mean) <= 0:
        failure_reasons.append("non_positive_oos_ic")
    if _missing(net_long_short_mean):
        failure_reasons.append("oos_net_long_short_not_available")
    elif float(net_long_short_mean) <= 0:
        failure_reasons.append("non_positive_oos_net_long_short")

    walk_forward = backtest_result.get("walk_forward", {})
    robustness = backtest_result.get("robustness", {})
    risk_warnings: list[str] = []
    walk_forward_status = walk_forward.get("status") if isinstance(walk_forward, dict) else None
    if walk_forward_status not in (None, "consistent_positive_ic"):
        risk_warnings.append(f"walk_forward:{walk_forward_status}")
    if isinstance(robustness, dict):
        for key in ("overfit_risk", "cost_sensitivity", "similarity_risk"):
            if robustness.get(key) in {"medium", "high"}:
                risk_warnings.append(f"{key}:{robustness[key]}")

    if failure_reasons:
        unavailable_only = all("not_available" in reason or "missing" in reason for reason in failure_reasons)
        status = "oos_inconclusive" if unavailable_only else "oos_failed"
    else:
        status = "oos_evidence_recorded"
    payload = {
        "factor_name": expr.name,
        "status": status,
        "failure_reasons": failure_reasons,
        "risk_warnings": risk_warnings,
        "summary": summary,
        "walk_forward": walk_forward,
        "tradability": backtest_result.get("tradability", {}),
        "robustness": robustness,
        "backtest_results_touched": True,
        "oos_values_exposed_to_generation": False,
        "clean_oos_test": True,
        "allowed_next_action": "record_evidence_only",
    }
    return FeedbackRecord(
        source=FeedbackSource.OOS_BACKTEST,
        factor_name=expr.name,
        payload=payload,
        next_generation_allowed=False,
        disposition="terminal_evidence",
    )


def feedback_summary(record: FeedbackRecord) -> dict[str, Any]:
    """Return an allowlisted feedback payload or fail closed for sealed OOS evidence."""
    if not isinstance(record, FeedbackRecord):
        raise TypeError("feedback must be an explicit FeedbackRecord with source provenance")
    if record.source not in GENERATION_FEEDBACK_SOURCES or not record.next_generation_allowed:
        raise FeedbackBoundaryError(f"{record.source.value} feedback is sealed and cannot enter generation")
    allowed_keys = GENERATION_FEEDBACK_KEYS[record.source]
    unexpected = set(record.payload) - allowed_keys
    if unexpected:
        raise FeedbackBoundaryError(
            f"{record.source.value} feedback contains non-allowlisted keys: {sorted(unexpected)}"
        )
    return {
        "source": record.source.value,
        "factor_name": record.factor_name,
        "diagnostics": dict(record.payload),
        "feedback_data_boundary": "non_oos_allowlisted_diagnostics_only",
        "oos_values_exposed": False,
    }


def refine(expr: FactorExpr, feedback: FeedbackRecord, client: LLMClient | None = None) -> FactorExpr | None:
    client = client or LLMClient()
    summary = feedback_summary(feedback)
    raw = client.generate(
        FEEDBACK_PROMPT.format(
            factor=json.dumps(expr.to_dict(), ensure_ascii=False, sort_keys=True),
            summary=json.dumps(summary, ensure_ascii=False, sort_keys=True),
        )
    )
    if raw.strip().lower() == "null":
        return None
    item = parse_llm_json(raw)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError("LLM feedback must return a factor JSON object or null")
    refined = factor_from_json(item)
    refined.metadata["feedback_lineage"] = {
        "parent_factor": expr.name,
        "source": feedback.source.value,
        "backtest_results_touched": True,
        "oos_values_exposed": False,
        "clean_oos_test": True,
    }
    return refined
