import pandas as pd
import pytest

from src.agents.validate import validate
from src.factors.engine import FactorExpr
from src.utils.align import get_pit_availability_audit, pit_merge
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

    merged = pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col=None)

    before_announcement = merged.loc[merged["date"] == pd.Timestamp("2020-01-03"), "net_income"].iloc[0]
    on_announcement = merged.loc[merged["date"] == pd.Timestamp("2020-01-06"), "net_income"].iloc[0]
    assert before_announcement == 100.0
    assert on_announcement == 100.0


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

    merged = pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col=None)
    metadata = get_field_availability(merged)

    assert metadata["close"]["source"] == "prices"
    assert metadata["net_income"]["source"] == "fundamentals"
    assert metadata["net_income"]["available_date"] == "information_available_at"
    assert metadata["net_income"]["pit_protected"] is True


def test_pit_merge_uses_pre_market_announcement_for_same_day_signal():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-06"]),
            "code": ["A"],
            "close": [12.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-06"]),
            "ann_time": pd.to_datetime(["2020-01-06 08:30:00"]),
            "net_income": [999.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="09:25:00", availability_time_col="ann_time")
    audit = get_pit_availability_audit(merged)

    assert merged.loc[0, "net_income"] == 999.0
    assert audit["publication_status_counts"] == {"exact_pre_market": 1}


def test_pit_merge_blocks_after_market_announcement_from_same_day_signal():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03", "2020-01-06"]),
            "code": ["A", "A"],
            "close": [11.0, 12.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-03"]),
            "ann_time": pd.to_datetime(["2020-01-03 18:00:00"]),
            "net_income": [999.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col="ann_time")
    audit = get_pit_availability_audit(merged)

    assert pd.isna(merged.loc[merged["date"] == pd.Timestamp("2020-01-03"), "net_income"]).all()
    next_day = merged.loc[merged["date"] == pd.Timestamp("2020-01-06")].iloc[0]
    assert next_day["net_income"] == 999.0
    assert audit["publication_status_counts"] == {"exact_after_market": 1}


def test_pit_merge_uses_non_trading_day_announcement_on_next_signal():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03", "2020-01-06"]),
            "code": ["A", "A"],
            "close": [11.0, 12.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-04"]),
            "ann_time": pd.to_datetime(["2020-01-04 12:00:00"]),
            "net_income": [999.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="09:25:00", availability_time_col="ann_time")
    audit = get_pit_availability_audit(merged)

    assert pd.isna(merged.loc[merged["date"] == pd.Timestamp("2020-01-03"), "net_income"]).all()
    next_day = merged.loc[merged["date"] == pd.Timestamp("2020-01-06")].iloc[0]
    assert next_day["net_income"] == 999.0
    assert audit["publication_status_counts"] == {"exact_non_trading_day": 1}


def test_pit_merge_delays_date_only_announcement_and_reports_audit():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-03", "2020-01-06", "2020-01-07"]),
            "code": ["A", "A", "A"],
            "close": [11.0, 12.0, 13.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A", "A"],
            "report_period": pd.to_datetime(["2019-09-30", "2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-03", "2020-01-07"]),
            "ann_time": pd.to_datetime([None, None]),
            "net_income": [100.0, 999.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col="ann_time")
    audit = get_pit_availability_audit(merged)

    assert pd.isna(merged.loc[merged["date"] == pd.Timestamp("2020-01-03"), "net_income"]).all()
    assert merged.loc[merged["date"] == pd.Timestamp("2020-01-06"), "net_income"].iloc[0] == 100.0
    assert merged.loc[merged["date"] == pd.Timestamp("2020-01-07"), "net_income"].iloc[0] == 100.0
    assert audit["publication_status_counts"] == {"date_only": 2}
    assert audit["conservative_delay_count"] == 2
    assert audit["unresolved_date_only_count"] == 1
    assert {"information_available_at", "publication_time_status"}.isdisjoint(merged.columns)


def test_pit_merge_treats_midnight_placeholder_as_date_only():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-06", "2020-01-07"]),
            "code": ["A", "A"],
            "close": [12.0, 13.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-06"]),
            "ann_time": pd.to_datetime(["2020-01-06 00:00:00"]),
            "net_income": [999.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col="ann_time")
    audit = get_pit_availability_audit(merged)

    assert pd.isna(merged.loc[merged["date"] == pd.Timestamp("2020-01-06"), "net_income"]).all()
    assert merged.loc[merged["date"] == pd.Timestamp("2020-01-07"), "net_income"].iloc[0] == 999.0
    assert audit["publication_status_counts"] == {"date_only": 1}
    assert audit["conservative_delay_count"] == 1


def test_pit_merge_uses_per_row_signal_times_for_intraday_boundary():
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-06", "2020-01-06"]),
            "code": ["B", "A"],
            "signal_time": pd.to_datetime(["2020-01-06 14:00:00", "2020-01-06 10:00:00"]),
            "close": [22.0, 12.0],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["A", "B"],
            "report_period": pd.to_datetime(["2019-12-31", "2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-06", "2020-01-06"]),
            "ann_time": pd.to_datetime(["2020-01-06 11:00:00", "2020-01-06 11:00:00"]),
            "net_income": [100.0, 200.0],
        }
    )

    merged = pit_merge(prices, fundamentals, signal_time="signal_time", availability_time_col="ann_time")

    assert pd.isna(merged.loc[merged["code"] == "A", "net_income"]).all()
    assert merged.loc[merged["code"] == "B", "net_income"].iloc[0] == 200.0


def test_pit_merge_rejects_exact_time_on_different_announcement_date():
    prices = pd.DataFrame({"date": pd.to_datetime(["2020-01-06"]), "code": ["A"]})
    fundamentals = pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-06"]),
            "ann_time": pd.to_datetime(["2020-01-07 08:00:00"]),
        }
    )

    with pytest.raises(ValueError, match="matching ann_date"):
        pit_merge(prices, fundamentals, signal_time="15:00:00", availability_time_col="ann_time")


def test_build_panel_creates_non_empty_panel(tmp_path):
    from src.config import Config

    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results")
    cfg.ensure_dirs()
    panel = build_panel(cfg, save=True)
    assert not panel.empty
    assert (cfg.processed_dir / "panel.parquet").exists() or (cfg.processed_dir / "panel.pkl").exists()
    audit = get_pit_availability_audit(panel)
    assert audit["signal_time"] == "15:00:00"
    assert audit["conservative_delay_count"] == audit["total_announcement_records"]


def test_build_panel_requires_explicit_certification_for_exact_announcement_time(tmp_path):
    from src.config import Config

    cfg = Config(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        fundamental_availability_time_col="ann_time",
    )
    cfg.ensure_dirs()
    raw = cfg.raw_dir
    pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-06"]),
            "code": ["A"],
            "close": [10.0],
        }
    ).to_csv(raw / "prices.csv", index=False)
    pd.DataFrame(
        {
            "code": ["A"],
            "report_period": pd.to_datetime(["2019-12-31"]),
            "ann_date": pd.to_datetime(["2020-01-06"]),
            "ann_time": pd.to_datetime(["2020-01-06 08:30:00"]),
            "net_income": [100.0],
        }
    ).to_csv(raw / "fundamentals.csv", index=False)
    pd.DataFrame({"date": pd.to_datetime(["2020-01-06"]), "code": ["A"]}).to_csv(
        raw / "universe.csv", index=False
    )

    panel = build_panel(cfg, save=False)

    assert panel.loc[(pd.Timestamp("2020-01-06"), "A"), "net_income"] == 100.0
    assert get_pit_availability_audit(panel)["availability_time_column"] == "ann_time"


def test_build_panel_rejects_missing_certified_announcement_time_column(tmp_path):
    from src.config import Config

    cfg = Config(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        fundamental_availability_time_col="verified_publish_time",
    )
    cfg.ensure_dirs()

    with pytest.raises(ValueError, match="missing availability time column"):
        build_panel(cfg, save=False)


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
    assert panel.loc[(pd.Timestamp("2020-01-06"), "A"), "mktcap"] == 2000.0
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
