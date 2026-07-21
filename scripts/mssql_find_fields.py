from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


TARGETS = {
    "prices": {
        "table": ["quote", "price", "daily", "trading", "行情", "交易", "日行情", "复权", "adj"],
        "columns": [
            "date",
            "tradingday",
            "tradedate",
            "enddate",
            "secu",
            "code",
            "ticker",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "vol",
            "turnover",
            "amount",
            "adj",
            "factor",
            "mktcap",
            "industry",
        ],
    },
    "fundamentals": {
        "table": ["balance", "income", "cashflow", "financial", "indicator", "forecast", "公告", "财务", "资产负债", "利润", "现金流", "指标", "估值"],
        "columns": [
            "secu",
            "code",
            "ticker",
            "report",
            "period",
            "enddate",
            "ann",
            "announce",
            "publish",
            "disclosure",
            "assets",
            "equity",
            "income",
            "profit",
            "revenue",
            "cash",
            "eps",
            "bps",
            "share",
        ],
    },
    "universe": {
        "table": ["index", "constituent", "component", "universe", "stocklist", "listed", "industry", "st", "suspend", "指数", "成分", "行业", "上市", "停牌"],
        "columns": [
            "date",
            "tradingday",
            "effect",
            "begin",
            "end",
            "secu",
            "code",
            "ticker",
            "weight",
            "constituent",
            "component",
            "listed",
            "delist",
            "industry",
            "suspend",
            "st",
        ],
    },
}


def _norm(value: object) -> str:
    return str(value or "").lower().replace("_", "")


def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    return [keyword for keyword in keywords if keyword.lower().replace("_", "") in text]


def _load_metadata(metadata_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    columns_path = metadata_dir / "columns.csv"
    if not columns_path.exists():
        raise FileNotFoundError(f"Missing {columns_path}; run mssql_tool.py snapshot first.")
    columns = pd.read_csv(columns_path)
    row_counts_path = metadata_dir / "row_counts.csv"
    row_counts = pd.read_csv(row_counts_path) if row_counts_path.exists() else None
    return columns, row_counts


def score_candidates(metadata_dir: Path, top: int = 15) -> dict[str, pd.DataFrame]:
    columns, row_counts = _load_metadata(metadata_dir)
    required = {"table_schema", "table_name", "column_name"}
    missing = required - set(columns.columns)
    if missing:
        raise ValueError(f"columns.csv missing required columns: {sorted(missing)}")

    grouped = columns.groupby(["table_schema", "table_name"], dropna=False)
    scored: dict[str, list[dict]] = {target: [] for target in TARGETS}
    for (schema, table), frame in grouped:
        table_text = _norm(table)
        column_text = " ".join(_norm(value) for value in frame["column_name"].tolist())
        for target, rules in TARGETS.items():
            table_hits = _keyword_hits(table_text, rules["table"])
            column_hits = _keyword_hits(column_text, rules["columns"])
            score = len(table_hits) * 3 + len(set(column_hits))
            if score <= 0:
                continue
            scored[target].append(
                {
                    "target": target,
                    "table_schema": schema,
                    "table_name": table,
                    "score": score,
                    "table_hits": ", ".join(table_hits),
                    "column_hits": ", ".join(sorted(set(column_hits))),
                    "column_count": int(len(frame)),
                    "sample_columns": ", ".join(str(value) for value in frame["column_name"].head(18).tolist()),
                }
            )

    result: dict[str, pd.DataFrame] = {}
    for target, rows in scored.items():
        frame = pd.DataFrame(rows)
        if frame.empty:
            result[target] = frame
            continue
        if row_counts is not None and {"table_schema", "table_name", "row_count"} <= set(row_counts.columns):
            frame = frame.merge(row_counts, on=["table_schema", "table_name"], how="left")
        frame = frame.sort_values(["score", "column_count"], ascending=[False, False]).head(top).reset_index(drop=True)
        result[target] = frame
    return result


def write_markdown(candidates: dict[str, pd.DataFrame], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# MSSQL field candidates", ""]
    for target, frame in candidates.items():
        lines.extend([f"## {target}", ""])
        if frame.empty:
            lines.extend(["No candidates found.", ""])
            continue
        cols = ["table_schema", "table_name", "score", "row_count", "table_hits", "column_hits", "sample_columns"]
        available = [column for column in cols if column in frame.columns]
        lines.append(frame[available].to_markdown(index=False))
        lines.append("")
    output.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rank likely MSSQL tables for project raw data mapping.")
    parser.add_argument("--metadata-dir", type=Path, default=ROOT / "data" / "metadata" / "mssql" / "latest")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--top", type=int, default=15)
    args = parser.parse_args(argv)
    output = args.output or args.metadata_dir / "field_candidates.md"
    candidates = score_candidates(args.metadata_dir, top=args.top)
    write_markdown(candidates, output)
    print(output)


if __name__ == "__main__":
    main()
