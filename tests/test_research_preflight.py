from dataclasses import replace
import json

import pandas as pd
import pytest

from src.research.contract import ResearchRequest, confirm_request
from src.research.preflight import (
    CapabilityEvidence,
    PreflightError,
    create_execution_permit,
    run_preflight,
    save_preflight_report,
    validate_execution_permit,
)
from src.utils.field_availability import price_field_metadata
from src.utils.fundamental_quality import FieldQualityPolicy, audit_fundamental_quality


def request(**overrides) -> ResearchRequest:
    values = {
        "raw_question": "Does price strength predict forward returns?",
        "hypothesis": "Cross-sectional close rank predicts 20-day returns.",
        "universe": "a_share_all",
        "start_date": "2015-01-01",
        "end_date": "2021-12-31",
        "event_scope": ("daily_close",),
        "field_scope": ("prices",),
        "target_horizon_days": 20,
        "baseline": "market neutral zero-alpha baseline",
        "allowed_fields": ("close",),
        "allowed_operators": ("rank",),
        "candidate_count": 5,
        "rounds": 1,
        "hold_period_days": 20,
        "quantiles": 5,
        "cost_bps": 10.0,
        "success_criteria": ("OOS rank IC reported with uncertainty",),
        "data_mode": "real",
    }
    values.update(overrides)
    return ResearchRequest(**values)


def evidence(**overrides) -> CapabilityEvidence:
    values = {
        "data_mode": "real",
        "available_start_date": "2015-01-01",
        "available_end_date": "2021-12-31",
        "available_fields": frozenset({"close", "amount"}),
        "forward_return_fields": frozenset({"fwd_ret_5", "fwd_ret_20"}),
        "supported_universes": frozenset({"a_share_all"}),
        "field_availability": {"close": price_field_metadata("close")},
        "historical_universe_verified": True,
        "adjustment_verified": True,
        "coverage_verified": True,
        "freshness_verified": True,
        "external_assumptions": ("Supplier announcement dates are accurate.",),
        "evidence_sources": {"field_availability": "panel attrs from PIT-safe loader"},
    }
    values.update(overrides)
    return CapabilityEvidence(**values)


def confirmed_request(**overrides) -> ResearchRequest:
    draft = request(**overrides)
    return confirm_request(draft, known_fields={"close", "amount"})


def test_unconfirmed_request_cannot_preflight_or_generate():
    draft = request()

    with pytest.raises(PreflightError, match="confirmed"):
        run_preflight(draft, evidence())


def test_passing_preflight_records_rules_evidence_and_execution_link():
    confirmed = confirmed_request()
    report = run_preflight(confirmed, evidence())

    assert report.allows_generation
    assert report.blocker_count == 0
    assert report.rule_version
    assert all(rule.rule_id and rule.evidence_source and rule.impact and rule.remediation for rule in report.rules)
    assert {rule.status for rule in report.rules} >= {"passed", "external_assumption"}

    permit = create_execution_permit(confirmed, report, run_id="run_test_001")
    assert permit.run_id == "run_test_001"
    assert permit.request_id == confirmed.request_id
    assert permit.request_fingerprint == confirmed.fingerprint()
    assert permit.preflight_report_id == report.report_id
    assert permit.allowed_fields == confirmed.allowed_fields
    assert permit.integrity_digest
    assert validate_execution_permit(permit) is permit


def test_tampered_or_manually_constructed_execution_permit_is_rejected():
    confirmed = confirmed_request()
    report = run_preflight(confirmed, evidence())
    permit = create_execution_permit(confirmed, report, run_id="run_integrity_001")

    tampered = replace(permit, candidate_count=permit.candidate_count + 1)
    forged = replace(permit, integrity_digest="0" * 64)

    with pytest.raises(PermissionError, match="integrity"):
        validate_execution_permit(tampered)
    with pytest.raises(PermissionError, match="integrity"):
        validate_execution_permit(forged)


def test_preflight_report_can_be_saved_with_request_rule_and_run_links(tmp_path):
    confirmed = confirmed_request()
    report = run_preflight(confirmed, evidence())
    permit = create_execution_permit(confirmed, report, run_id="run_saved_001")

    path = save_preflight_report(report, tmp_path / "preflight.json", permit=permit)
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["request_id"] == confirmed.request_id
    assert payload["request_version"] == confirmed.version
    assert payload["rule_version"] == report.rule_version
    assert payload["run_id"] == permit.run_id
    assert payload["allows_generation"] is True


@pytest.mark.parametrize(
    ("request_overrides", "expected_rule"),
    [
        ({"pit_enabled": False}, "PF-007"),
        ({"oos_split": "random_shuffle"}, "PF-008"),
        ({"backtest_llm_enabled": True}, "PF-009"),
        ({"oos_feedback_enabled": True}, "PF-010"),
    ],
)
def test_hard_constraints_cannot_be_disabled(request_overrides, expected_rule):
    draft = request(**request_overrides)
    # These unsafe toggles are intentionally allowed to reach preflight so the
    # execution boundary independently fails closed.
    confirmed = replace(
        draft,
        confirmed=True,
        request_id=draft.expected_request_id,
        version=draft.expected_version,
    )

    report = run_preflight(confirmed, evidence())

    result = next(rule for rule in report.rules if rule.rule_id == expected_rule)
    assert result.status == "blocked"
    assert result.blocking
    assert not report.allows_generation
    with pytest.raises(PreflightError, match="blocking"):
        create_execution_permit(confirmed, report)


def test_missing_field_and_pit_proof_block_generation():
    confirmed = confirmed_request(allowed_fields=("amount",))
    missing_field = run_preflight(
        confirmed,
        evidence(available_fields=frozenset({"close"}), field_availability={"close": price_field_metadata("close")}),
    )
    missing_pit = run_preflight(
        confirmed,
        evidence(field_availability={"close": price_field_metadata("close")}),
    )

    assert not missing_field.allows_generation
    assert next(rule for rule in missing_field.rules if rule.rule_id == "PF-005").blocking
    assert not missing_pit.allows_generation
    assert next(rule for rule in missing_pit.rules if rule.rule_id == "PF-006").blocking


def test_missing_capability_audit_is_unverified_and_blocking():
    confirmed = confirmed_request()
    report = run_preflight(confirmed, evidence(coverage_verified=None))

    coverage = next(rule for rule in report.rules if rule.rule_id == "PF-013")
    assert coverage.status == "unverified"
    assert coverage.blocking
    assert not report.allows_generation


def test_fundamental_quality_audit_drives_coverage_and_freshness_rules():
    observations = pd.DataFrame(
        {
            "date": pd.to_datetime(["2022-01-10", "2022-01-10"]),
            "code": ["STALE", "MISSING"],
        }
    )
    fundamentals = pd.DataFrame(
        {
            "code": ["STALE"],
            "report_period": pd.to_datetime(["2019-09-30"]),
            "ann_date": pd.to_datetime(["2020-01-01"]),
            "ann_time": pd.to_datetime(["2020-01-01 18:00:00"]),
            "net_income": [10.0],
        }
    )
    audit = audit_fundamental_quality(
        observations,
        fundamentals,
        {
            "net_income": FieldQualityPolicy(
                max_age_days=365,
                min_coverage_ratio=0.8,
                max_stale_ratio=0.0,
            )
        },
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )

    report = run_preflight(confirmed_request(), evidence(**audit.preflight_evidence()))
    coverage = next(rule for rule in report.rules if rule.rule_id == "PF-013")
    freshness = next(rule for rule in report.rules if rule.rule_id == "PF-014")

    assert coverage.status == "blocked"
    assert freshness.status == "blocked"
    assert audit.audit_id in coverage.evidence_source
    assert audit.audit_id in freshness.evidence_source
    assert not report.allows_generation


def test_contract_change_invalidates_old_preflight():
    original = confirmed_request()
    report = run_preflight(original, evidence())
    changed = confirmed_request(target_horizon_days=5, hold_period_days=5)

    assert not report.is_current_for(changed)
    with pytest.raises(PreflightError, match="stale"):
        create_execution_permit(changed, report)


def test_modified_confirmed_request_cannot_bypass_confirmation():
    original = confirmed_request()
    modified = replace(original, candidate_count=1000)

    with pytest.raises(PreflightError, match="stale"):
        run_preflight(modified, evidence())


def test_synthetic_mode_is_never_described_as_market_evidence():
    confirmed = confirmed_request(data_mode="synthetic")
    report = run_preflight(confirmed, evidence(data_mode="synthetic"))

    assert report.allows_generation
    assert not report.market_evidence_allowed
    assert "synthetic engineering validation" in report.evidence_label
    assert "real-market evidence" in report.evidence_label
