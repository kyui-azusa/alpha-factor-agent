from dataclasses import replace

import pytest

from src.research.contract import ContractValidationError, ResearchRequest, confirm_request, review_request


KNOWN_FIELDS = {"close", "amount", "forecast_text_score", "fwd_ret_20"}


def complete_request(**overrides) -> ResearchRequest:
    values = {
        "raw_question": "Does forecast text add information over structured guidance?",
        "hypothesis": "Text tone has incremental cross-sectional predictive power.",
        "universe": "a_share_all",
        "start_date": "2015-01-01",
        "end_date": "2021-12-31",
        "event_scope": ("performance_forecast",),
        "field_scope": ("structured_guidance", "forecast_text"),
        "target_horizon_days": 20,
        "baseline": "structured guidance only",
        "allowed_fields": ("close", "forecast_text_score"),
        "allowed_operators": ("rank", "add"),
        "candidate_count": 8,
        "rounds": 2,
        "hold_period_days": 20,
        "quantiles": 5,
        "cost_bps": 10.0,
        "oos_split": "date_ordered_train_end_exclusive",
        "success_criteria": ("incremental OOS rank IC with uncertainty",),
        "data_mode": "real",
    }
    values.update(overrides)
    return ResearchRequest(**values)


def test_missing_horizon_universe_and_data_mode_require_clarification():
    request = complete_request(universe=None, target_horizon_days=None, data_mode=None)

    review = review_request(request, known_fields=KNOWN_FIELDS)

    assert not review.can_confirm
    assert set(review.clarification_fields) >= {"universe", "target_horizon_days", "data_mode"}
    assert review.to_dict()["can_enter_generation"] is False
    with pytest.raises(ContractValidationError):
        confirm_request(request, known_fields=KNOWN_FIELDS)


def test_contract_rejects_conflicting_dates_unknown_fields_and_future_label_inputs():
    request = complete_request(
        start_date="2022-01-01",
        end_date="2021-01-01",
        allowed_fields=("unknown_sentiment", "fwd_ret_20"),
    )

    codes = {issue.code for issue in review_request(request, known_fields=KNOWN_FIELDS).issues}

    assert "contract.conflicting_dates" in codes
    assert "contract.unknown_fields" in codes
    assert "contract.future_label_input" in codes


def test_contract_rejects_any_forward_return_label_pattern():
    request = complete_request(allowed_fields=("close", "fwd_ret_63"))

    review = review_request(request, known_fields=KNOWN_FIELDS | {"fwd_ret_63"})

    issue = next(issue for issue in review.issues if issue.code == "contract.future_label_input")
    assert "fwd_ret_63" in issue.message


def test_contract_rejects_unsupported_minute_frequency():
    review = review_request(complete_request(frequency="1min"), known_fields=KNOWN_FIELDS)

    assert "contract.unsupported_frequency" in {issue.code for issue in review.issues}


def test_identical_confirmed_contract_has_stable_id_and_version():
    first = confirm_request(complete_request(), known_fields=KNOWN_FIELDS)
    second = confirm_request(complete_request(), known_fields=KNOWN_FIELDS)

    assert first.confirmed and second.confirmed
    assert first.request_id == second.request_id
    assert first.version == second.version
    assert first.fingerprint() == second.fingerprint()
    assert first.can_enter_generation is False


def test_changed_contract_gets_new_identity():
    original = confirm_request(complete_request(), known_fields=KNOWN_FIELDS)
    changed = confirm_request(replace(complete_request(), target_horizon_days=5), known_fields=KNOWN_FIELDS)

    assert original.request_id != changed.request_id
    assert original.version != changed.version


def test_modified_confirmed_contract_has_stale_identity():
    confirmed = confirm_request(complete_request(), known_fields=KNOWN_FIELDS)
    modified = replace(confirmed, target_horizon_days=5)

    review = review_request(modified, known_fields=KNOWN_FIELDS)

    assert not modified.has_valid_confirmation
    assert "contract.stale_confirmation" in {issue.code for issue in review.issues}
    with pytest.raises(ContractValidationError):
        confirm_request(modified, known_fields=KNOWN_FIELDS)
