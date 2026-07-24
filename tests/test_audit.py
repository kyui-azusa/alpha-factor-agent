from src.audit import CandidateFunnelSummary
from src.audit import EvidenceState
from src.audit import EvidenceStatus
from src.audit import ExclusionAuditRecord
from src.audit import candidate_funnel_summary


def test_all_evidence_statuses_are_serializable_ascii_values():
    expected = {
        EvidenceStatus.VERIFIED: "verified",
        EvidenceStatus.ADJUSTABLE: "adjustable",
        EvidenceStatus.FIXED_THIS_RUN: "fixed_this_run",
        EvidenceStatus.EXTERNAL_ASSUMPTION: "external_assumption",
        EvidenceStatus.UNTESTED: "untested",
    }

    for status, value in expected.items():
        payload = EvidenceState(status=status, evidence=["source"], reason_code="ok").to_dict()
        assert payload["status"] == value
        assert isinstance(payload["status"], str)
        assert set(payload) == {"status", "is_passed", "reason_code", "message", "evidence"}


def test_missing_evidence_fails_closed_even_for_passing_status():
    payload = EvidenceState(
        status=EvidenceStatus.VERIFIED,
        evidence=[],
        reason_code="missing_input_evidence",
        message="No deterministic evidence was attached.",
    ).to_dict()

    assert payload["is_passed"] is False
    assert payload["reason_code"] == "missing_input_evidence"


def test_untested_status_blocks_even_with_evidence():
    payload = EvidenceState(
        status=EvidenceStatus.UNTESTED,
        evidence=["candidate_spec_present"],
        reason_code="not_evaluated",
    ).to_dict()

    assert payload["is_passed"] is False


def test_evidence_state_sorts_evidence_for_deterministic_serialization():
    left = EvidenceState(
        status="verified",
        evidence=["z_rule", "a_rule", "z_rule"],
        reason_code="stable_evidence",
    ).to_dict()
    right = EvidenceState(
        status=EvidenceStatus.VERIFIED,
        evidence=["a_rule", "z_rule"],
        reason_code="stable_evidence",
    ).to_dict()

    assert left == right
    assert left["evidence"] == ["a_rule", "z_rule"]
    assert left["is_passed"] is True


def test_exclusion_audit_record_has_stable_required_fields():
    record = ExclusionAuditRecord(
        decision="exclude",
        reason_code="lookahead_field",
        message="Candidate used a forbidden future return field.",
        rule_version="audit-v1",
        decided_by="deterministic_validator",
        affected_count=3,
        adjustable=True,
    ).to_dict()

    assert record == {
        "decision": "exclude",
        "reason_code": "lookahead_field",
        "message": "Candidate used a forbidden future return field.",
        "rule_version": "audit-v1",
        "decided_by": "deterministic_validator",
        "affected_count": 3,
        "adjustable": True,
    }


def test_candidate_funnel_summary_flags_selection_bias_and_multiple_testing():
    summary = CandidateFunnelSummary(
        generated=5,
        validated=4,
        backtested=3,
        promoted=1,
        rejected=2,
        reason_codes=["weak_ic", "parse_error", "weak_ic"],
    ).to_dict()

    assert summary["generated"] == 5
    assert summary["validated"] == 4
    assert summary["backtested"] == 3
    assert summary["promoted"] == 1
    assert summary["rejected"] == 2
    assert summary["selection_bias_disclosure_required"] is True
    assert summary["multiple_testing_disclosure_required"] is True
    assert summary["disclosures"] == ["selection_bias", "multiple_testing"]
    assert summary["reason_codes"] == ["parse_error", "weak_ic"]


def test_candidate_funnel_summary_from_records_is_deterministic():
    rows = [
        {
            "generated": True,
            "validated": True,
            "backtested": True,
            "promoted": False,
            "rejected": True,
            "reason_code": "weak_ic",
        },
        {
            "generated": True,
            "validated": False,
            "backtested": False,
            "promoted": False,
            "rejected": True,
            "reason_code": "parse_error",
        },
        {
            "generated": True,
            "validated": True,
            "backtested": True,
            "promoted": True,
            "rejected": False,
            "reason_code": "promoted_oos",
        },
    ]

    forward = candidate_funnel_summary(rows).to_dict()
    reverse = candidate_funnel_summary(reversed(rows)).to_dict()

    assert forward == reverse
    assert forward["generated"] == 3
    assert forward["validated"] == 2
    assert forward["backtested"] == 2
    assert forward["promoted"] == 1
    assert forward["rejected"] == 2
    assert forward["reason_codes"] == ["parse_error", "promoted_oos", "weak_ic"]
