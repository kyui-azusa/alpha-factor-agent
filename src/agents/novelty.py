from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.agents.validate import deterministic_fingerprint
from src.factors.engine import FactorExpr, evaluate


@dataclass(frozen=True)
class NoveltyPolicy:
    signal_warn: float = 0.60
    signal_reject: float = 0.85
    behavior_warn: float = 0.70
    behavior_reject: float = 0.90
    rolling_window_days: int = 63
    min_observations: int = 20


def _correlation(left: pd.Series, right: pd.Series, min_observations: int) -> tuple[float, int]:
    aligned = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if len(aligned) < min_observations or aligned["left"].nunique() < 2 or aligned["right"].nunique() < 2:
        return float("nan"), int(len(aligned))
    return float(aligned["left"].corr(aligned["right"])), int(len(aligned))


def _cross_section_ranks(values: pd.Series) -> pd.Series:
    if isinstance(values.index, pd.MultiIndex) and "date" in values.index.names:
        return values.groupby(level="date").rank(pct=True)
    return values.rank(pct=True)


def rolling_signal_similarity(
    candidate: pd.Series,
    reference: pd.Series,
    *,
    window_days: int = 63,
    min_observations: int = 20,
) -> dict[str, Any]:
    left = _cross_section_ranks(candidate).rename("candidate")
    right = _cross_section_ranks(reference).rename("reference")
    aligned = pd.concat([left, right], axis=1).dropna()
    if aligned.empty:
        return {"windows": [], "max_abs_corr": float("nan"), "latest_abs_corr": float("nan")}
    if isinstance(aligned.index, pd.MultiIndex) and "date" in aligned.index.names:
        dates = pd.Index(aligned.index.get_level_values("date").unique()).sort_values()
    else:
        dates = pd.Index(aligned.index).sort_values()
    windows: list[dict[str, Any]] = []
    for start in range(0, len(dates), window_days):
        selected = dates[start : start + window_days]
        if isinstance(aligned.index, pd.MultiIndex):
            chunk = aligned.loc[aligned.index.get_level_values("date").isin(selected)]
        else:
            chunk = aligned.loc[aligned.index.isin(selected)]
        corr, count = _correlation(chunk["candidate"], chunk["reference"], min_observations)
        if not pd.isna(corr):
            windows.append(
                {
                    "start_date": str(pd.Timestamp(selected[0]).date()),
                    "end_date": str(pd.Timestamp(selected[-1]).date()),
                    "abs_corr": abs(corr),
                    "observations": count,
                }
            )
    values = [row["abs_corr"] for row in windows]
    return {
        "windows": windows,
        "max_abs_corr": max(values) if values else float("nan"),
        "latest_abs_corr": values[-1] if values else float("nan"),
    }


def pairwise_signal_review(
    candidate: FactorExpr,
    reference: FactorExpr,
    panel: pd.DataFrame,
    policy: NoveltyPolicy = NoveltyPolicy(),
) -> dict[str, Any]:
    if deterministic_fingerprint(candidate) == deterministic_fingerprint(reference):
        return {
            "candidate": candidate.name,
            "reference": reference.name,
            "status": "reject",
            "reason": "deterministic_expression_duplicate",
            "abs_signal_corr": 1.0,
            "rolling": {"windows": [], "max_abs_corr": 1.0, "latest_abs_corr": 1.0},
        }
    candidate_values = evaluate(candidate, panel)
    reference_values = evaluate(reference, panel)
    corr, count = _correlation(
        _cross_section_ranks(candidate_values),
        _cross_section_ranks(reference_values),
        policy.min_observations,
    )
    abs_corr = abs(corr) if not pd.isna(corr) else float("nan")
    rolling = rolling_signal_similarity(
        candidate_values,
        reference_values,
        window_days=policy.rolling_window_days,
        min_observations=policy.min_observations,
    )
    effective = max(
        [value for value in (abs_corr, rolling["latest_abs_corr"]) if not pd.isna(value)],
        default=float("nan"),
    )
    if not pd.isna(effective) and effective >= policy.signal_reject:
        status = "reject"
    elif not pd.isna(effective) and effective >= policy.signal_warn:
        status = "warn"
    else:
        status = "pass"
    return {
        "candidate": candidate.name,
        "reference": reference.name,
        "status": status,
        "reason": "signal_similarity",
        "abs_signal_corr": abs_corr,
        "observations": count,
        "rolling": rolling,
    }


def batch_novelty_review(
    candidates: list[FactorExpr],
    existing_factors: list[FactorExpr],
    panel: pd.DataFrame,
    policy: NoveltyPolicy = NoveltyPolicy(),
) -> tuple[list[FactorExpr], list[dict[str, Any]]]:
    """Reject duplicates against both the library and earlier candidates in this batch."""

    accepted: list[FactorExpr] = []
    decisions: list[dict[str, Any]] = []
    for candidate in candidates:
        reviews: list[dict[str, Any]] = []
        for reference in [*existing_factors, *accepted]:
            try:
                reviews.append(pairwise_signal_review(candidate, reference, panel, policy))
            except (ValueError, KeyError):
                continue
        rejects = [review for review in reviews if review["status"] == "reject"]
        warnings = [review for review in reviews if review["status"] == "warn"]
        if rejects:
            nearest = max(rejects, key=lambda row: row.get("abs_signal_corr", 0.0))
            decision = "reject"
            reason = f"batch novelty reject versus {nearest['reference']}"
        else:
            accepted.append(candidate)
            decision = "warn" if warnings else "pass"
            reason = "batch novelty warning" if warnings else "ok"
        summary = {
            "candidate": candidate.name,
            "decision": decision,
            "reason": reason,
            "comparisons": reviews,
            "policy": asdict(policy),
        }
        candidate.metadata.setdefault("validation", {})["batch_novelty"] = summary
        decisions.append(summary)
    return accepted, decisions


def behavioral_novelty_review(
    candidate_result: dict[str, Any],
    reference_results: list[dict[str, Any]],
    policy: NoveltyPolicy = NoveltyPolicy(),
) -> dict[str, Any]:
    comparisons: list[dict[str, Any]] = []
    for reference in reference_results:
        name = reference.get("summary", {}).get("name") or reference.get("expr", {}).get("name", "unknown")
        ic_corr, ic_count = _correlation(
            candidate_result.get("rank_ic", pd.Series(dtype=float)),
            reference.get("rank_ic", pd.Series(dtype=float)),
            policy.min_observations,
        )
        return_corr, return_count = _correlation(
            candidate_result.get("long_short", pd.Series(dtype=float)),
            reference.get("long_short", pd.Series(dtype=float)),
            policy.min_observations,
        )
        usable = [abs(value) for value in (ic_corr, return_corr) if not pd.isna(value)]
        score = max(usable, default=float("nan"))
        comparisons.append(
            {
                "reference": name,
                "abs_rank_ic_corr": abs(ic_corr) if not pd.isna(ic_corr) else float("nan"),
                "rank_ic_observations": ic_count,
                "abs_long_short_corr": abs(return_corr) if not pd.isna(return_corr) else float("nan"),
                "long_short_observations": return_count,
                "behavior_score": score,
            }
        )
    usable = [row for row in comparisons if not pd.isna(row["behavior_score"])]
    nearest = max(usable, key=lambda row: row["behavior_score"]) if usable else None
    score = nearest["behavior_score"] if nearest else float("nan")
    if not pd.isna(score) and score >= policy.behavior_reject:
        status = "reject"
    elif not pd.isna(score) and score >= policy.behavior_warn:
        status = "warn"
    else:
        status = "pass"
    return {
        "status": status,
        "nearest_factor": nearest["reference"] if nearest else None,
        "max_behavior_score": score,
        "comparisons": comparisons,
        "policy": asdict(policy),
    }


def promotion_decision(
    candidate_result: dict[str, Any],
    signal_review: dict[str, Any],
    reference_results: list[dict[str, Any]],
    policy: NoveltyPolicy = NoveltyPolicy(),
) -> dict[str, Any]:
    behavior = behavioral_novelty_review(candidate_result, reference_results, policy)
    signal_status = signal_review.get("decision", signal_review.get("status", "pass"))
    finite_ic = np.isfinite(candidate_result.get("summary", {}).get("ic_mean", np.nan))
    reasons: list[str] = []
    if signal_status == "reject":
        reasons.append("signal_similarity_reject")
    if behavior["status"] == "reject":
        reasons.append("behavior_similarity_reject")
    if not finite_ic:
        reasons.append("missing_oos_ic")
    return {
        "action": "reject" if reasons else "promote",
        "reasons": reasons or ["passed_deterministic_novelty_and_backtest_availability"],
        "signal_review": signal_review,
        "behavior_review": behavior,
    }


def reassess_library_entry(
    entry: dict[str, Any],
    *,
    as_of: str | pd.Timestamp,
    max_age_days: int = 365,
    recent_behavior_score: float | None = None,
    reject_threshold: float = 0.90,
) -> dict[str, Any]:
    """Make library membership reversible as evidence and market state change."""

    validated_at = pd.Timestamp(entry["last_validated_at"])
    age_days = int((pd.Timestamp(as_of) - validated_at).days)
    reasons: list[str] = []
    if age_days > max_age_days:
        reasons.append("validation_stale")
    if recent_behavior_score is not None and recent_behavior_score >= reject_threshold:
        reasons.append("recent_behavior_converged_with_library")
    return {
        **entry,
        "age_days": age_days,
        "library_status": "demote" if reasons else "active",
        "reassessment_reasons": reasons or ["current"],
    }
