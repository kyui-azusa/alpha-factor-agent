"""Build the static datasets consumed by ``panel/``.

All market calculations happen here. The browser only reads the exported JSON,
combines already-computed return series, and renders charts.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
RESULTS_DIR = ROOT / "results" / "reports" / "baselines"
DEFAULT_OUT_DIR = ROOT / "panel" / "public" / "data"

# Fields allowed in public panel factor payloads. Everything else is dropped.
FACTOR_PUBLIC_FIELDS = {
    "id", "label", "category", "ic_series", "quantile_returns",
    "long_short_nav", "turnover",
}
# Real-data expressions and tuning details must never reach panel artifacts.
FACTOR_REDACTED_FIELDS = {"expression", "params", "window", "threshold", "weights"}

FORECAST_TYPE_LABELS = {
    1: "首亏",
    2: "续亏",
    3: "扭亏",
    4: "预增",
    5: "略增",
    6: "续盈",
    7: "预亏",
    8: "预减",
}

FACTOR_META = {
    "baseline_value_ep_bp": ("价值基线", "价值"),
    "baseline_quality_roe": ("质量基线", "质量"),
    "baseline_momentum_20d": ("动量基线", "动量"),
    "baseline_low_volatility_20d": ("低波动基线", "波动率"),
    "baseline_liquidity_turnover": ("流动性基线", "流动性"),
}

KNOWN_NAMES = {
    "000001.SZ": "平安银行",
    "000002.SZ": "万科A",
    "000333.SZ": "美的集团",
    "000651.SZ": "格力电器",
    "000858.SZ": "五粮液",
    "002415.SZ": "海康威视",
    "300750.SZ": "宁德时代",
    "600036.SH": "招商银行",
    "600519.SH": "贵州茅台",
    "601318.SH": "中国平安",
}


def _json_value(value: Any, digits: int = 6) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (float, np.floating)):
        return round(float(value), digits)
    if isinstance(value, (int, np.integer)):
        return int(value)
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def apply_adjustment_factors(prices: pd.DataFrame, factors: pd.DataFrame) -> pd.DataFrame:
    """Expand factor events backward-asof and return adjusted OHLC plus returns."""
    required_prices = {"date", "code", "open", "high", "low", "close", "vol"}
    required_factors = {"code", "ex_date", "adj_factor"}
    if missing := required_prices - set(prices.columns):
        raise ValueError(f"prices missing columns: {sorted(missing)}")
    if missing := required_factors - set(factors.columns):
        raise ValueError(f"adjustment factors missing columns: {sorted(missing)}")

    px = prices.copy()
    adj = factors.copy()
    px["date"] = pd.to_datetime(px["date"])
    adj["ex_date"] = pd.to_datetime(adj["ex_date"])
    adj = adj.dropna(subset=["adj_factor"]).drop_duplicates(["code", "ex_date"], keep="last")

    merged = pd.merge_asof(
        px.sort_values(["date", "code"]),
        adj.sort_values(["ex_date", "code"])[["code", "ex_date", "adj_factor"]],
        left_on="date",
        right_on="ex_date",
        by="code",
        direction="backward",
    )
    merged["adj_factor"] = merged["adj_factor"].fillna(1.0)
    for column in ("open", "high", "low", "close"):
        merged[column] = merged[column] * merged["adj_factor"]
    merged = merged.sort_values(["code", "date"])
    merged["ret"] = merged.groupby("code", sort=False)["close"].pct_change(fill_method=None)
    return merged.drop(columns=["ex_date"])


def next_trading_days(
    publication_dates: pd.Series, trading_days: pd.DatetimeIndex
) -> pd.Series:
    """Map each publication date to the first strictly later trading day."""
    calendar = pd.DatetimeIndex(trading_days).drop_duplicates().sort_values()
    dates = pd.to_datetime(publication_dates)
    positions = calendar.searchsorted(dates.to_numpy(), side="right")
    values = [calendar[pos] if pos < len(calendar) else pd.NaT for pos in positions]
    result = pd.Series(values, index=publication_dates.index, dtype="datetime64[ns]")
    comparable = result.notna()
    assert (result[comparable] > dates[comparable]).all(), (
        "usable_from must be strictly later than publ_date"
    )
    return result


def sanitize_factor_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on forbidden keys, then retain only the public schema."""
    forbidden = FACTOR_REDACTED_FIELDS.intersection(payload)
    assert not forbidden, f"redacted factor fields present: {sorted(forbidden)}"
    public = {key: payload[key] for key in FACTOR_PUBLIC_FIELDS if key in payload}
    leaked = FACTOR_REDACTED_FIELDS.intersection(public)
    assert not leaked, f"redacted factor fields leaked: {sorted(leaked)}"
    return public


def _load_prices(codes: list[str] | None = None) -> pd.DataFrame:
    prices = pd.read_pickle(RAW_DIR / "prices_raw.pkl")
    if codes is not None:
        prices = prices.loc[prices["code"].isin(codes)].copy()
    return prices


def _load_events() -> pd.DataFrame:
    events = pd.read_pickle(RAW_DIR / "forecasts.pkl")
    events["publ_date"] = pd.to_datetime(events["InfoPublDate"]).dt.normalize()
    events["end_date"] = pd.to_datetime(events["EndDate"])
    suffix = events["SecuMarket"].map({90: ".SZ", 83: ".SH"})
    events["code"] = events["SecuCode"].astype(str).str.zfill(6) + suffix.fillna("")
    events = events.loc[suffix.notna()].copy()
    events = events.drop_duplicates(
        ["code", "publ_date", "end_date", "EGrowthRateFloor", "EGrowthRateCeiling"]
    )
    # Same-day announcements for multiple periods retain the nearest current period.
    return (
        events.sort_values(["code", "publ_date", "end_date"])
        .groupby(["code", "publ_date"], as_index=False)
        .last()
    )


def _industry_by_code() -> dict[str, str]:
    path = RAW_DIR / "industry.csv"
    if not path.exists():
        return {}
    industry = pd.read_csv(path)
    industry["info_publ_date"] = pd.to_datetime(industry["info_publ_date"])
    industry = industry.sort_values("info_publ_date").drop_duplicates("code", keep="last")
    return dict(zip(industry["code"], industry["industry"], strict=False))


def select_default_codes(limit: int = 80) -> list[str]:
    events = _load_events()
    prices = _load_prices()
    available = prices.groupby("code").size()
    eligible = set(available[available >= 250].index)
    event_counts = events.loc[events["code"].isin(eligible), "code"].value_counts()
    preferred = [code for code in KNOWN_NAMES if code in event_counts.index]
    ranked = [code for code in event_counts.index if code not in preferred]
    return (preferred + ranked)[:limit]


def _stock_catalog(codes: list[str]) -> list[dict[str, str]]:
    industry = _industry_by_code()
    return [
        {
            "code": code,
            "name": KNOWN_NAMES.get(code, code),
            "industry": industry.get(code, "未分类"),
        }
        for code in codes
    ]


def export_manifest(out_dir: Path, codes: list[str] | None = None) -> None:
    selected = codes or select_default_codes()
    prices = _load_prices(selected)
    factor_items = [
        {"id": factor_id, "label": label, "category": category}
        for factor_id, (label, category) in FACTOR_META.items()
        if (RESULTS_DIR / factor_id / "report.json").exists()
    ]
    payload = {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "date_range": [
            pd.to_datetime(prices["date"]).min().date().isoformat(),
            pd.to_datetime(prices["date"]).max().date().isoformat(),
        ],
        "stocks": _stock_catalog(selected),
        "factors": factor_items,
    }
    _write_json(out_dir / "manifest.json", payload)


def export_stocks(codes: list[str], out_dir: Path) -> None:
    prices = _load_prices(codes)
    factors = pd.read_csv(RAW_DIR / "adj_factors.csv")
    factors = factors.loc[factors["code"].isin(codes)].copy()
    adjusted = apply_adjustment_factors(prices, factors)
    benchmark_returns = (
        adjusted.dropna(subset=["ret"])
        .groupby("date", as_index=False)["ret"]
        .mean()
        .sort_values("date")
    )
    benchmark_returns["nav"] = (1.0 + benchmark_returns["ret"]).cumprod()
    _write_json(
        out_dir / "benchmark.json",
        {
            "label": "样本股票等权基准",
            "dates": benchmark_returns["date"].dt.strftime("%Y-%m-%d").tolist(),
            "ret": [_json_value(v, 8) for v in benchmark_returns["ret"]],
            "nav": [_json_value(v, 8) for v in benchmark_returns["nav"]],
        },
    )
    catalog = {item["code"]: item for item in _stock_catalog(codes)}
    for code, frame in adjusted.groupby("code", sort=False):
        frame = frame.sort_values("date")
        meta = catalog[code]
        payload = {
            **meta,
            "dates": frame["date"].dt.strftime("%Y-%m-%d").tolist(),
            "ohlc": [
                [_json_value(v, 4) for v in row]
                for row in frame[["open", "high", "low", "close"]].itertuples(index=False, name=None)
            ],
            "volume": [_json_value(v, 0) for v in frame["vol"]],
            "ret": [_json_value(v, 8) for v in frame["ret"]],
        }
        _write_json(out_dir / "stocks" / f"{code}.json", payload)


def export_events(out_dir: Path) -> None:
    events = _load_events()
    trading_days = pd.DatetimeIndex(
        pd.to_datetime(_load_prices()["date"]).drop_duplicates().sort_values()
    )
    events["usable_from"] = next_trading_days(events["publ_date"], trading_days)
    events = events.dropna(subset=["usable_from"])
    assert (events["usable_from"] > events["publ_date"]).all()
    records = []
    for row in events.itertuples(index=False):
        records.append(
            {
                "code": row.code,
                "publ_date": row.publ_date.date().isoformat(),
                "usable_from": row.usable_from.date().isoformat(),
                "type": FORECAST_TYPE_LABELS.get(row.ForcastType, "其他"),
                "growth_floor": _json_value(row.EGrowthRateFloor, 2),
                "growth_ceiling": _json_value(row.EGrowthRateCeiling, 2),
            }
        )
    _write_json(out_dir / "events.json", {"events": records})


def export_factor_result(factor_id: str, out_dir: Path) -> None:
    if factor_id not in FACTOR_META:
        raise ValueError(f"factor is not public: {factor_id}")
    source_path = RESULTS_DIR / factor_id / "report.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    label, category = FACTOR_META[factor_id]

    ic_series = [
        {"date": item["date"][:10], "value": item["rank_ic"]}
        for item in source.get("rank_ic", [])
    ]
    quantile_rows = source.get("quantile_returns", [])
    quantile_returns: dict[str, float] = {}
    if quantile_rows:
        keys = [key for key in quantile_rows[0] if key != "date"]
        quantile_returns = {
            key: float(np.nanmean([row.get(key, np.nan) for row in quantile_rows]))
            for key in keys
        }

    nav = 1.0
    long_short_nav = []
    for item in source.get("net_long_short", source.get("long_short", [])):
        value = item.get("net_long_short", item.get("long_short"))
        if value is None:
            continue
        nav *= 1.0 + float(value)
        long_short_nav.append({"date": item["date"][:10], "value": nav})

    payload = sanitize_factor_payload(
        {
            "id": factor_id,
            "label": label,
            "category": category,
            "ic_series": ic_series,
            "quantile_returns": quantile_returns,
            "long_short_nav": long_short_nav,
            "turnover": [
                {"date": item["date"][:10], "value": item["turnover"]}
                for item in source.get("turnover", [])
            ],
        }
    )
    assert not FACTOR_REDACTED_FIELDS.intersection(payload)
    _write_json(out_dir / "factors" / f"{factor_id}.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export static Alpha research panel data")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument("--codes", nargs="*")
    args = parser.parse_args()

    codes = args.codes or select_default_codes(args.limit)
    if len(codes) < 50 and not args.codes:
        raise RuntimeError("panel export requires at least 50 eligible stocks")
    export_manifest(args.out_dir, codes)
    export_stocks(codes, args.out_dir)
    export_events(args.out_dir)
    for factor_id in FACTOR_META:
        if (RESULTS_DIR / factor_id / "report.json").exists():
            export_factor_result(factor_id, args.out_dir)
    print(f"Exported {len(codes)} stocks to {args.out_dir}")


if __name__ == "__main__":
    main()
