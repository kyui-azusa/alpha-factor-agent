from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.audit import candidate_funnel_summary
from src.agents.feedback import development_feedback, refine, sealed_oos_evidence
from src.agents.generate import propose_factors
from src.agents.knowledge import generation_context
from src.agents.novelty import batch_novelty_review, promotion_decision
from src.agents.validate import validate
from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import CONFIG, Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.utils.data_loader import build_panel, get_forward_returns, load_prices

if TYPE_CHECKING:
    from src.research.preflight import ExecutionPermit


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


def _stamp_execution_lineage(expr: FactorExpr, permit: ExecutionPermit) -> None:
    expr.metadata["research_execution"] = permit.to_dict()


def _contract_scope_reason(expr: FactorExpr, permit: ExecutionPermit) -> str | None:
    from src.factors.engine import expression_names

    used_fields = expression_names(expr.expression) | set(expr.fields_used)
    outside_fields = sorted(used_fields - set(permit.allowed_fields))
    if outside_fields:
        return f"candidate uses fields outside the confirmed research contract: {outside_fields}"

    operator_names = {
        ast.Add: "add",
        ast.Sub: "sub",
        ast.Mult: "mul",
        ast.Div: "div",
        ast.Pow: "pow",
        ast.Mod: "mod",
    }
    tree = ast.parse(expr.expression, mode="eval")
    used_operators = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    used_operators.update(
        operator_names[type(node.op)]
        for node in ast.walk(tree)
        if isinstance(node, ast.BinOp) and type(node.op) in operator_names
    )
    outside_operators = sorted(used_operators - set(permit.allowed_operators))
    if outside_operators:
        return f"candidate uses operators outside the confirmed research contract: {outside_operators}"
    return None


def _save_oos_evidence(evidence: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_loop(
    rounds: int = 1,
    per_round: int = 2,
    cfg: Config = CONFIG,
    client: LLMClient | None = None,
    refine_rounds: int = 1,
    execution_permit: ExecutionPermit | None = None,
) -> list[dict]:
    from src.research.preflight import validate_execution_permit

    execution_permit = validate_execution_permit(execution_permit)
    if rounds > execution_permit.rounds or rounds * per_round > execution_permit.candidate_count:
        raise PermissionError("agent generation exceeds the rounds or candidate count confirmed by the contract")
    client = client or LLMClient(cfg)
    panel = build_panel(cfg, save=True)
    fwd_ret = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))
    field_dict = _field_dict(panel)
    gen_context = generation_context(panel)
    accepted: list[FactorExpr] = list(BASELINE_FACTORS)
    accepted_results: list[dict] = []
    results: list[dict] = []
    candidate_audit: list[dict] = []

    for round_id in range(1, rounds + 1):
        candidates = propose_factors([factor.to_dict() for factor in accepted], gen_context, n=per_round, client=client)
        candidates, batch_decisions = batch_novelty_review(candidates, accepted, panel)
        rejected_names = {item["candidate"] for item in batch_decisions if item["decision"] == "reject"}
        for decision in batch_decisions:
            if decision["candidate"] in rejected_names:
                audit_row = {
                    "generated": True,
                    "validated": False,
                    "backtested": False,
                    "promoted": False,
                    "rejected": True,
                    "reason_code": "batch_novelty_rejected",
                }
                candidate_audit.append(audit_row)
                results.append({"round": round_id, "attempt": 0, "batch_novelty_rejected": decision, "candidate_audit": audit_row})
        for expr in candidates:
            current = expr
            parent: str | None = None
            for attempt in range(refine_rounds + 1):
                _stamp_execution_lineage(current, execution_permit)
                try:
                    scope_reason = _contract_scope_reason(current, execution_permit)
                except (SyntaxError, ValueError) as exc:
                    scope_reason = f"candidate contract-scope validation failed: {exc}"
                if scope_reason:
                    audit_row = {
                        "generated": True,
                        "validated": False,
                        "backtested": False,
                        "promoted": False,
                        "rejected": True,
                        "reason_code": "contract_scope_rejected",
                    }
                    candidate_audit.append(audit_row)
                    results.append(
                        {
                            "round": round_id,
                            "attempt": attempt,
                            "expr": current.to_dict(),
                            "parent": parent,
                            "rejected": scope_reason,
                            "candidate_audit": audit_row,
                        }
                    )
                    break
                ok, reason = validate(current, field_dict, panel=panel, existing_factors=accepted, client=client)
                if not ok:
                    audit_row = {
                        "generated": True,
                        "validated": False,
                        "backtested": False,
                        "promoted": False,
                        "rejected": True,
                        "reason_code": reason.split(":", 1)[0].replace(" ", "_").lower(),
                    }
                    candidate_audit.append(audit_row)
                    results.append(
                        {
                            "round": round_id,
                            "attempt": attempt,
                            "expr": current.to_dict(),
                            "parent": parent,
                            "rejected": reason,
                            "candidate_audit": audit_row,
                        }
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
                promotion = promotion_decision(
                    result,
                    current.metadata.get("validation", {}).get("batch_novelty", {}),
                    accepted_results,
                )
                if promotion["action"] != "promote":
                    audit_row = {
                        "generated": True,
                        "validated": True,
                        "backtested": True,
                        "promoted": False,
                        "rejected": True,
                        "reason_code": ",".join(promotion["reasons"]),
                    }
                    candidate_audit.append(audit_row)
                    results.append(
                        {
                            "round": round_id,
                            "attempt": attempt,
                            "expr": current.to_dict(),
                            "parent": parent,
                            "rejected": "; ".join(promotion["reasons"]),
                            "promotion": promotion,
                            "candidate_audit": audit_row,
                        }
                    )
                    break
                current.metadata.setdefault("validation", {})["promotion"] = promotion
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
                accepted_results.append(result)
                audit_row = {
                    "generated": True,
                    "validated": True,
                    "backtested": True,
                    "promoted": True,
                    "rejected": False,
                    "reason_code": "promoted",
                }
                candidate_audit.append(audit_row)
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
                        "candidate_audit": audit_row,
                    }
                )
                if attempt >= refine_rounds:
                    break
                refined = refine(current, dev_feedback, client=client)
                if refined is None:
                    break
                parent = current.name
                current = refined
    funnel = candidate_funnel_summary(candidate_audit).to_dict()
    for item in results:
        item["candidate_funnel"] = funnel
    return results


if __name__ == "__main__":
    raise SystemExit("Agent generation requires a confirmed request and passing preflight; use the research service.")
