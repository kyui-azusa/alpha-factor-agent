from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype


MAX_AST_NODES = 64
MAX_AST_DEPTH = 12
MAX_TIME_WINDOW = 252


@dataclass
class FactorExpr:
    name: str
    expression: str
    economic_rationale: str
    fields_used: list[str]
    formula: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["formula"] = self.formula or self.expression
        return data


ALLOWED_AST_NODES = (
    ast.Expression,
    ast.BinOp,
    ast.UnaryOp,
    ast.Call,
    ast.Name,
    ast.Load,
    ast.Constant,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
    ast.USub,
    ast.UAdd,
)


def _ast_depth(node: ast.AST) -> int:
    children = list(ast.iter_child_nodes(node))
    if not children:
        return 1
    return 1 + max(_ast_depth(child) for child in children)


def _numeric_constant(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_constant(node.operand)
        return -value if value is not None else None
    return None


def _validate_complexity(tree: ast.AST) -> None:
    nodes = list(ast.walk(tree))
    if len(nodes) > MAX_AST_NODES:
        raise ValueError(f"Expression is too complex: node_count={len(nodes)} max={MAX_AST_NODES}")
    depth = _ast_depth(tree)
    if depth > MAX_AST_DEPTH:
        raise ValueError(f"Expression is too deeply nested: depth={depth} max={MAX_AST_DEPTH}")


def _validate_ast(tree: ast.AST, allowed_names: set[str], allowed_funcs: set[str]) -> None:
    _validate_complexity(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_AST_NODES):
            raise ValueError(f"Unsupported expression syntax: {type(node).__name__}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id not in allowed_names and node.id not in allowed_funcs:
            raise ValueError(f"Unknown field or function: {node.id}")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed_funcs:
                raise ValueError("Only registered factor functions can be called")
            if node.keywords:
                raise ValueError("Keyword arguments are not supported in factor expressions")
            if node.func.id == "where":
                if len(node.args) != 3:
                    raise ValueError("where requires condition, on_true, and on_false")
                if not isinstance(node.args[0], ast.Name) or not node.args[0].id.startswith("regime_"):
                    raise ValueError("where condition must be a registered regime_ field")
            if node.func.id in {"delay", "delta", "ts_mean", "ts_std"} and len(node.args) >= 2:
                value = _numeric_constant(node.args[1])
                if value is None:
                    raise ValueError(f"{node.func.id} window/period argument must be a numeric constant")
                if abs(value) > MAX_TIME_WINDOW:
                    raise ValueError(
                        f"{node.func.id} window/period is too large: value={value:g} max={MAX_TIME_WINDOW}"
                    )


def cs_rank(s: pd.Series) -> pd.Series:
    return s.groupby(level="date").rank(pct=True)


def rank(s: pd.Series) -> pd.Series:
    return cs_rank(s)


def ts_mean(s: pd.Series, window: int) -> pd.Series:
    if int(window) <= 0:
        raise ValueError("ts_mean window must be positive")
    return s.groupby(level="code", group_keys=False).transform(lambda x: x.rolling(int(window), min_periods=int(window)).mean())


def ts_std(s: pd.Series, window: int) -> pd.Series:
    if int(window) <= 0:
        raise ValueError("ts_std window must be positive")
    return s.groupby(level="code", group_keys=False).transform(lambda x: x.rolling(int(window), min_periods=int(window)).std(ddof=0))


def delay(s: pd.Series, periods: int = 1) -> pd.Series:
    if int(periods) < 0:
        raise ValueError("delay periods must be non-negative")
    return s.groupby(level="code", group_keys=False).shift(int(periods))


def delta(s: pd.Series, periods: int = 1) -> pd.Series:
    if int(periods) <= 0:
        raise ValueError("delta periods must be positive")
    return s - delay(s, int(periods))


def signed_log(s: pd.Series) -> pd.Series:
    return np.sign(s) * np.log1p(np.abs(s))


def safe_div(left: pd.Series | float, right: pd.Series | float) -> pd.Series | float:
    if isinstance(right, pd.Series):
        return left / right.replace(0, np.nan)
    return left / (right if right != 0 else np.nan)


def where(
    condition: pd.Series,
    on_true: pd.Series | float,
    on_false: pd.Series | float,
) -> pd.Series:
    if not isinstance(condition, pd.Series):
        raise ValueError("where condition must be a registered binary state field")
    observed = set(pd.to_numeric(condition, errors="coerce").dropna().unique())
    if not observed <= {0.0, 1.0}:
        raise ValueError("where condition must contain only binary 0/1 state values")
    if isinstance(on_true, pd.Series):
        index = on_true.index
    elif isinstance(on_false, pd.Series):
        index = on_false.index
    else:
        index = condition.index
    mask = condition.reindex(index).astype("boolean")
    true_value = on_true.reindex(index) if isinstance(on_true, pd.Series) else on_true
    false_value = on_false.reindex(index) if isinstance(on_false, pd.Series) else on_false
    return pd.Series(np.where(mask.fillna(False), true_value, false_value), index=index).where(mask.notna())


FACTOR_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "abs": abs,
    "cs_rank": cs_rank,
    "rank": rank,
    "ts_mean": ts_mean,
    "ts_std": ts_std,
    "delay": delay,
    "delta": delta,
    "signed_log": signed_log,
    "safe_div": safe_div,
    "where": where,
}


def evaluate(expr: FactorExpr, panel: pd.DataFrame) -> pd.Series:
    if not isinstance(panel.index, pd.MultiIndex) or list(panel.index.names)[:2] != ["date", "code"]:
        raise ValueError("panel must use MultiIndex[date, code]")
    missing = set(expr.fields_used) - set(panel.columns)
    if missing:
        raise ValueError(f"panel missing fields for factor {expr.name}: {sorted(missing)}")

    panel_sorted = panel.sort_index()
    env: dict[str, Any] = {}
    for column in panel_sorted.columns:
        series = panel_sorted[column]
        env[column] = series if not is_numeric_dtype(series) else pd.to_numeric(series)
    env.update(FACTOR_FUNCTIONS)
    tree = ast.parse(expr.expression, mode="eval")
    _validate_ast(tree, set(panel_sorted.columns), set(FACTOR_FUNCTIONS))
    value = eval(compile(tree, "<factor-expression>", "eval"), {"__builtins__": {}}, env)
    if not isinstance(value, pd.Series):
        value = pd.Series(value, index=panel_sorted.index)
    value = pd.to_numeric(value, errors="coerce")
    value.name = expr.name
    return value.sort_index()


def expression_names(expression: str) -> set[str]:
    tree = ast.parse(expression, mode="eval")
    _validate_complexity(tree)
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} - set(FACTOR_FUNCTIONS)
