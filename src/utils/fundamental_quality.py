from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.utils.align import resolve_information_availability, resolve_signal_times


FUNDAMENTAL_QUALITY_RULE_VERSION = "2026.07.23.1"
QUALITY_STATUSES = {
    "valid",
    "stale",
    "never_available",
    "not_yet_announced",
    "business_excluded",
}
STALE_ACTIONS = {"block", "exclude", "unverified"}


@dataclass(frozen=True)
class FieldQualityPolicy:
    max_age_days: int
    min_coverage_ratio: float = 0.8
    max_stale_ratio: float = 0.0
    stale_action: str = "block"

    def __post_init__(self) -> None:
        if self.max_age_days < 0:
            raise ValueError("max_age_days must be non-negative")
        if not 0.0 <= self.min_coverage_ratio <= 1.0:
            raise ValueError("min_coverage_ratio must be between 0 and 1")
        if not 0.0 <= self.max_stale_ratio <= 1.0:
            raise ValueError("max_stale_ratio must be between 0 and 1")
        if self.stale_action not in STALE_ACTIONS:
            raise ValueError(f"stale_action must be one of {sorted(STALE_ACTIONS)}")


@dataclass
class FundamentalQualityAudit:
    audit_id: str
    rule_version: str
    rows: pd.DataFrame
    field_summary: pd.DataFrame
    date_summary: pd.DataFrame
    industry_summary: pd.DataFrame
    policies: dict[str, FieldQualityPolicy]
    coverage_verified: bool
    freshness_verified: bool

    @property
    def verified(self) -> bool:
        return self.coverage_verified and self.freshness_verified

    def preflight_evidence(self, source: str = "fundamental quality audit") -> dict[str, Any]:
        return {
            "coverage_verified": self.coverage_verified,
            "freshness_verified": self.freshness_verified,
            "evidence_sources": {
                "coverage": f"{source}:{self.audit_id}",
                "freshness": f"{source}:{self.audit_id}",
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "rule_version": self.rule_version,
            "verified": self.verified,
            "coverage_verified": self.coverage_verified,
            "freshness_verified": self.freshness_verified,
            "policies": {field: asdict(policy) for field, policy in self.policies.items()},
            "field_summary": _records(self.field_summary),
            "date_summary": _records(self.date_summary),
            "industry_summary": _records(self.industry_summary),
        }


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    normalized = frame.copy()
    for column in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column]):
            normalized[column] = normalized[column].map(lambda value: value.isoformat() if pd.notna(value) else None)
    return normalized.where(pd.notna(normalized), None).to_dict(orient="records")


def _validate_inputs(
    observations: pd.DataFrame,
    fundamentals: pd.DataFrame,
    policies: Mapping[str, FieldQualityPolicy],
) -> None:
    missing_observations = {"date", "code"} - set(observations.columns)
    if missing_observations:
        raise ValueError(f"observations missing columns: {sorted(missing_observations)}")
    missing_fundamentals = {"code", "ann_date", "report_period"} - set(fundamentals.columns)
    if missing_fundamentals:
        raise ValueError(f"fundamentals missing columns: {sorted(missing_fundamentals)}")
    if not policies:
        raise ValueError("at least one field quality policy is required")
    missing_fields = set(policies) - set(fundamentals.columns)
    if missing_fields:
        raise ValueError(f"fundamentals missing audited fields: {sorted(missing_fields)}")
    duplicate_keys = observations.duplicated(["date", "code"])
    if duplicate_keys.any():
        raise ValueError("observations must contain unique date, code rows")


def _business_exclusion(row: pd.Series) -> tuple[bool, str | None]:
    excluded = row.get("business_excluded", False)
    if pd.isna(excluded):
        excluded = False
    if not isinstance(excluded, (bool, np.bool_, int, np.integer)):
        raise ValueError("business_excluded must contain boolean values")
    reason = row.get("business_exclusion_reason")
    if bool(excluded) and (pd.isna(reason) or not str(reason).strip()):
        raise ValueError("business excluded rows require business_exclusion_reason")
    return bool(excluded), str(reason) if bool(excluded) else None


def _latest_available_record(
    code_records: pd.DataFrame,
    field: str,
    observation_time: pd.Timestamp,
) -> tuple[pd.Series | None, bool]:
    valued = code_records.loc[code_records[field].notna()]
    if valued.empty:
        return None, False
    available = valued.loc[
        valued["information_available_at"].notna()
        & (valued["information_available_at"] <= observation_time)
    ]
    if not available.empty:
        return available.iloc[-1], False
    future_exists = bool(
        (
            (
                valued["information_available_at"].notna()
                & (valued["information_available_at"] > observation_time)
            )
            | (
                valued["information_available_at"].isna()
                & (valued["ann_date"].dt.normalize() >= observation_time.normalize())
            )
        ).any()
    )
    return None, future_exists


def _detail_row(
    observation: pd.Series,
    observation_time: pd.Timestamp,
    field: str,
    policy: FieldQualityPolicy,
    code_records: pd.DataFrame,
) -> dict[str, Any]:
    excluded, exclusion_reason = _business_exclusion(observation)
    base = {
        "date": observation["date"],
        "code": str(observation["code"]),
        "industry": observation.get("industry"),
        "field": field,
        "observation_time": observation_time,
        "status": None,
        "included": False,
        "value": None,
        "last_available_at": pd.NaT,
        "last_ann_date": pd.NaT,
        "last_report_period": pd.NaT,
        "lag_days": None,
        "max_age_days": policy.max_age_days,
        "decision": None,
        "exclusion_reason": exclusion_reason,
    }
    if excluded:
        base.update(status="business_excluded", decision="exclude")
        return base

    latest, future_exists = _latest_available_record(code_records, field, observation_time)
    if latest is None:
        status = "not_yet_announced" if future_exists else "never_available"
        base.update(status=status, decision="exclude", exclusion_reason=status)
        return base

    lag_days = int((observation_time.normalize() - latest["information_available_at"].normalize()).days)
    stale = lag_days > policy.max_age_days
    status = "stale" if stale else "valid"
    base.update(
        status=status,
        included=not stale,
        value=latest[field],
        last_available_at=latest["information_available_at"],
        last_ann_date=latest["ann_date"],
        last_report_period=latest["report_period"],
        lag_days=lag_days,
        decision=policy.stale_action if stale else "include",
        exclusion_reason=(f"stale_over_{policy.max_age_days}_days" if stale else None),
    )
    return base


def _summary(frame: pd.DataFrame, group_columns: list[str]) -> pd.DataFrame:
    columns = group_columns + [
        "total_count",
        "eligible_count",
        "valid_count",
        "stale_count",
        "never_available_count",
        "not_yet_announced_count",
        "business_excluded_count",
        "coverage_ratio",
        "usable_coverage_ratio",
        "missing_ratio",
        "stale_ratio",
        "last_available_at",
        "last_ann_date",
        "last_report_period",
        "max_lag_days",
        "median_lag_days",
    ]
    if frame.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    keys: str | list[str] = group_columns[0] if len(group_columns) == 1 else group_columns
    for group_key, group in frame.groupby(keys, dropna=False, sort=True):
        values = (group_key,) if len(group_columns) == 1 else group_key
        result = dict(zip(group_columns, values, strict=True))
        status_counts = group["status"].value_counts()
        total = len(group)
        excluded = int(status_counts.get("business_excluded", 0))
        eligible = total - excluded
        valid = int(status_counts.get("valid", 0))
        stale = int(status_counts.get("stale", 0))
        never = int(status_counts.get("never_available", 0))
        not_yet = int(status_counts.get("not_yet_announced", 0))
        available = valid + stale
        lags = pd.to_numeric(group["lag_days"], errors="coerce").dropna()
        result.update(
            total_count=total,
            eligible_count=eligible,
            valid_count=valid,
            stale_count=stale,
            never_available_count=never,
            not_yet_announced_count=not_yet,
            business_excluded_count=excluded,
            coverage_ratio=(available / eligible if eligible else 1.0),
            usable_coverage_ratio=(valid / eligible if eligible else 1.0),
            missing_ratio=((never + not_yet) / eligible if eligible else 0.0),
            stale_ratio=(stale / eligible if eligible else 0.0),
            last_available_at=group["last_available_at"].max(),
            last_ann_date=group["last_ann_date"].max(),
            last_report_period=group["last_report_period"].max(),
            max_lag_days=(int(lags.max()) if not lags.empty else None),
            median_lag_days=(float(lags.median()) if not lags.empty else None),
        )
        rows.append(result)
    return pd.DataFrame(rows, columns=columns)


def _audit_id(
    rows: pd.DataFrame,
    field_summary: pd.DataFrame,
    date_summary: pd.DataFrame,
    industry_summary: pd.DataFrame,
    policies: Mapping[str, FieldQualityPolicy],
) -> str:
    payload = {
        "rule_version": FUNDAMENTAL_QUALITY_RULE_VERSION,
        "policies": {field: asdict(policy) for field, policy in sorted(policies.items())},
        "rows": _records(rows),
        "field_summary": _records(field_summary),
        "date_summary": _records(date_summary),
        "industry_summary": _records(industry_summary),
    }
    canonical = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return f"fqa_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]}"


def audit_fundamental_quality(
    observations: pd.DataFrame,
    fundamentals: pd.DataFrame,
    policies: Mapping[str, FieldQualityPolicy],
    *,
    signal_time: str | pd.Series,
    availability_time_col: str | None,
) -> FundamentalQualityAudit:
    _validate_inputs(observations, fundamentals, policies)
    observation_data = observations.copy().reset_index(drop=True)
    observation_data["date"] = pd.to_datetime(observation_data["date"], errors="raise")
    observation_data["_observation_time"] = resolve_signal_times(observation_data, signal_time)
    trading_dates = pd.DatetimeIndex(observation_data["date"].dt.normalize().drop_duplicates().sort_values())

    fundamental_data = fundamentals.copy()
    fundamental_data["ann_date"] = pd.to_datetime(fundamental_data["ann_date"], errors="raise")
    fundamental_data["report_period"] = pd.to_datetime(fundamental_data["report_period"], errors="raise")
    fundamental_data = resolve_information_availability(
        fundamental_data,
        trading_dates,
        availability_time_col,
    ).sort_values(["code", "information_available_at", "report_period"], na_position="last")

    records_by_code = {
        str(code): group.reset_index(drop=True)
        for code, group in fundamental_data.groupby("code", sort=False)
    }
    empty_records = fundamental_data.iloc[0:0]
    detail_rows: list[dict[str, Any]] = []
    for _, observation in observation_data.iterrows():
        code_records = records_by_code.get(str(observation["code"]), empty_records)
        for field, policy in policies.items():
            detail_rows.append(
                _detail_row(
                    observation,
                    observation["_observation_time"],
                    field,
                    policy,
                    code_records,
                )
            )
    rows = pd.DataFrame(detail_rows)
    if not set(rows["status"]).issubset(QUALITY_STATUSES):
        raise AssertionError("fundamental quality audit produced an unknown status")

    field_summary = _summary(rows, ["field"])
    date_summary = _summary(rows, ["date", "field"])
    industry_summary = (
        _summary(rows.loc[rows["industry"].notna()], ["industry", "field"])
        if "industry" in rows
        else pd.DataFrame()
    )

    summary_by_field = field_summary.set_index("field")
    coverage_verified = all(
        summary_by_field.loc[field, "usable_coverage_ratio"] >= policy.min_coverage_ratio
        for field, policy in policies.items()
    )
    freshness_verified = all(
        summary_by_field.loc[field, "stale_ratio"] <= policy.max_stale_ratio
        or policy.stale_action == "exclude"
        for field, policy in policies.items()
    )
    return FundamentalQualityAudit(
        audit_id=_audit_id(rows, field_summary, date_summary, industry_summary, policies),
        rule_version=FUNDAMENTAL_QUALITY_RULE_VERSION,
        rows=rows,
        field_summary=field_summary,
        date_summary=date_summary,
        industry_summary=industry_summary,
        policies=dict(policies),
        coverage_verified=coverage_verified,
        freshness_verified=freshness_verified,
    )


def save_fundamental_quality_audit(audit: FundamentalQualityAudit, directory: str | Path) -> Path:
    output_dir = Path(directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit.rows.to_csv(output_dir / "records.csv", index=False)
    audit.field_summary.to_csv(output_dir / "fields.csv", index=False)
    audit.date_summary.to_csv(output_dir / "dates.csv", index=False)
    audit.industry_summary.to_csv(output_dir / "industries.csv", index=False)
    manifest_path = output_dir / "audit.json"
    manifest_path.write_text(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path
