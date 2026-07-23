from __future__ import annotations

from src.agents.json_utils import factor_from_json, parse_llm_json
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.llm.prompts import FEEDBACK_PROMPT


TRAIN_FEEDBACK_KEYS = {
    "name",
    "segment",
    "start_date",
    "end_date",
    "train_end",
    "ic_mean",
    "ic_ir",
    "ic_count",
    "ic_std",
    "ic_stderr",
    "ic_t_stat",
    "ic_pvalue_normal_approx",
    "ic_inference_note",
    "long_short_mean",
    "turnover_mean",
    "net_long_short_mean",
    "observations",
    "cost_bps",
}


def feedback_summary(backtest_result: dict) -> dict:
    """Return the train-only summary that may be shown to the LLM feedback step."""
    if "train_summary" in backtest_result:
        source = backtest_result.get("train_summary") or {}
    elif isinstance(backtest_result.get("summary"), dict):
        source = backtest_result.get("summary") or {}
    else:
        source = backtest_result
    summary = {key: source[key] for key in TRAIN_FEEDBACK_KEYS if key in source}
    summary["feedback_data_boundary"] = "train_segment_only_no_oos_metrics"
    return summary


def refine(expr: FactorExpr, backtest_result: dict, client: LLMClient | None = None) -> FactorExpr | None:
    client = client or LLMClient()
    raw = client.generate(FEEDBACK_PROMPT.format(factor=expr.to_dict(), summary=feedback_summary(backtest_result)))
    if raw.strip().lower() == "null":
        return None
    item = parse_llm_json(raw)
    if item is None:
        return None
    if not isinstance(item, dict):
        raise ValueError("LLM feedback must return a factor JSON object or null")
    return factor_from_json(item)
