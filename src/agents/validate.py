from __future__ import annotations

import json
import ast

import pandas as pd

from src.factors.engine import FACTOR_FUNCTIONS, MAX_TIME_WINDOW, FactorExpr, evaluate, expression_names
from src.llm.client import LLMClient
from src.llm.prompts import VALIDATE_SEMANTIC_PROMPT
from src.utils.field_availability import validate_field_availability


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
                return False, f"{func} window/period argument must be a numeric constant"
            if func == "delay" and value < 0:
                return False, "delay with negative periods would reference future data"
            if func == "delta" and value <= 0:
                return False, "delta periods must be positive"
            if func in {"ts_mean", "ts_std"} and value <= 0:
                return False, f"{func} window must be positive"
            if abs(value) > MAX_TIME_WINDOW:
                return False, f"{func} window/period exceeds max {MAX_TIME_WINDOW}"
    return True, "ok"


def _metadata_warnings(expr: FactorExpr) -> list[str]:
    warnings: list[str] = []
    metadata = expr.metadata or {}
    status = metadata.get("backtestable_status")
    if status and status != "currently_backtestable":
        warnings.append(f"candidate status is {status}")
    for key in ("alpha_target", "economic_mechanism", "risk_exposures", "validation_notes"):
        if key not in metadata:
            warnings.append(f"metadata missing {key}")
    return warnings


def deterministic_fingerprint(expr: FactorExpr) -> str:
    try:
        tree = ast.parse(expr.expression, mode="eval")
    except SyntaxError:
        return expr.expression.replace(" ", "").lower()

    def render(node: ast.AST) -> str:
        if isinstance(node, ast.Expression):
            return render(node.body)
        if isinstance(node, ast.Name):
            return node.id.lower()
        if isinstance(node, ast.Constant):
            return "num" if isinstance(node.value, (int, float)) else repr(node.value)
        if isinstance(node, ast.UnaryOp):
            return f"{type(node.op).__name__}({render(node.operand)})"
        if isinstance(node, ast.BinOp):
            return f"{type(node.op).__name__}({render(node.left)},{render(node.right)})"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args = ",".join(render(arg) for arg in node.args)
            return f"{node.func.id.lower()}({args})"
        return type(node).__name__

    return render(tree)


def _factor_fields(expr: FactorExpr) -> set[str]:
    try:
        parsed_fields = expression_names(expr.expression)
    except Exception:
        parsed_fields = set()
    return parsed_fields | set(expr.fields_used)


def _novelty_evidence(
    *,
    candidate: FactorExpr,
    existing: FactorExpr,
    similarity_type: str,
    candidate_fingerprint: str,
    existing_fingerprint: str,
    abs_corr: float | None,
    threshold: float | None,
    corr_warn: float,
    corr_reject: float,
    status: str,
    reason: str,
) -> dict:
    return {
        "candidate_name": candidate.name,
        "nearest_factor": existing.name,
        "similarity_type": similarity_type,
        "shared_fields": sorted(_factor_fields(candidate) & _factor_fields(existing)),
        "candidate_fingerprint": candidate_fingerprint,
        "nearest_fingerprint": existing_fingerprint,
        "abs_corr": abs_corr,
        "threshold": threshold,
        "corr_warn_threshold": corr_warn,
        "corr_reject_threshold": corr_reject,
        "decision": status,
        "status": status,
        "reason": reason,
    }


def novelty_review(
    expr: FactorExpr,
    evaluated: pd.Series,
    existing_factors: list[FactorExpr],
    panel: pd.DataFrame,
    *,
    corr_reject: float = 0.90,
    corr_warn: float = 0.65,
) -> tuple[bool, str, dict]:
    expr_fp = deterministic_fingerprint(expr)
    max_corr = 0.0
    max_name: str | None = None
    max_factor: FactorExpr | None = None
    max_fp: str | None = None
    for existing in existing_factors:
        existing_fp = deterministic_fingerprint(existing)
        if existing_fp == expr_fp:
            reason = f"deterministic duplicate expression: {existing.name}"
            evidence = _novelty_evidence(
                candidate=expr,
                existing=existing,
                similarity_type="deterministic_duplicate",
                candidate_fingerprint=expr_fp,
                existing_fingerprint=existing_fp,
                abs_corr=1.0,
                threshold=1.0,
                corr_warn=corr_warn,
                corr_reject=corr_reject,
                status="reject",
                reason=reason,
            )
            return False, reason, {
                "max_abs_existing_corr": 1.0,
                "nearest_factor": existing.name,
                "corr_warn_threshold": corr_warn,
                "corr_reject_threshold": corr_reject,
                "status": "reject",
                "evidence": [evidence],
                "reason": reason,
            }
        try:
            base = evaluate(existing, panel)
        except Exception:
            continue
        aligned = pd.concat([evaluated.rename("candidate"), base.rename("existing")], axis=1).dropna()
        if len(aligned) < 3 or aligned["candidate"].nunique() < 2 or aligned["existing"].nunique() < 2:
            continue
        corr = abs(float(aligned["candidate"].corr(aligned["existing"])))
        if corr > max_corr:
            max_corr = corr
            max_name = existing.name
            max_factor = existing
            max_fp = existing_fp
    review = {
        "max_abs_existing_corr": max_corr,
        "nearest_factor": max_name,
        "corr_warn_threshold": corr_warn,
        "corr_reject_threshold": corr_reject,
        "status": "pass",
        "evidence": [],
    }
    if max_corr >= corr_reject:
        reason = f"factor is too correlated with existing factor {max_name}: {max_corr:.3f}"
        review["status"] = "reject"
        review["reason"] = reason
        if max_factor is not None and max_fp is not None:
            review["evidence"] = [
                _novelty_evidence(
                    candidate=expr,
                    existing=max_factor,
                    similarity_type="high_correlation_reject",
                    candidate_fingerprint=expr_fp,
                    existing_fingerprint=max_fp,
                    abs_corr=max_corr,
                    threshold=corr_reject,
                    corr_warn=corr_warn,
                    corr_reject=corr_reject,
                    status="reject",
                    reason=reason,
                )
            ]
        return False, reason, review
    if max_corr >= corr_warn:
        reason = f"ok; novelty warning versus {max_name}: abs_corr={max_corr:.3f}"
        review["status"] = "warn"
        review["reason"] = reason
        if max_factor is not None and max_fp is not None:
            review["evidence"] = [
                _novelty_evidence(
                    candidate=expr,
                    existing=max_factor,
                    similarity_type="high_correlation_warn",
                    candidate_fingerprint=expr_fp,
                    existing_fingerprint=max_fp,
                    abs_corr=max_corr,
                    threshold=corr_warn,
                    corr_warn=corr_warn,
                    corr_reject=corr_reject,
                    status="warn",
                    reason=reason,
                )
            ]
        return True, reason, review
    return True, "ok", review


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
    unexpected_funcs = expression_names(expr.expression) & set(FACTOR_FUNCTIONS)
    if unexpected_funcs:
        return False, f"internal parser error, functions treated as fields: {sorted(unexpected_funcs)}"
    ok, reason = _validate_time_function_args(expr.expression)
    if not ok:
        return False, reason
    if panel is not None:
        ok, reason = validate_field_availability(used_names | declared, panel)
        if not ok:
            return False, reason
        try:
            evaluated = evaluate(expr, panel)
        except Exception as exc:
            return False, f"expression cannot be evaluated: {exc}"
        if evaluated.dropna().empty:
            return False, "expression evaluates to all NaN"
        if existing_factors:
            ok, novelty_reason, review = novelty_review(expr, evaluated, existing_factors, panel)
            expr.metadata.setdefault("validation", {})["novelty"] = review
            if not ok:
                return False, novelty_reason
            if novelty_reason != "ok":
                expr.metadata.setdefault("validation", {})["warning"] = novelty_reason
    warnings = _metadata_warnings(expr)
    if warnings:
        expr.metadata.setdefault("validation", {})["metadata_warnings"] = warnings
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
