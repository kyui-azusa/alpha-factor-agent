from __future__ import annotations

from dataclasses import dataclass
from typing import Any


CONTRACT_VERSION = "experiment-evidence-v1"

EVIDENCE_REQUIREMENTS: dict[str, dict[str, str]] = {
    "human_labels": {
        "label": "人工标签",
        "reason": "需要 2-3 人独立标注或仲裁后的 ground truth，不能用模型自判替代。",
    },
    "real_llm_calls": {
        "label": "真实 LLM 调用",
        "reason": "需要冻结模型、prompt、temperature 后的真实调用记录，mock 后端只能证明流程可运行。",
    },
    "factor_catalog_100": {
        "label": "100 因子目录",
        "reason": "需要固定的 100 个候选/已知因子目录作为抽样、覆盖度或搜索效率比较的输入。",
    },
    "real_jydb_data": {
        "label": "真实 JYDB 数据",
        "reason": "需要聚源真实 raw 表与 PIT 面板；合成数据只能证明工程链路，不支持实证结论。",
    },
}


@dataclass(frozen=True)
class ExperimentSpec:
    issue_number: int
    title: str
    required_evidence: tuple[str, ...]
    conclusion_metric: str


EXPERIMENT_SPECS: dict[int, ExperimentSpec] = {
    71: ExperimentSpec(
        issue_number=71,
        title="LLM 语义查重的假阳性与假阴性率量化实验",
        required_evidence=("human_labels", "real_llm_calls", "factor_catalog_100"),
        conclusion_metric="false_positive_rate / false_negative_rate / F1 / McNemar p-value",
    ),
    73: ExperimentSpec(
        issue_number=73,
        title="LLM 假设空间探索效率 vs 遗传规划 / 随机搜索",
        required_evidence=("real_llm_calls", "factor_catalog_100", "real_jydb_data"),
        conclusion_metric="valid_factor_count / top5_oos_rank_ic / effect_size",
    ),
    74: ExperimentSpec(
        issue_number=74,
        title="受限表达式引擎白名单覆盖度评估",
        required_evidence=("factor_catalog_100",),
        conclusion_metric="whitelist_coverage_rate / missing_operator_top_n",
    ),
    75: ExperimentSpec(
        issue_number=75,
        title="PIT 对齐 vs 朴素对齐的 Rank IC 膨胀量化",
        required_evidence=("real_jydb_data",),
        conclusion_metric="delta_ic_distribution / max_delta_ic / Wilcoxon p-value",
    ),
    77: ExperimentSpec(
        issue_number=77,
        title="FeedbackAgent 闭环有效性验证对照实验",
        required_evidence=("real_llm_calls", "real_jydb_data"),
        conclusion_metric="closed_loop_top1_oos_ic_delta / positive_round_count / Wilcoxon p-value",
    ),
}


def _requirement_payload(key: str) -> dict[str, str]:
    if key not in EVIDENCE_REQUIREMENTS:
        raise KeyError(f"unknown evidence requirement: {key}")
    item = EVIDENCE_REQUIREMENTS[key]
    return {"key": key, "label": item["label"], "reason": item["reason"]}


def build_evidence_contract(
    issue_number: int,
    *,
    code_ready: bool = True,
    input_ready: bool = True,
    available_evidence: set[str] | list[str] | tuple[str, ...] | None = None,
    research_conclusion: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the shared evidence contract for experiment issues.

    Top-level ``status=ready`` means only that experiment code and declared
    inputs are in place. Research support is tracked separately under
    ``evidence.status`` and ``research_conclusion``.
    """

    spec = EXPERIMENT_SPECS[issue_number]
    available = set(available_evidence or ())
    unknown = available - set(EVIDENCE_REQUIREMENTS)
    if unknown:
        raise ValueError(f"unknown evidence keys: {sorted(unknown)}")

    missing = [key for key in spec.required_evidence if key not in available]
    readiness_status = "ready" if code_ready and input_ready else "not_ready"
    evidence_status = "ready" if not missing else "insufficient_evidence"
    conclusion = research_conclusion or {
        "status": "not_computed",
        "metric": spec.conclusion_metric,
        "value": None,
    }

    return {
        "contract_version": CONTRACT_VERSION,
        "issue_number": spec.issue_number,
        "title": spec.title,
        "status": readiness_status,
        "status_meaning": "ready only means experiment code and declared inputs are complete; it is not a research conclusion",
        "code_ready": bool(code_ready),
        "input_ready": bool(input_ready),
        "required_evidence": [_requirement_payload(key) for key in spec.required_evidence],
        "evidence": {
            "status": evidence_status,
            "missing": [_requirement_payload(key) for key in missing],
            "available": [_requirement_payload(key) for key in spec.required_evidence if key in available],
        },
        "research_conclusion": conclusion,
    }
