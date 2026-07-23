from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
import hashlib
import json
from typing import Any, Iterable

from src.agents.validate import is_forbidden_field
from src.factors.engine import FACTOR_FUNCTIONS, MAX_TIME_WINDOW


SUPPORTED_FREQUENCIES = {"D"}
SUPPORTED_DATA_MODES = {"real", "synthetic", "unavailable"}
SUPPORTED_OOS_SPLITS = {"date_ordered_train_end_exclusive", "walk_forward"}
TERMINAL_STATES = {"positive", "negative", "insufficient_evidence"}
ARITHMETIC_OPERATORS = {"add", "sub", "mul", "div", "pow", "mod"}
SUPPORTED_OPERATORS = frozenset(FACTOR_FUNCTIONS) | ARITHMETIC_OPERATORS


@dataclass(frozen=True)
class ContractIssue:
    code: str
    field: str
    message: str
    remediation: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ResearchRequest:
    raw_question: str
    hypothesis: str
    universe: str | None
    start_date: str | None
    end_date: str | None
    event_scope: tuple[str, ...] = ()
    field_scope: tuple[str, ...] = ()
    target_horizon_days: int | None = None
    baseline: str | None = None
    allowed_fields: tuple[str, ...] = ()
    allowed_operators: tuple[str, ...] = ()
    candidate_count: int = 5
    rounds: int = 1
    hold_period_days: int | None = None
    quantiles: int = 5
    cost_bps: float = 10.0
    oos_split: str = "date_ordered_train_end_exclusive"
    success_criteria: tuple[str, ...] = ()
    final_states: tuple[str, ...] = ("positive", "negative", "insufficient_evidence")
    data_mode: str | None = None
    frequency: str = "D"
    pit_enabled: bool = True
    backtest_llm_enabled: bool = False
    oos_feedback_enabled: bool = False
    confirmed: bool = False
    request_id: str | None = None
    version: str | None = None

    @property
    def target_return_field(self) -> str | None:
        if self.target_horizon_days is None:
            return None
        return f"fwd_ret_{self.target_horizon_days}"

    @property
    def can_enter_generation(self) -> bool:
        return False

    def contract_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("confirmed", "request_id", "version"):
            payload.pop(key)
        return payload

    def fingerprint(self) -> str:
        return _fingerprint(self.contract_payload())

    @property
    def expected_request_id(self) -> str:
        return f"req_{self.fingerprint()[:16]}"

    @property
    def expected_version(self) -> str:
        return f"v1-{self.fingerprint()[:12]}"

    @property
    def has_valid_confirmation(self) -> bool:
        return (
            self.confirmed
            and self.request_id == self.expected_request_id
            and self.version == self.expected_version
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["target_return_field"] = self.target_return_field
        payload["contract_fingerprint"] = self.fingerprint()
        payload["can_enter_generation"] = self.can_enter_generation
        return payload


@dataclass(frozen=True)
class ContractReview:
    request: ResearchRequest
    issues: tuple[ContractIssue, ...]

    @property
    def can_confirm(self) -> bool:
        return not self.issues

    @property
    def clarification_fields(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(issue.field for issue in self.issues))

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_confirm": self.can_confirm,
            "can_enter_generation": False,
            "clarification_fields": list(self.clarification_fields),
            "issues": [issue.to_dict() for issue in self.issues],
            "request": self.request.to_dict(),
        }


class ContractValidationError(ValueError):
    def __init__(self, review: ContractReview):
        self.review = review
        details = "; ".join(f"{issue.field}: {issue.message}" for issue in review.issues)
        super().__init__(f"research request cannot be confirmed: {details}")


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _missing(field: str, message: str) -> ContractIssue:
    return ContractIssue(
        code=f"contract.missing_{field}",
        field=field,
        message=message,
        remediation=f"Provide an explicit {field} and review the confirmation summary.",
    )


def _unknown_values(values: Iterable[str], known: set[str] | frozenset[str]) -> list[str]:
    return sorted(set(values) - set(known))


def _parse_date(value: str | None, field: str, issues: list[ContractIssue]) -> date | None:
    if not value:
        issues.append(_missing(field, f"{field} is required"))
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        issues.append(
            ContractIssue(
                code="contract.invalid_date",
                field=field,
                message=f"{value!r} is not an ISO calendar date",
                remediation="Use YYYY-MM-DD.",
            )
        )
        return None


def review_request(
    request: ResearchRequest,
    *,
    known_fields: Iterable[str] | None = None,
    known_universes: Iterable[str] | None = None,
) -> ContractReview:
    issues: list[ContractIssue] = []
    if not request.raw_question.strip():
        issues.append(_missing("raw_question", "the original user question is required"))
    if not request.hypothesis.strip():
        issues.append(_missing("hypothesis", "an explicit, falsifiable hypothesis is required"))
    if not request.universe:
        issues.append(_missing("universe", "a historical stock universe is required"))
    elif known_universes is not None and request.universe not in set(known_universes):
        issues.append(
            ContractIssue(
                code="contract.unknown_universe",
                field="universe",
                message=f"unknown universe: {request.universe}",
                remediation="Choose a universe with historical membership evidence.",
            )
        )

    start = _parse_date(request.start_date, "start_date", issues)
    end = _parse_date(request.end_date, "end_date", issues)
    if start is not None and end is not None and start > end:
        issues.append(
            ContractIssue(
                code="contract.conflicting_dates",
                field="date_range",
                message="start_date is after end_date",
                remediation="Choose a chronological date range.",
            )
        )

    if request.target_horizon_days is None:
        issues.append(_missing("target_horizon_days", "a concrete forward-return horizon is required"))
    elif not 1 <= request.target_horizon_days <= MAX_TIME_WINDOW:
        issues.append(
            ContractIssue(
                code="contract.invalid_target_horizon",
                field="target_horizon_days",
                message=f"target horizon must be between 1 and {MAX_TIME_WINDOW} trading days",
                remediation="Select a supported daily forward-return horizon.",
            )
        )
    if not request.baseline:
        issues.append(_missing("baseline", "an explicit comparison baseline is required"))
    if not request.allowed_fields:
        issues.append(_missing("allowed_fields", "at least one candidate input field is required"))
    if known_fields is not None:
        unknown = _unknown_values(request.allowed_fields, set(known_fields))
        if unknown:
            issues.append(
                ContractIssue(
                    code="contract.unknown_fields",
                    field="allowed_fields",
                    message=f"unknown input fields: {unknown}",
                    remediation="Remove the fields or provide a registered field catalog entry.",
                )
            )
    forbidden = sorted(field for field in set(request.allowed_fields) if is_forbidden_field(field))
    if forbidden:
        issues.append(
            ContractIssue(
                code="contract.future_label_input",
                field="allowed_fields",
                message=f"future-return or label fields cannot be factor inputs: {forbidden}",
                remediation="Keep target returns separate from candidate input fields.",
            )
        )
    if not request.allowed_operators:
        issues.append(_missing("allowed_operators", "at least one registered factor operator is required"))
    unknown_operators = _unknown_values(request.allowed_operators, SUPPORTED_OPERATORS)
    if unknown_operators:
        issues.append(
            ContractIssue(
                code="contract.unknown_operators",
                field="allowed_operators",
                message=f"unknown operators: {unknown_operators}",
                remediation="Use only registered deterministic factor operators.",
            )
        )
    if request.frequency not in SUPPORTED_FREQUENCIES:
        issues.append(
            ContractIssue(
                code="contract.unsupported_frequency",
                field="frequency",
                message=f"frequency {request.frequency!r} is unsupported; only daily data is available",
                remediation="Reframe the request using daily observations.",
            )
        )
    if request.data_mode is None:
        issues.append(_missing("data_mode", "data mode must be real, synthetic, or unavailable"))
    elif request.data_mode not in SUPPORTED_DATA_MODES:
        issues.append(
            ContractIssue(
                code="contract.invalid_data_mode",
                field="data_mode",
                message=f"unsupported data mode: {request.data_mode}",
                remediation="Choose real, synthetic, or unavailable.",
            )
        )
    if not request.success_criteria:
        issues.append(_missing("success_criteria", "success and failure criteria must be explicit"))
    invalid_states = sorted(set(request.final_states) - TERMINAL_STATES)
    if invalid_states or set(request.final_states) != TERMINAL_STATES:
        issues.append(
            ContractIssue(
                code="contract.invalid_final_states",
                field="final_states",
                message="final states must allow positive, negative, and insufficient-evidence outcomes",
                remediation="Include all three permitted research conclusions.",
            )
        )
    if request.oos_split not in SUPPORTED_OOS_SPLITS:
        issues.append(
            ContractIssue(
                code="contract.invalid_oos_split",
                field="oos_split",
                message="out-of-sample splitting must be chronological",
                remediation="Use a date-ordered holdout or walk-forward split.",
            )
        )
    for field, value, lower, upper in (
        ("candidate_count", request.candidate_count, 1, 100),
        ("rounds", request.rounds, 1, 10),
        ("quantiles", request.quantiles, 2, 20),
    ):
        if not lower <= value <= upper:
            issues.append(
                ContractIssue(
                    code="contract.parameter_out_of_range",
                    field=field,
                    message=f"{field} must be between {lower} and {upper}",
                    remediation="Choose a value inside the deterministic execution limit.",
                )
            )
    if request.hold_period_days is None:
        issues.append(_missing("hold_period_days", "a concrete holding period is required"))
    elif not 1 <= request.hold_period_days <= MAX_TIME_WINDOW:
        issues.append(
            ContractIssue(
                code="contract.parameter_out_of_range",
                field="hold_period_days",
                message=f"hold_period_days must be between 1 and {MAX_TIME_WINDOW}",
                remediation="Choose a supported daily holding period.",
            )
        )
    if not 0 <= request.cost_bps <= 1000:
        issues.append(
            ContractIssue(
                code="contract.parameter_out_of_range",
                field="cost_bps",
                message="cost_bps must be between 0 and 1000",
                remediation="Use a non-negative, bounded trading-cost assumption.",
            )
        )
    if request.confirmed and not request.has_valid_confirmation:
        issues.append(
            ContractIssue(
                code="contract.stale_confirmation",
                field="request_id",
                message="confirmed identity does not match the current contract contents",
                remediation="Create and confirm a new contract version after changing any parameter.",
            )
        )
    return ContractReview(request=request, issues=tuple(issues))


def confirm_request(
    request: ResearchRequest,
    *,
    known_fields: Iterable[str] | None = None,
    known_universes: Iterable[str] | None = None,
) -> ResearchRequest:
    if request.confirmed:
        review = review_request(request, known_fields=known_fields, known_universes=known_universes)
        if not review.can_confirm:
            raise ContractValidationError(review)
        return request
    review = review_request(request, known_fields=known_fields, known_universes=known_universes)
    if not review.can_confirm:
        raise ContractValidationError(review)
    return replace(
        request,
        confirmed=True,
        request_id=request.expected_request_id,
        version=request.expected_version,
    )
