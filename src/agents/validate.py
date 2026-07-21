from __future__ import annotations

import json
import ast

import pandas as pd

from src.factors.engine import FactorExpr, evaluate, expression_names
from src.llm.client import LLMClient
from src.llm.prompts import VALIDATE_SEMANTIC_PROMPT


FORBIDDEN_FIELDS = {"fwd_ret", "fwd_ret_1", "fwd_ret_5", "fwd_ret_20", "future_return", "label"}


def _numeric_arg(node: ast.AST) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_arg(node.operand)
        return -value if value is not None else None
    return None


def _validate_time_function_args(expression: str) -> tuple[bool, str]:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return False, f"expression syntax error: {exc}"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        func = node.func.id
        if func in {"delay", "delta", "ts_mean", "ts_std"} and len(node.args) >= 2:
            value = _numeric_arg(node.args[1])
            if value is None:
                continue
            if func == "delay" and value < 0:
                return False, "delay with negative periods would reference future data"
            if func == "delta" and value <= 0:
                return False, "delta periods must be positive"
            if func in {"ts_mean", "ts_std"} and value <= 0:
                return False, f"{func} window must be positive"
    return True, "ok"


def validate(
    expr: FactorExpr,
    field_dict: dict[str, str] | set[str] | list[str],
    panel: pd.DataFrame | None = None,
    existing_factors: list[FactorExpr] | None = None,
    client: LLMClient | None = None,
) -> tuple[bool, str]:
    allowed_fields = set(field_dict if not isinstance(field_dict, dict) else field_dict.keys())
    try:
        used_names = expression_names(expr.expression)
    except SyntaxError as exc:
        return False, f"expression syntax error: {exc}"
    except ValueError as exc:
        return False, f"expression cannot be parsed: {exc}"
    declared = set(expr.fields_used)
    missing = (used_names | declared) - allowed_fields
    if missing:
        return False, f"unknown fields: {sorted(missing)}"
    forbidden = (used_names | declared) & FORBIDDEN_FIELDS
    if forbidden:
        return False, f"future/label fields are forbidden in factor expressions: {sorted(forbidden)}"
    lowered = expr.expression.lower()
    if "shift(-" in lowered or "future" in lowered:
        return False, "expression appears to reference future data"
    ok, reason = _validate_time_function_args(expr.expression)
    if not ok:
        return False, reason
    if panel is not None:
        try:
            evaluated = evaluate(expr, panel)
        except Exception as exc:
            return False, f"expression cannot be evaluated: {exc}"
        if evaluated.dropna().empty:
            return False, "expression evaluates to all NaN"
    if existing_factors:
        duplicate_names = {factor.name for factor in existing_factors}
        if expr.name in duplicate_names:
            return False, f"duplicate factor name: {expr.name}"
        client = client or LLMClient()
        prompt = VALIDATE_SEMANTIC_PROMPT.format(
            existing_factors=[factor.to_dict() for factor in existing_factors], candidate=expr.to_dict()
        )
        try:
            semantic = json.loads(client.generate(prompt))
            if semantic.get("duplicate"):
                return False, f"semantic duplicate: {semantic.get('reason', '')}"
        except Exception:
            pass
    return True, "ok"
