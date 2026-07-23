from __future__ import annotations

from typing import Any

import pandas as pd


FIELD_AVAILABILITY_ATTR = "field_availability"
PIT_PROVENANCE_ATTR = "pit_provenance"

SAME_DAY_MARKET_FIELDS = {"open", "high", "low", "close", "vol", "amount"}
MARKET_FIELDS = SAME_DAY_MARKET_FIELDS | {"adj_factor", "mktcap", "industry"}
UNIVERSE_FIELDS = {"weight"}
IDENTITY_FIELDS = {"date", "code"}


def price_field_metadata(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "source": "prices",
        "available_date": "date",
        "rule": "same trading date market data; usable at date for forward-return tests",
        "pit_protected": True,
    }


def universe_field_metadata(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "source": "universe",
        "available_date": "date",
        "rule": "historical universe membership for the same trading date",
        "pit_protected": True,
    }


def fundamental_field_metadata(field: str) -> dict[str, Any]:
    return {
        "field": field,
        "source": "fundamentals",
        "available_date": "information_available_at",
        "rule": (
            "latest record with information_available_at <= signal_time selected by pit_merge; "
            "date-only announcements become available on the next trading day"
        ),
        "pit_protected": True,
    }


def derived_field_metadata(field: str, inputs: list[str], rule: str) -> dict[str, Any]:
    return {
        "field": field,
        "source": "derived",
        "available_date": "max(input available dates)",
        "inputs": inputs,
        "rule": rule,
        "pit_protected": True,
    }


def build_pit_merge_metadata(price_columns: list[str], fundamental_columns: list[str]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for field in price_columns:
        if field not in IDENTITY_FIELDS:
            metadata[field] = price_field_metadata(field)
    for field in fundamental_columns:
        if field != "code":
            metadata[field] = fundamental_field_metadata(field)
    return metadata


def attach_field_availability(df: pd.DataFrame, metadata: dict[str, dict[str, Any]]) -> pd.DataFrame:
    out = df.copy()
    out.attrs[FIELD_AVAILABILITY_ATTR] = {key: dict(value) for key, value in metadata.items()}
    return out


def get_field_availability(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    raw = df.attrs.get(FIELD_AVAILABILITY_ATTR, {})
    return raw if isinstance(raw, dict) else {}


def set_field_metadata(df: pd.DataFrame, field: str, metadata: dict[str, Any]) -> None:
    field_metadata = dict(get_field_availability(df))
    field_metadata[field] = dict(metadata)
    df.attrs[FIELD_AVAILABILITY_ATTR] = field_metadata


def validate_field_availability(fields: set[str], panel: pd.DataFrame) -> tuple[bool, str]:
    metadata = get_field_availability(panel)
    panel_fields = set(panel.columns)
    used_panel_fields = fields & panel_fields
    if not used_panel_fields:
        return True, "ok"

    if not metadata:
        pit_sensitive = sorted(field for field in used_panel_fields if field not in SAME_DAY_MARKET_FIELDS)
        if pit_sensitive:
            return False, f"field availability metadata missing for PIT-sensitive fields: {pit_sensitive}"
        return True, "ok"

    missing = sorted(field for field in used_panel_fields if field not in metadata)
    if missing:
        return False, f"field availability metadata missing for fields: {missing}"

    for field in sorted(used_panel_fields):
        field_meta = metadata[field]
        source = field_meta.get("source")
        if source == "fundamentals":
            if field_meta.get("available_date") != "information_available_at" or not field_meta.get(
                "pit_protected"
            ):
                return False, f"fundamental field {field} is not proven point-in-time by availability timestamp"
        elif source == "derived":
            inputs = set(field_meta.get("inputs", []))
            ok, reason = validate_field_availability(inputs, panel)
            if not ok:
                return False, f"derived field {field} is not PIT-safe: {reason}"
        elif source not in {"prices", "universe"}:
            return False, f"field {field} has unsupported availability source: {source}"

    return True, "ok"
