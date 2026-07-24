from __future__ import annotations

import json
from pathlib import Path

from src.audit import candidate_funnel_summary
from src.agents.feedback import refine
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


def _save_factor(expr: FactorExpr, result: dict, path: Path, parent: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "expr": expr.to_dict(),
        "parent": parent,
        "train_summary": result["train_summary"],
        "summary": result["summary"],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
    candidate_audit: list[dict] = []

    for round_id in range(1, rounds + 1):
        candidates = propose_factors([factor.to_dict() for factor in accepted], gen_context, n=per_round, client=client)
        for expr in candidates:
            current = expr
            parent: str | None = None
            for attempt in range(refine_rounds + 1):
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
                to_report(result, cfg.report_dir / current.name)
                _save_factor(current, result, cfg.factor_dir / f"{current.name}.json", parent=parent)
                accepted.append(current)
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
                        "candidate_audit": audit_row,
                    }
                )
                if attempt >= refine_rounds:
                    break
                # 信息单向阀:只把训练段结果交给 LLM,样本外结果全程封存
                refined = refine(current, {"summary": result["train_summary"]}, client=client)
                if refined is None:
                    break
                parent = current.name
                current = refined
    funnel = candidate_funnel_summary(candidate_audit).to_dict()
    for item in results:
        item["candidate_funnel"] = funnel
    return results


if __name__ == "__main__":
    output = run_loop(rounds=1, per_round=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
