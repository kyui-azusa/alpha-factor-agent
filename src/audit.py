"""Deterministic audit primitives for factor evidence and candidate filtering.

This module is intentionally independent from backtest execution and report
generation. It records how deterministic code judged evidence and candidate
funnels without changing any numerical backtest result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence


class EvidenceStatus(str, Enum):
    """ASCII evidence status values used in serialized audit payloads."""

    VERIFIED = "verified"
    ADJUSTABLE = "adjustable"
    FIXED_THIS_RUN = "fixed_this_run"
    EXTERNAL_ASSUMPTION = "external_assumption"
    UNTESTED = "untested"


_PASSING_STATUSES = {
    EvidenceStatus.VERIFIED,
    EvidenceStatus.ADJUSTABLE,
    EvidenceStatus.FIXED_THIS_RUN,
    EvidenceStatus.EXTERNAL_ASSUMPTION,
}


def _status(value: EvidenceStatus | str) -> EvidenceStatus:
    if isinstance(value, EvidenceStatus):
        return value
    return EvidenceStatus(str(value))


def _stable_unique(values: Iterable[str]) -> list[str]:
    return sorted({str(value) for value in values})


@dataclass(frozen=True)
class EvidenceState:
    """A serializable evidence decision with fail-closed pass semantics."""

    status: EvidenceStatus | str
    evidence: Sequence[str] = field(default_factory=tuple)
    reason_code: str = ""
    message: str = ""

    @property
    def is_passed(self) -> bool:
        status = _status(self.status)
        return bool(self.evidence) and status in _PASSING_STATUSES

    def to_dict(self) -> dict[str, Any]:
        status = _status(self.status)
        return {
            "status": status.value,
            "is_passed": self.is_passed,
            "reason_code": self.reason_code,
            "message": self.message,
            "evidence": _stable_unique(self.evidence),
        }


@dataclass(frozen=True)
class ExclusionAuditRecord:
    """Stable record for a deterministic include/exclude decision."""

    decision: str
    reason_code: str
    message: str
    rule_version: str
    decided_by: str
    affected_count: int = 0
    adjustable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason_code": self.reason_code,
            "message": self.message,
            "rule_version": self.rule_version,
            "decided_by": self.decided_by,
            "affected_count": int(self.affected_count),
            "adjustable": bool(self.adjustable),
        }


@dataclass(frozen=True)
class CandidateFunnelSummary:
    """Deterministic counts for candidate selection and multiple testing."""

    generated: int = 0
    validated: int = 0
    backtested: int = 0
    promoted: int = 0
    rejected: int = 0
    reason_codes: Sequence[str] = field(default_factory=tuple)

    @property
    def selection_bias_disclosure_required(self) -> bool:
        return self.generated > self.promoted or self.rejected > 0

    @property
    def multiple_testing_disclosure_required(self) -> bool:
        return self.backtested > 1

    def disclosures(self) -> list[str]:
        disclosures: list[str] = []
        if self.selection_bias_disclosure_required:
            disclosures.append("selection_bias")
        if self.multiple_testing_disclosure_required:
            disclosures.append("multiple_testing")
        return disclosures

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated": int(self.generated),
            "validated": int(self.validated),
            "backtested": int(self.backtested),
            "promoted": int(self.promoted),
            "rejected": int(self.rejected),
            "selection_bias_disclosure_required": self.selection_bias_disclosure_required,
            "multiple_testing_disclosure_required": self.multiple_testing_disclosure_required,
            "disclosures": self.disclosures(),
            "reason_codes": _stable_unique(self.reason_codes),
        }


def candidate_funnel_summary(candidates: Iterable[Mapping[str, Any]]) -> CandidateFunnelSummary:
    """Build deterministic funnel counts from candidate audit rows.

    Each row may expose boolean fields named ``generated``, ``validated``,
    ``backtested``, ``promoted``, and ``rejected``. Missing fields are treated as
    false. ``reason_code`` values are collected into a stable sorted list.
    """

    rows = list(candidates)
    return CandidateFunnelSummary(
        generated=sum(1 for row in rows if bool(row.get("generated"))),
        validated=sum(1 for row in rows if bool(row.get("validated"))),
        backtested=sum(1 for row in rows if bool(row.get("backtested"))),
        promoted=sum(1 for row in rows if bool(row.get("promoted"))),
        rejected=sum(1 for row in rows if bool(row.get("rejected"))),
        reason_codes=[str(row["reason_code"]) for row in rows if row.get("reason_code")],
    )
