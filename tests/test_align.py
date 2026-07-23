import pandas as pd

from src.agents.validate import validate
from src.factors.engine import FactorExpr
from src.utils.align import pit_merge
from src.utils.data_loader import build_panel
from src.utils.field_availability import get_field_availability


def test_pit_merge_does_not_use_future_announcements():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-02", "2020-01-03", "2020-01-06"]),
            "code": ["A", "A", "A"],
            "close": [10.0, 11.0, 12.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A", "A"],
            "report_period": pd.to_datetime(["2019-09-30", "2019-12-31"]),
            "ann_date": pd.to_datetime(["2019-12-31", "2020-01-06"]),
            "net_income": [100.0, 999.0],
        }
    )

    merged = pit_merge(prices, fundamentals)

    before_announcement = merged.loc[merged["date"] == pd.Timestamp("2020-01-03"), "net_income"].iloc[0]
    on_announcement = merged.loc[merged["date"] == pd.Timestamp("2020-01-06"), "net_income"].iloc[0]
    assert before_announcement == 100.0
    assert on_announcement == 999.0


def test_pit_merge_attaches_ann_date_availability_metadata():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03"]),
            "code": ["A"],
            "close": [11.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-09-30"]),
            "ann_date": pd.to_datetime(["2019-12-31"]),
            "net_income": [100.0],
        }
    )

    merged = pit_merge(prices, fundamentals)
    metadata = get_field_availability(merged)

    assert metadata["close"]["source"] == "prices"
    assert metadata["net_income"]["source"] == "fundamentals"
    assert metadata["net_income"]["available_date"] == "ann_date"
    assert metadata["net_income"]["pit_protected"] is True


def test_build_panel_creates_non_empty_panel(tmp_path):
    from src.config import Config

    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results")
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=True)
    assert not panel.empty
    assert (cfg.processed_dir / "panel.parquet").exists() or (cfg.processed_dir / "panel.pkl").exists()


def test_build_panel_infers_mktcap_after_pit_merge(tmp_path):
    from src.config import Config

    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results")
    cfg.ensure_dirs()
    raw = cfg.raw_dir
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03", "2020-01-06"]),
            "code": ["A", "A"],
            "open": [10.0, 20.0],
            "high": [10.0, 20.0],
            "low": [10.0, 20.0],
            "close": [10.0, 20.0],
            "vol": [1000.0, 2000.0],
            "amount": [10000.0, 40000.0],
            "adj_factor": [1.0, 1.0],
        }
    ).to_csv(raw / "prices.csv", index=False)
    pd.DataFrame(
        {
            "code": ["A", "A"],
            "report_period": pd.to_datetime(["2019-09-30", "2019-12-31"]),
            "ann_date": pd.to_datetime(["2019-12-31", "2020-01-06"]),
            "shares_outstanding": [100.0, 999.0],
        }
    ).to_csv(raw / "fundamentals.csv", index=False)
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03", "2020-01-06"]),
            "code": ["A", "A"],
            "weight": [1.0, 1.0],
        }
    ).to_csv(raw / "universe.csv", index=False)

    panel = build_panel(cfg, save=False)

    assert panel.loc[(pd.Timestamp("2020-01-03"), "A"), "mktcap"] == 1000.0
    assert panel.loc[(pd.Timestamp("2020-01-06"), "A"), "mktcap"] == 19980.0
    metadata = get_field_availability(panel)
    assert metadata["mktcap"]["source"] == "derived"
    assert metadata["mktcap"]["inputs"] == ["close", "shares_outstanding"]


def test_validate_rejects_fundamental_field_without_pit_metadata():
    panel = build_panel(save=False)
    raw_panel = panel.copy()
    raw_panel.attrs.clear()
    expr = FactorExpr(
        name="raw_roe",
        expression="rank(safe_div(net_income, total_equity))",
        economic_rationale="quality test",
        fields_used=["net_income", "total_equity"],
    )

    ok, reason = validate(expr, set(raw_panel.columns), panel=raw_panel)

    assert not ok
    assert "availability metadata" in reason


def test_validate_rejects_mktcap_without_availability_metadata():
    panel = build_panel(save=False)
    raw_panel = panel.copy()
    raw_panel.attrs.clear()
    expr = FactorExpr(
        name="raw_liquidity",
        expression="rank(-safe_div(amount, mktcap))",
        economic_rationale="liquidity test",
        fields_used=["amount", "mktcap"],
    )

    ok, reason = validate(expr, set(raw_panel.columns), panel=raw_panel)

    assert not ok
    assert "mktcap" in reason


def test_validate_accepts_pit_proven_fundamental_fields():
    panel = build_panel(save=False)
    expr = FactorExpr(
        name="pit_roe",
        expression="rank(safe_div(net_income, total_equity))",
        economic_rationale="quality test",
        fields_used=["net_income", "total_equity"],
    )

    ok, reason = validate(expr, set(panel.columns), panel=panel)

    assert ok, reason
