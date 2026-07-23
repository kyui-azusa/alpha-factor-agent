from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import hashlib
import hmac
import json
from pathlib import Path
import secrets
from types import MappingProxyType
from typing import Any, Mapping
from uuid import uuid4

import pandas as pd

from src.factors.engine import MAX_TIME_WINDOW
from src.research.contract import ResearchRequest
from src.utils.field_availability import FIELD_AVAILABILITY_ATTR, validate_field_availability


PREFLIGHT_RULE_VERSION = "2026.07.23.1"
RULE_STATUSES = {"passed", "needs_modification", "external_assumption", "unverified", "blocked"}
_PERMIT_SIGNING_KEY = secrets.token_bytes(32)


@dataclass(frozen=True)
class CapabilityEvidence:
    data_mode: str
    available_start_date: str
    available_end_date: str
    available_fields: frozenset[str]
    forward_return_fields: frozenset[str]
    supported_universes: frozenset[str]
    field_availability: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    historical_universe_verified: bool | None = None
    adjustment_verified: bool | None = None
    coverage_verified: bool | None = None
    freshness_verified: bool | None = None
    external_assumptions: tuple[str, ...] = ()
    evidence_sources: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        metadata = {name: MappingProxyType(dict(value)) for name, value in self.field_availability.items()}
        object.__setattr__(self, "field_availability", MappingProxyType(metadata))
        object.__setattr__(self, "evidence_sources", MappingProxyType(dict(self.evidence_sources)))

    def source(self, key: str, fallback: str) -> str:
        return self.evidence_sources.get(key, fallback)


@dataclass(frozen=True)
class RuleResult:
    rule_id: str
    status: str
    title: str
    evidence_source: str
    impact: str
    remediation: str
    blocking: bool = False

    def __post_init__(self) -> None:
        if self.status not in RULE_STATUSES:
            raise ValueError(f"unknown preflight rule status: {self.status}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreflightReport:
    report_id: str
    rule_version: str
    request_id: str
    request_version: str
    request_fingerprint: str
    rules: tuple[RuleResult, ...]
    evidence_label: str
    market_evidence_allowed: bool
    run_id: str | None = None

    @property
    def blocker_count(self) -> int:
        return sum(rule.blocking for rule in self.rules)

    @property
    def allows_generation(self) -> bool:
        return self.blocker_count == 0

    def is_current_for(self, request: ResearchRequest) -> bool:
        return (
            request.confirmed
            and request.request_id == self.request_id
            and request.version == self.request_version
            and request.fingerprint() == self.request_fingerprint
            and self.rule_version == PREFLIGHT_RULE_VERSION
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "rule_version": self.rule_version,
            "request_id": self.request_id,
            "request_version": self.request_version,
            "request_fingerprint": self.request_fingerprint,
            "run_id": self.run_id,
            "blocker_count": self.blocker_count,
            "allows_generation": self.allows_generation,
            "evidence_label": self.evidence_label,
            "market_evidence_allowed": self.market_evidence_allowed,
            "rules": [rule.to_dict() for rule in self.rules],
        }


@dataclass(frozen=True)
class ExecutionPermit:
    run_id: str
    request_id: str
    request_version: str
    request_fingerprint: str
    preflight_report_id: str
    preflight_rule_version: str
    allowed_fields: tuple[str, ...]
    allowed_operators: tuple[str, ...]
    candidate_count: int
    rounds: int
    integrity_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PreflightError(RuntimeError):
    pass


def _permit_payload(permit: ExecutionPermit) -> dict[str, Any]:
    payload = permit.to_dict()
    payload.pop("integrity_digest")
    return payload


def _sign_permit_payload(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hmac.new(_PERMIT_SIGNING_KEY, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def validate_execution_permit(permit: ExecutionPermit | None) -> ExecutionPermit:
    if not isinstance(permit, ExecutionPermit):
        raise PermissionError("agent generation requires an ExecutionPermit from a passing preflight")
    expected = _sign_permit_payload(_permit_payload(permit))
    if not hmac.compare_digest(permit.integrity_digest, expected):
        raise PermissionError("execution permit integrity validation failed")
    return permit


def _rule(
    rule_id: str,
    status: str,
    title: str,
    evidence_source: str,
    impact: str,
    remediation: str,
    *,
    blocking: bool = False,
) -> RuleResult:
    return RuleResult(rule_id, status, title, evidence_source, impact, remediation, blocking)


def _boolean_evidence_rule(
    rule_id: str,
    title: str,
    value: bool | None,
    source: str,
    failure_impact: str,
    remediation: str,
) -> RuleResult:
    if value is True:
        return _rule(rule_id, "passed", title, source, "Required evidence is present.", "None.")
    if value is False:
        return _rule(rule_id, "blocked", title, source, failure_impact, remediation, blocking=True)
    return _rule(
        rule_id,
        "unverified",
        title,
        source,
        failure_impact,
        remediation,
        blocking=True,
    )


def _date_in_range(request_value: str, available_value: str) -> date:
    return date.fromisoformat(request_value or available_value)


def _pit_rule(request: ResearchRequest, evidence: CapabilityEvidence) -> RuleResult:
    fields = set(request.allowed_fields)
    panel = pd.DataFrame(columns=sorted(fields))
    panel.attrs[FIELD_AVAILABILITY_ATTR] = {
        key: dict(value) for key, value in evidence.field_availability.items()
    }
    ok, reason = validate_field_availability(fields, panel)
    if ok:
        return _rule(
            "PF-006",
            "passed",
            "Input field point-in-time evidence",
            evidence.source("field_availability", "panel.field_availability"),
            "All requested fields have usable availability rules.",
            "None.",
        )
    return _rule(
        "PF-006",
        "blocked",
        "Input field point-in-time evidence",
        evidence.source("field_availability", "panel.field_availability"),
        reason,
        "Rebuild the panel through the PIT-safe loader or register valid field availability metadata.",
        blocking=True,
    )


def run_preflight(request: ResearchRequest, evidence: CapabilityEvidence) -> PreflightReport:
    if not request.confirmed or not request.request_id or not request.version:
        raise PreflightError("only a confirmed research request can enter preflight")
    if not request.has_valid_confirmation:
        raise PreflightError("confirmed request identity is stale or inconsistent with its contents")

    rules: list[RuleResult] = []
    if request.data_mode == "unavailable":
        rules.append(
            _rule(
                "PF-001",
                "blocked",
                "Data mode compatibility",
                evidence.source("data_mode", "runtime data manifest"),
                "The contract explicitly declares data unavailable.",
                "Choose a supported real or synthetic data mode and reconfirm the request.",
                blocking=True,
            )
        )
    elif request.data_mode != evidence.data_mode:
        rules.append(
            _rule(
                "PF-001",
                "blocked",
                "Data mode compatibility",
                evidence.source("data_mode", "runtime data manifest"),
                f"Requested {request.data_mode} data but runtime evidence is {evidence.data_mode}.",
                "Select the available mode or connect the required data source, then reconfirm.",
                blocking=True,
            )
        )
    else:
        rules.append(
            _rule(
                "PF-001",
                "passed",
                "Data mode compatibility",
                evidence.source("data_mode", "runtime data manifest"),
                f"Runtime data mode matches the confirmed {request.data_mode} contract.",
                "None.",
            )
        )

    requested_start = _date_in_range(request.start_date or "", evidence.available_start_date)
    requested_end = _date_in_range(request.end_date or "", evidence.available_end_date)
    available_start = date.fromisoformat(evidence.available_start_date)
    available_end = date.fromisoformat(evidence.available_end_date)
    if requested_start < available_start or requested_end > available_end:
        rules.append(
            _rule(
                "PF-002",
                "needs_modification",
                "Date range coverage",
                evidence.source("date_range", "runtime data manifest"),
                f"Requested range is outside {available_start} to {available_end}.",
                "Narrow the date range or load the missing history, then reconfirm.",
                blocking=True,
            )
        )
    else:
        rules.append(
            _rule(
                "PF-002",
                "passed",
                "Date range coverage",
                evidence.source("date_range", "runtime data manifest"),
                "Requested dates are covered.",
                "None.",
            )
        )

    if request.universe not in evidence.supported_universes:
        rules.append(
            _rule(
                "PF-003",
                "blocked",
                "Universe availability",
                evidence.source("universe", "historical universe manifest"),
                f"Universe {request.universe!r} is not available.",
                "Choose a supported universe with historical membership data.",
                blocking=True,
            )
        )
    else:
        rules.append(
            _rule(
                "PF-003",
                "passed",
                "Universe availability",
                evidence.source("universe", "historical universe manifest"),
                "The requested universe is registered.",
                "None.",
            )
        )

    target_field = request.target_return_field
    if target_field not in evidence.forward_return_fields:
        rules.append(
            _rule(
                "PF-004",
                "needs_modification",
                "Target return availability",
                evidence.source("forward_returns", "forward-return manifest"),
                f"Target column {target_field!r} is unavailable.",
                "Choose a generated forward-return horizon or create it deterministically.",
                blocking=True,
            )
        )
    else:
        rules.append(
            _rule(
                "PF-004",
                "passed",
                "Target return availability",
                evidence.source("forward_returns", "forward-return manifest"),
                f"Target column {target_field} is available and remains label-only.",
                "None.",
            )
        )

    missing_fields = sorted(set(request.allowed_fields) - set(evidence.available_fields))
    if missing_fields:
        rules.append(
            _rule(
                "PF-005",
                "blocked",
                "Input field availability",
                evidence.source("fields", "registered field catalog"),
                f"Requested input fields are missing: {missing_fields}.",
                "Remove unavailable fields or register and load them with provenance.",
                blocking=True,
            )
        )
    else:
        rules.append(
            _rule(
                "PF-005",
                "passed",
                "Input field availability",
                evidence.source("fields", "registered field catalog"),
                "All requested input fields are registered.",
                "None.",
            )
        )
    rules.append(_pit_rule(request, evidence))

    hard_constraints = (
        ("PF-007", request.pit_enabled, "PIT protection is mandatory", "Enable PIT protection."),
        (
            "PF-008",
            request.oos_split in {"date_ordered_train_end_exclusive", "walk_forward"},
            "Out-of-sample splitting must remain chronological",
            "Use a date-ordered holdout or walk-forward split.",
        ),
        (
            "PF-009",
            not request.backtest_llm_enabled,
            "Backtests must not call an LLM",
            "Disable LLM access in the backtest path.",
        ),
        (
            "PF-010",
            not request.oos_feedback_enabled,
            "OOS outcomes must not feed candidate generation",
            "Restrict feedback to the development segment.",
        ),
    )
    for rule_id, passed, title, remediation in hard_constraints:
        rules.append(
            _rule(
                rule_id,
                "passed" if passed else "blocked",
                title,
                "confirmed ResearchRequest",
                "Hard constraint remains enforced." if passed else "A non-disableable trust boundary was changed.",
                "None." if passed else remediation,
                blocking=not passed,
            )
        )

    execution_parameters_valid = (
        1 <= request.candidate_count <= 100
        and 1 <= request.rounds <= 10
        and request.hold_period_days is not None
        and 1 <= request.hold_period_days <= MAX_TIME_WINDOW
        and 2 <= request.quantiles <= 20
        and 0 <= request.cost_bps <= 1000
        and request.frequency == "D"
    )
    rules.append(
        _rule(
            "PF-015",
            "passed" if execution_parameters_valid else "blocked",
            "Execution parameter limits",
            "confirmed ResearchRequest and deterministic engine limits",
            (
                "Candidate count, rounds, holding period, quantiles, cost, and frequency are supported."
                if execution_parameters_valid
                else "At least one execution parameter is outside deterministic engine limits."
            ),
            "None." if execution_parameters_valid else "Adjust the unsupported parameter and reconfirm the request.",
            blocking=not execution_parameters_valid,
        )
    )

    rules.extend(
        (
            _boolean_evidence_rule(
                "PF-011",
                "Historical universe evidence",
                evidence.historical_universe_verified,
                evidence.source("historical_universe", "historical universe audit"),
                "Survivorship-bias protection is not proven.",
                "Provide a dated membership audit for the requested range.",
            ),
            _boolean_evidence_rule(
                "PF-012",
                "Price adjustment evidence",
                evidence.adjustment_verified,
                evidence.source("adjustment", "corporate-action audit"),
                "Return construction may be inconsistent across corporate actions.",
                "Run and attach the adjustment-quality audit.",
            ),
            _boolean_evidence_rule(
                "PF-013",
                "Coverage evidence",
                evidence.coverage_verified,
                evidence.source("coverage", "field coverage audit"),
                "The usable sample may not meet the research contract.",
                "Run the field and event coverage audit for the requested range.",
            ),
            _boolean_evidence_rule(
                "PF-014",
                "Freshness evidence",
                evidence.freshness_verified,
                evidence.source("freshness", "field freshness audit"),
                "Stale observations may be treated as current information.",
                "Run the field freshness audit and define expiry rules.",
            ),
        )
    )
    for index, assumption in enumerate(evidence.external_assumptions, start=1):
        rules.append(
            _rule(
                f"PF-EXT-{index:02d}",
                "external_assumption",
                "External data assumption",
                evidence.source("external_assumptions", "supplier/extraction documentation"),
                assumption,
                "Keep the assumption visible in every downstream report.",
            )
        )

    fingerprint = request.fingerprint()
    serialized = json.dumps(
        {
            "request_id": request.request_id,
            "request_version": request.version,
            "request_fingerprint": fingerprint,
            "rule_version": PREFLIGHT_RULE_VERSION,
            "rules": [rule.to_dict() for rule in rules],
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    report_id = f"preflight_{hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]}"
    synthetic = evidence.data_mode == "synthetic"
    return PreflightReport(
        report_id=report_id,
        rule_version=PREFLIGHT_RULE_VERSION,
        request_id=request.request_id,
        request_version=request.version,
        request_fingerprint=fingerprint,
        rules=tuple(rules),
        evidence_label=(
            "synthetic engineering validation; not real-market evidence"
            if synthetic
            else "real-data capability preflight; not a research finding"
        ),
        market_evidence_allowed=evidence.data_mode == "real",
    )


def create_execution_permit(
    request: ResearchRequest,
    report: PreflightReport,
    *,
    run_id: str | None = None,
) -> ExecutionPermit:
    if not report.is_current_for(request):
        raise PreflightError("preflight report is stale or belongs to a different contract version")
    if not report.allows_generation:
        raise PreflightError(f"preflight has {report.blocker_count} blocking rules")
    payload = {
        "run_id": run_id or f"run_{uuid4().hex}",
        "request_id": report.request_id,
        "request_version": report.request_version,
        "request_fingerprint": report.request_fingerprint,
        "preflight_report_id": report.report_id,
        "preflight_rule_version": report.rule_version,
        "allowed_fields": request.allowed_fields,
        "allowed_operators": request.allowed_operators,
        "candidate_count": request.candidate_count,
        "rounds": request.rounds,
    }
    return ExecutionPermit(**payload, integrity_digest=_sign_permit_payload(payload))


def save_preflight_report(
    report: PreflightReport,
    destination: str | Path,
    *,
    permit: ExecutionPermit | None = None,
) -> Path:
    if permit is not None:
        validate_execution_permit(permit)
        if permit.preflight_report_id != report.report_id:
            raise PreflightError("execution permit belongs to a different preflight report")
        if permit.request_id != report.request_id or permit.request_version != report.request_version:
            raise PreflightError("execution permit belongs to a different research request")
        if permit.request_fingerprint != report.request_fingerprint:
            raise PreflightError("execution permit contract fingerprint does not match the preflight report")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    payload["run_id"] = permit.run_id if permit is not None else None
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path
