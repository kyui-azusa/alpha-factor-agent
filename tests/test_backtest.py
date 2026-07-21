import numpy as np
import pandas as pd

from src.backtest.metrics import rank_ic
from src.backtest.report import to_report
from src.backtest.runner import backtest
from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr
from src.utils.data_loader import build_panel, get_forward_returns, load_prices


def test_future_return_sanity_check_has_rank_ic_one():
    idx = pd.MultiIndex.from_product([pd.date_range("2020-01-01", periods=4), list("ABC")], names=["date", "code"])
    fwd = pd.Series(np.tile([0.01, 0.02, 0.03], 4), index=idx, name="fwd_ret_1")
    ic = rank_ic(fwd, fwd)
    assert np.isclose(ic.mean(), 1.0)


def test_random_factor_rank_ic_near_zero():
    idx = pd.MultiIndex.from_product([pd.date_range("2020-01-01", periods=80), [f"S{i:02d}" for i in range(30)]], names=["date", "code"])
    rng = np.random.default_rng(3)
    factor = pd.Series(rng.normal(size=len(idx)), index=idx)
    fwd = pd.Series(rng.normal(size=len(idx)), index=idx)
    ic = rank_ic(factor, fwd)
    assert abs(ic.mean()) < 0.08


def test_backtest_baseline_writes_report(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", train_end="2020-12-31")
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=True)
    fwd = get_forward_returns(load_prices(cfg), periods=(5,))
    result = backtest(BASELINE_FACTORS[0], panel, fwd, cfg=cfg, n_quantiles=3)
    report_dir = to_report(result, tmp_path / "report")
    assert (report_dir / "report.json").exists()
    assert (report_dir / "summary.png").exists()
    assert result["summary"]["observations"] > 0


def test_backtest_does_not_need_llm():
    expr = FactorExpr("simple", "rank(eps)", "test", ["eps"])
    panel = build_panel(save=False)
    fwd = get_forward_returns(load_prices(), periods=(5,))
    result = backtest(expr, panel, fwd, n_quantiles=3)
    assert "summary" in result
