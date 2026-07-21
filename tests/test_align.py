import pandas as pd

from src.utils.align import pit_merge
from src.utils.data_loader import build_panel


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
