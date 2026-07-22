from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.agents.generate import propose_factors
from src.agents.novelty import NoveltyPolicy, batch_novelty_review
from src.agents.validate import deterministic_fingerprint, validate
from src.factors.engine import FactorExpr


@dataclass(frozen=True)
class TemperatureSweepConfig:
    temperatures: tuple[float, ...] = (0.0, 0.2, 0.5, 0.8, 1.0)
    repeats: int = 3
    candidates_per_repeat: int = 5


def _pareto_frontier(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        row["pareto_optimal"] = not any(
            other is not row
            and other["validity_rate"] >= row["validity_rate"]
            and other["novelty_rate"] >= row["novelty_rate"]
            and (
                other["validity_rate"] > row["validity_rate"]
                or other["novelty_rate"] > row["novelty_rate"]
            )
            for other in rows
        )


def sweep_temperatures(
    *,
    existing_factors: list[FactorExpr],
    generation_context: dict[str, Any],
    field_dict: dict[str, str] | set[str] | list[str],
    panel: pd.DataFrame,
    client_factory: Callable[[float, int], Any],
    config: TemperatureSweepConfig = TemperatureSweepConfig(),
    novelty_policy: NoveltyPolicy = NoveltyPolicy(),
) -> dict[str, Any]:
    if config.repeats <= 0 or config.candidates_per_repeat <= 0:
        raise ValueError("temperature sweep repeats and candidates_per_repeat must be positive")
    rows: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for temperature in config.temperatures:
        proposed = 0
        parse_failures = 0
        valid_candidates: list[FactorExpr] = []
        invalid_reasons: list[str] = []
        for repeat in range(config.repeats):
            client = client_factory(float(temperature), repeat)
            context = {
                **generation_context,
                "temperature_experiment": {
                    "temperature": float(temperature),
                    "repeat": repeat,
                    "purpose": "controlled novelty-validity sweep; not backtest evidence",
                },
            }
            try:
                candidates = propose_factors(
                    [factor.to_dict() for factor in existing_factors],
                    context,
                    n=config.candidates_per_repeat,
                    client=client,
                )
            except ValueError as exc:
                parse_failures += config.candidates_per_repeat
                invalid_reasons.append(str(exc))
                continue
            proposed += len(candidates)
            parse_failures += max(config.candidates_per_repeat - len(candidates), 0)
            for candidate in candidates:
                ok, reason = validate(candidate, field_dict, panel=panel, existing_factors=None)
                if ok:
                    valid_candidates.append(candidate)
                else:
                    invalid_reasons.append(reason)

        reviewed, novelty_decisions = batch_novelty_review(
            valid_candidates,
            existing_factors,
            panel,
            policy=novelty_policy,
        )
        strict_novel = [item for item in novelty_decisions if item["decision"] == "pass"]
        fingerprints = {deterministic_fingerprint(candidate) for candidate in valid_candidates}
        denominator = proposed + parse_failures
        validity_rate = len(valid_candidates) / denominator if denominator else 0.0
        novelty_rate = len(strict_novel) / len(valid_candidates) if valid_candidates else 0.0
        unique_rate = len(fingerprints) / len(valid_candidates) if valid_candidates else 0.0
        row = {
            "temperature": float(temperature),
            "requested_count": config.repeats * config.candidates_per_repeat,
            "proposed_count": proposed,
            "parse_failure_count": parse_failures,
            "rule_valid_count": len(valid_candidates),
            "novel_pass_count": len(strict_novel),
            "accepted_after_novelty_count": len(reviewed),
            "unique_expression_count": len(fingerprints),
            "validity_rate": validity_rate,
            "novelty_rate": novelty_rate,
            "unique_expression_rate": unique_rate,
        }
        rows.append(row)
        details.append(
            {
                "temperature": float(temperature),
                "invalid_reasons": invalid_reasons,
                "novelty_decisions": novelty_decisions,
            }
        )
    _pareto_frontier(rows)
    return {
        "config": asdict(config),
        "metric_definitions": {
            "validity_rate": "rule-valid executable candidates / requested candidates",
            "novelty_rate": "strict novelty passes / rule-valid candidates; warnings do not count as novel",
            "unique_expression_rate": "unique deterministic expression fingerprints / rule-valid candidates",
            "pareto_optimal": "not dominated on both validity_rate and novelty_rate",
        },
        "rows": rows,
        "details": details,
    }


def write_temperature_report(report: dict[str, Any], output_dir: str | Path) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "temperature_sweep.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    pd.DataFrame(report["rows"]).to_csv(path / "temperature_sweep.csv", index=False)
    return path
