import json

import pandas as pd
import pytest

from src.utils.fundamental_quality import (
    FieldQualityPolicy,
    audit_fundamental_quality,
    save_fundamental_quality_audit,
)


def _observations() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": pd.to_datetime(["2022-01-10"] * 5),
            "code": ["STALE", "VALID", "NEVER", "FUTURE", "EXCLUDED"],
            "industry": ["bank", "tech", "tech", "bank", "bank"],
            "business_excluded": [False, False, False, False, True],
            "business_exclusion_reason": [None, None, None, None, "financial_sector_policy"],
        }
    )


def _fundamentals() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code": ["STALE", "VALID", "FUTURE", "EXCLUDED"],
            "report_period": pd.to_datetime(["2019-09-30", "2021-09-30", "2021-12-31", "2021-09-30"]),
            "ann_date": pd.to_datetime(["2020-01-01", "2022-01-07", "2022-01-11", "2022-01-07"]),
            "ann_time": pd.to_datetime(
                ["2020-01-01 18:00:00", "2022-01-07 18:00:00", None, "2022-01-07 18:00:00"]
            ),
            "net_income": [10.0, 20.0, 30.0, 40.0],
            "revenue": [100.0, 200.0, 300.0, 400.0],
        }
    )


def test_audit_distinguishes_all_exclusion_reasons_and_stale_values():
    audit = audit_fundamental_quality(
        _observations(),
        _fundamentals(),
        {"net_income": FieldQualityPolicy(max_age_days=365, min_coverage_ratio=0.5)},
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )
    rows = audit.rows.set_index("code")

    assert rows.loc["STALE", "status"] == "stale"
    assert rows.loc["STALE", "lag_days"] > 700
    assert rows.loc["STALE", "last_ann_date"] == pd.Timestamp("2020-01-01")
    assert rows.loc["STALE", "last_report_period"] == pd.Timestamp("2019-09-30")
    assert rows.loc["VALID", "status"] == "valid"
    assert rows.loc["NEVER", "status"] == "never_available"
    assert rows.loc["FUTURE", "status"] == "not_yet_announced"
    assert rows.loc["EXCLUDED", "status"] == "business_excluded"
    assert rows.loc["EXCLUDED", "exclusion_reason"] == "financial_sector_policy"
    assert set(audit.rows["status"]) == {
        "valid",
        "stale",
        "never_available",
        "not_yet_announced",
        "business_excluded",
    }


def test_audit_summarizes_field_date_and_industry_coverage():
    audit = audit_fundamental_quality(
        _observations(),
        _fundamentals(),
        {"net_income": FieldQualityPolicy(max_age_days=365, min_coverage_ratio=0.5)},
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )
    summary = audit.field_summary.set_index("field").loc["net_income"]

    assert summary["eligible_count"] == 4
    assert summary["valid_count"] == 1
    assert summary["stale_count"] == 1
    assert summary["never_available_count"] == 1
    assert summary["not_yet_announced_count"] == 1
    assert summary["business_excluded_count"] == 1
    assert summary["coverage_ratio"] == 0.5
    assert summary["usable_coverage_ratio"] == 0.25
    assert summary["missing_ratio"] == 0.5
    assert summary["stale_ratio"] == 0.25
    assert summary["last_available_at"] == pd.Timestamp("2022-01-07 18:00:00")
    assert summary["max_lag_days"] > 700
    assert len(audit.date_summary) == 1
    assert set(audit.industry_summary["industry"]) == {"bank", "tech"}


def test_low_usable_coverage_and_stale_ratio_fail_preflight_evidence():
    audit = audit_fundamental_quality(
        _observations(),
        _fundamentals(),
        {
            "net_income": FieldQualityPolicy(
                max_age_days=365,
                min_coverage_ratio=0.8,
                max_stale_ratio=0.0,
                stale_action="unverified",
            )
        },
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )
    evidence = audit.preflight_evidence("test audit")

    assert not audit.verified
    assert evidence["coverage_verified"] is False
    assert evidence["freshness_verified"] is False
    assert evidence["evidence_sources"]["coverage"].endswith(audit.audit_id)


def test_excluded_stale_values_still_reduce_usable_coverage():
    observations = _observations().iloc[[0, 1]].copy()
    audit = audit_fundamental_quality(
        observations,
        _fundamentals(),
        {
            "net_income": FieldQualityPolicy(
                max_age_days=365,
                min_coverage_ratio=0.75,
                max_stale_ratio=0.0,
                stale_action="exclude",
            )
        },
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )

    assert audit.freshness_verified
    assert not audit.coverage_verified
    assert not audit.verified


def test_audit_supports_field_specific_expiry_policies():
    audit = audit_fundamental_quality(
        _observations().iloc[[0]].copy(),
        _fundamentals(),
        {
            "net_income": FieldQualityPolicy(max_age_days=365),
            "revenue": FieldQualityPolicy(max_age_days=1000),
        },
        signal_time="15:00:00",
        availability_time_col="ann_time",
    )
    statuses = audit.rows.set_index("field")["status"]

    assert statuses["net_income"] == "stale"
    assert statuses["revenue"] == "valid"


def test_business_exclusion_requires_a_reason():
    observations = _observations().iloc[[-1]].copy()
    observations["business_exclusion_reason"] = None

    with pytest.raises(ValueError, match="business_exclusion_reason"):
        audit_fundamental_quality(
            observations,
            _fundamentals(),
            {"net_income": FieldQualityPolicy(max_age_days=365)},
            signal_time="15:00:00",
            availability_time_col="ann_time",
        )


def test_audit_is_stable_and_can_be_saved(tmp_path):
    kwargs = {
        "observations": _observations(),
        "fundamentals": _fundamentals(),
        "policies": {"net_income": FieldQualityPolicy(max_age_days=365)},
        "signal_time": "15:00:00",
        "availability_time_col": "ann_time",
    }
    first = audit_fundamental_quality(**kwargs)
    second = audit_fundamental_quality(**kwargs)

    assert first.audit_id == second.audit_id
    manifest_path = save_fundamental_quality_audit(first, tmp_path / "audit")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["audit_id"] == first.audit_id
    assert (manifest_path.parent / "records.csv").exists()
    assert (manifest_path.parent / "fields.csv").exists()
    assert (manifest_path.parent / "dates.csv").exists()
    assert (manifest_path.parent / "industries.csv").exists()
