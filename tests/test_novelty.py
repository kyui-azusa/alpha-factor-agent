import pandas as pd

from src.agents.novelty import (
    NoveltyPolicy,
    batch_novelty_review,
    behavioral_novelty_review,
    promotion_decision,
    reassess_library_entry,
    rolling_signal_similarity,
)
from src.config import Config
from src.factors.engine import FactorExpr, evaluate
from src.utils.data_loader import build_panel


def _panel():
    cfg = Config(start_date="2020-01-01", end_date="2020-06-30", train_end="2020-03-31")
    return build_panel(cfg, save=False)


def test_batch_review_rejects_candidate_to_candidate_reskin():
    panel = _panel()
    first = FactorExpr("first", "rank(eps)", "first", ["eps"])
    reskin = FactorExpr("reskin", "2 * rank(eps) + 7", "same ranks", ["eps"])

    accepted, decisions = batch_novelty_review([first, reskin], [], panel)

    assert [factor.name for factor in accepted] == ["first"]
    assert decisions[1]["decision"] == "reject"
    assert decisions[1]["comparisons"][0]["reference"] == "first"


def test_rolling_similarity_detects_recent_style_convergence():
    dates = pd.date_range("2020-01-01", periods=8)
    index = pd.MultiIndex.from_product([dates, list("ABCD")], names=["date", "code"])
    reference = pd.Series(list(range(4)) * 8, index=index, dtype=float)
    candidate = reference.copy()
    candidate.loc[pd.IndexSlice[dates[:4], :]] = list(reversed(range(4))) * 4

    review = rolling_signal_similarity(candidate, reference, window_days=4, min_observations=8)

    assert review["latest_abs_corr"] == 1.0
    assert len(review["windows"]) == 2


def test_behavioral_review_uses_rank_ic_and_long_short_paths():
    dates = pd.date_range("2020-01-01", periods=30)
    candidate = {
        "summary": {"name": "candidate", "ic_mean": 0.02},
        "rank_ic": pd.Series(range(30), index=dates, dtype=float),
        "long_short": pd.Series(range(30), index=dates, dtype=float),
    }
    reference = {
        "summary": {"name": "reference"},
        "rank_ic": candidate["rank_ic"] * 2,
        "long_short": candidate["long_short"] * -3,
    }

    review = behavioral_novelty_review(candidate, [reference])

    assert review["status"] == "reject"
    assert review["nearest_factor"] == "reference"


def test_promotion_requires_novel_signal_behavior_and_finite_backtest():
    dates = pd.date_range("2020-01-01", periods=30)
    result = {
        "summary": {"name": "candidate", "ic_mean": 0.01},
        "rank_ic": pd.Series(range(30), index=dates, dtype=float),
        "long_short": pd.Series(range(30), index=dates, dtype=float),
    }

    decision = promotion_decision(result, {"decision": "pass"}, [], NoveltyPolicy())

    assert decision["action"] == "promote"


def test_library_reassessment_can_demote_stale_or_converged_factors():
    stale = reassess_library_entry(
        {"name": "old", "last_validated_at": "2020-01-01"},
        as_of="2022-01-01",
        recent_behavior_score=0.95,
    )

    assert stale["library_status"] == "demote"
    assert set(stale["reassessment_reasons"]) == {"validation_stale", "recent_behavior_converged_with_library"}
