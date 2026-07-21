from __future__ import annotations

import json
from pathlib import Path

from src.agents.generate import propose_factors
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


def _save_factor(expr: FactorExpr, result: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"expr": expr.to_dict(), "summary": result["summary"]}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_loop(rounds: int = 1, per_round: int = 2, cfg: Config = CONFIG, client: LLMClient | None = None) -> list[dict]:
    client = client or LLMClient(cfg)
    panel = build_panel(cfg, save=True)
    fwd_ret = get_forward_returns(load_prices(cfg), periods=(1, 5, 20))
    field_dict = _field_dict(panel)
    accepted: list[FactorExpr] = list(BASELINE_FACTORS)
    results: list[dict] = []

    for round_id in range(1, rounds + 1):
        candidates = propose_factors([factor.to_dict() for factor in accepted], field_dict, n=per_round, client=client)
        for expr in candidates:
            ok, reason = validate(expr, field_dict, panel=panel, existing_factors=accepted, client=client)
            if not ok:
                continue
            result = backtest(expr, panel, fwd_ret, cfg=cfg)
            to_report(result, cfg.report_dir / expr.name)
            _save_factor(expr, result, cfg.factor_dir / f"{expr.name}.json")
            accepted.append(expr)
            results.append({"round": round_id, "expr": expr.to_dict(), "summary": result["summary"], "validation": reason})
    return results


if __name__ == "__main__":
    output = run_loop(rounds=1, per_round=2)
    print(json.dumps(output, ensure_ascii=False, indent=2))
