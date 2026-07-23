from __future__ import annotations

import json
from pathlib import Path

from src.agents.feedback import development_feedback, refine, sealed_oos_evidence
from src.agents.generate import propose_factors
from src.agents.knowledge import generation_context
from src.agents.validate import validate
from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import CONFIG, Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.utils.data_loader import build_panel, get_forward_returns, load_prices


def _field_dict(panel) -> dict[str, str]:
    return {column: str(dtype) for column, dtype in panel.dtypes.items()}


def _save_factor(
    expr: FactorExpr,
    result: dict,
    path: Path,
    parent: str | None = None,
    feedback_audit: dict | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "expr": expr.to_dict(),
        "parent": parent,
        "train_summary": result["train_summary"],
        "summary": result["summary"],
        "feedback_audit": feedback_audit or {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_oos_evidence(evidence: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_loop(
    rounds: int = 1,
    per_round: int = 2,
    cfg: Config = CONFIG,
    client: LLMClient | None = None,
    refine_rounds: int = 1,
) -> list[dict]:
    client = client or LLMClient(cfg)
    panel = build_panel(cfg, save=True)
    fwd_ret = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))
    field_dict = _field_dict(panel)
    gen_context = generation_context(panel)
    accepted: list[FactorExpr] = list(BASELINE_FACTORS)
    results: list[dict] = []

    for round_id in range(1, rounds + 1):
        candidates = propose_factors([factor.to_dict() for factor in accepted], gen_context, n=per_round, client=client)
        for expr in candidates:
            current = expr
            parent: str | None = None
            for attempt in range(refine_rounds + 1):
                ok, reason = validate(current, field_dict, panel=panel, existing_factors=accepted, client=client)
                if not ok:
                    results.append(
                        {"round": round_id, "attempt": attempt, "expr": current.to_dict(), "parent": parent, "rejected": reason}
                    )
                    break
                result = backtest(current, panel, fwd_ret, cfg=cfg)
                dev_feedback = development_feedback(current, result)
                oos_evidence = sealed_oos_evidence(current, result)
                feedback_audit = {
                    "backtest_results_touched": True,
                    "generation_feedback_source": dev_feedback.source.value,
                    "oos_evidence_source": oos_evidence.source.value,
                    "oos_values_exposed_to_generation": False,
                    "clean_oos_test": True,
                    "next_generation_allowed_from_oos": False,
                }
                result["development_feedback"] = dev_feedback.to_dict()
                result["oos_evidence"] = oos_evidence.to_dict()
                result["feedback_audit"] = feedback_audit
                to_report(result, cfg.report_dir / current.name)
                _save_factor(
                    current,
                    result,
                    cfg.factor_dir / f"{current.name}.json",
                    parent=parent,
                    feedback_audit=feedback_audit,
                )
                _save_oos_evidence(
                    oos_evidence.to_dict(),
                    cfg.results_dir / "feedback" / "oos" / f"{current.name}.json",
                )
                accepted.append(current)
                results.append(
                    {
                        "round": round_id,
                        "attempt": attempt,
                        "expr": current.to_dict(),
                        "parent": parent,
                        "train_summary": result["train_summary"],
                        "summary": result["summary"],
                        "validation": reason,
                        "development_feedback": result["development_feedback"],
                        "oos_evidence": result["oos_evidence"],
                        "feedback_audit": feedback_audit,
                    }
                )
                if attempt >= refine_rounds:
                    break
                refined = refine(current, dev_feedback, client=client)
                if refined is None:
                    break
                parent = current.name
                current = refined
    return results


if __name__ == "__main__":
    output = run_loop(rounds=1, per_round=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
