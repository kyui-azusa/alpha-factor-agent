from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import CONFIG, Config
from src.utils.align import pit_merge
from src.utils.field_availability import attach_field_availability, derived_field_metadata, get_field_availability, set_field_metadata
from src.utils.synthetic import make_synthetic_data


def _load_table(name: str, cfg: Config = CONFIG) -> pd.DataFrame | None:
    for suffix, reader in (
        ("parquet", pd.read_parquet),
        ("csv", pd.read_csv),
        ("pkl", pd.read_pickle),
    ):
        path = cfg.raw_dir / f"{name}.{suffix}"
        if path.exists():
            return reader(path)
    return None


def _coerce_dates(df: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = pd.to_datetime(out[column])
    return out


def load_prices(cfg: Config = CONFIG) -> pd.DataFrame:
    data = _load_table("prices", cfg)
    if data is None:
        data, _, _ = make_synthetic_data(cfg.start_date, cfg.end_date)
    data = _coerce_dates(data, ("date",))
    return data.sort_values(["date", "code"]).reset_index(drop=True)


def load_fundamentals(cfg: Config = CONFIG) -> pd.DataFrame:
    data = _load_table("fundamentals", cfg)
    if data is None:
        _, data, _ = make_synthetic_data(cfg.start_date, cfg.end_date)
    data = _coerce_dates(data, ("report_period", "ann_date"))
    return data.sort_values(["code", "ann_date", "report_period"]).reset_index(drop=True)


def load_universe(cfg: Config = CONFIG) -> pd.DataFrame:
    data = _load_table("universe", cfg)
    if data is None:
        _, _, data = make_synthetic_data(cfg.start_date, cfg.end_date)
    data = _coerce_dates(data, ("date",))
    return data.sort_values(["date", "code"]).reset_index(drop=True)


def get_forward_returns(prices: pd.DataFrame, periods: tuple[int, ...] = (1, 5, 20)) -> pd.DataFrame:
    required = {"date", "code", "close"}
    missing = required - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing columns: {sorted(missing)}")
    data = _coerce_dates(prices, ("date",)).sort_values(["code", "date"])
    result = data[["date", "code"]].copy()
    close = data.groupby("code", sort=False)["close"]
    for period in periods:
        result[f"fwd_ret_{period}"] = close.shift(-period).to_numpy() / data["close"].to_numpy() - 1.0
    return result.set_index(["date", "code"]).sort_index()


def build_panel(cfg: Config = CONFIG, save: bool = True) -> pd.DataFrame:
    prices = load_prices(cfg)
    fundamentals = load_fundamentals(cfg)
    universe = load_universe(cfg)[["date", "code"]].drop_duplicates()
    filtered_prices = prices.merge(universe, on=["date", "code"], how="inner")
    panel = pit_merge(filtered_prices, fundamentals)
    panel = _fill_pit_safe_mktcap(panel)
    metadata = get_field_availability(panel)
    panel = panel.set_index(["date", "code"]).sort_index()
    panel = attach_field_availability(panel, metadata)
    if save:
        path = cfg.processed_dir / "panel.parquet"
        _safe_to_parquet(panel, path)
    return panel


def _fill_pit_safe_mktcap(panel: pd.DataFrame) -> pd.DataFrame:
    if "close" not in panel.columns or "shares_outstanding" not in panel.columns:
        return panel
    out = panel.copy()
    inferred = pd.to_numeric(out["close"], errors="coerce") * pd.to_numeric(
        out["shares_outstanding"], errors="coerce"
    )
    if "mktcap" in out.columns:
        out["mktcap"] = pd.to_numeric(out["mktcap"], errors="coerce").fillna(inferred)
    else:
        out["mktcap"] = inferred
    set_field_metadata(
        out,
        "mktcap",
        derived_field_metadata(
            "mktcap",
            ["close", "shares_outstanding"],
            "close multiplied by PIT-merged shares_outstanding when raw market cap is unavailable",
        ),
    )
    return out


def _safe_to_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path)
    except (ImportError, ValueError):
        df.to_pickle(path.with_suffix(".pkl"))


def load_panel(cfg: Config = CONFIG) -> pd.DataFrame:
    path = cfg.processed_dir / "panel.parquet"
    if path.exists():
        return pd.read_parquet(path)
    fallback = path.with_suffix(".pkl")
    if fallback.exists():
        return pd.read_pickle(fallback)
    return build_panel(cfg, save=True)


if __name__ == "__main__":
    panel = build_panel(CONFIG, save=True)
    print(f"panel rows={len(panel)} columns={len(panel.columns)}")
