from __future__ import annotations

import json

import pandas as pd

from src.config import CONFIG, Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import FactorExpr, evaluate
from src.utils.data_loader import load_panel


SUMMARY_COLUMNS = [
    "name",
    "IC",
    "ICIR",
    "turnover",
    "net_long_short",
    "max_abs_baseline_corr",
    "expression",
    "economic_rationale",
]


def _factor_from_payload(expr: dict) -> FactorExpr:
    return FactorExpr(
        name=expr["name"],
        expression=expr["expression"],
        economic_rationale=expr["economic_rationale"],
        fields_used=list(expr["fields_used"]),
        formula=expr.get("formula"),
        metadata=expr.get("metadata", {}),
    )


def _max_baseline_corr(expr: FactorExpr, cfg: Config) -> float | None:
    try:
        panel = load_panel(cfg)
        target = evaluate(expr, panel)
        corrs = []
        for baseline in BASELINE_FACTORS:
            base = evaluate(baseline, panel)
            data = pd.concat([target.rename("target"), base.rename("baseline")], axis=1).dropna()
            if len(data) > 2 and data["target"].nunique() > 1 and data["baseline"].nunique() > 1:
                corrs.append(abs(float(data["target"].corr(data["baseline"]))))
        return max(corrs) if corrs else None
    except Exception:
        return None


def summarize_factors(cfg: Config = CONFIG, include_baseline_corr: bool = True) -> pd.DataFrame:
    rows = []
    for path in sorted(cfg.factor_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        expr = payload["expr"]
        summary = payload["summary"]
        factor_expr = _factor_from_payload(expr)
        rows.append(
            {
                "name": expr["name"],
                "IC": summary.get("ic_mean"),
                "ICIR": summary.get("ic_ir"),
                "turnover": summary.get("turnover_mean"),
                "net_long_short": summary.get("net_long_short_mean"),
                "max_abs_baseline_corr": _max_baseline_corr(factor_expr, cfg) if include_baseline_corr else None,
                "expression": expr["expression"],
                "economic_rationale": expr["economic_rationale"],
            }
        )
    frame = pd.DataFrame(rows, columns=SUMMARY_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["ICIR", "IC"], ascending=False, na_position="last")
    return frame


def export_summary(cfg: Config = CONFIG) -> tuple[pd.DataFrame, str]:
    cfg.report_dir.mkdir(parents=True, exist_ok=True)
    frame = summarize_factors(cfg)
    csv_path = cfg.report_dir / "factor_summary.csv"
    md_path = cfg.report_dir / "factor_cards.md"
    frame.to_csv(csv_path, index=False)
    lines = ["# Factor Cards", ""]
    for row in frame.to_dict(orient="records"):
        lines.extend(
            [
                f"## {row['name']}",
                "",
                f"- Expression: `{row['expression']}`",
                f"- IC: `{row['IC']}`",
                f"- ICIR: `{row['ICIR']}`",
                f"- Turnover: `{row['turnover']}`",
                f"- Net long-short: `{row['net_long_short']}`",
                f"- Max abs baseline corr: `{row['max_abs_baseline_corr']}`",
                f"- Economic rationale: {row['economic_rationale']}",
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return frame, str(csv_path)


if __name__ == "__main__":
    summary, path = export_summary()
    print(f"wrote {path} rows={len(summary)}")
