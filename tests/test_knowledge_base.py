import json

import pandas as pd
import pytest

from src.agents.knowledge import generation_context
from src.agents.knowledge_base import KnowledgeValidationError, load_knowledge_base
from src.agents.validate import validate
from src.config import Config
from src.factors.engine import FactorExpr
from src.utils.data_loader import build_panel
from src.utils.field_availability import get_field_availability, price_field_metadata


def _panel():
    return build_panel(
        Config(start_date="2020-01-01", end_date="2020-04-30", train_end="2020-03-31"),
        save=False,
    )


def test_default_knowledge_base_is_versioned_and_traceable():
    knowledge = load_knowledge_base()
    source_ids = {item["source_id"] for item in knowledge["sources"]}
    fields = {item["field"]: item for item in knowledge["fields"]}

    assert knowledge["schema_version"] == "1.0"
    assert knowledge["knowledge_version"]
    assert {"juyuan-core-market-data", "juyuan-performance-forecast"} <= source_ids
    assert fields["forecast_text_feature"]["available_date"] == "next_trading_date(InfoPublDate)"
    assert fields["forecast_text_feature"]["source_id"] == "juyuan-performance-forecast"


def test_loader_rejects_unknown_source_reference(tmp_path):
    knowledge = json.loads(json.dumps(load_knowledge_base()))
    knowledge["fields"][0]["source_id"] = "missing-source"
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(knowledge), encoding="utf-8")

    with pytest.raises(KnowledgeValidationError, match="unknown source"):
        load_knowledge_base(path)


def test_generation_context_exposes_only_catalogued_panel_fields():
    panel = _panel()
    panel["uncatalogued_runtime_value"] = 1.0
    context = generation_context(panel)
    fields = {item["field"] for item in context["field_catalog"]}

    assert "close" in fields
    assert "uncatalogued_runtime_value" not in fields
    assert context["knowledge_sources"]
    assert context["institution_rules"]


def test_uncatalogued_field_cannot_claim_current_backtestability():
    panel = _panel().copy()
    panel["mystery_signal"] = pd.Series(1.0, index=panel.index)
    metadata = get_field_availability(panel)
    metadata["mystery_signal"] = price_field_metadata("mystery_signal")
    panel.attrs["field_availability"] = metadata
    expr = FactorExpr(
        name="invented",
        expression="rank(mystery_signal)",
        economic_rationale="test fail-closed knowledge boundary",
        fields_used=["mystery_signal"],
        metadata={
            "backtestable_status": "currently_backtestable",
            "knowledge_citations": ["juyuan-core-market-data"],
        },
    )

    ok, reason = validate(expr, set(panel.columns), panel=panel)

    assert not ok
    assert "not registered as backtestable" in reason


def test_currently_backtestable_candidate_must_cite_field_source():
    panel = _panel()
    expr = FactorExpr(
        name="uncited",
        expression="rank(close)",
        economic_rationale="test citation boundary",
        fields_used=["close"],
        metadata={"backtestable_status": "currently_backtestable", "knowledge_citations": ["cninfo-disclosure"]},
    )

    ok, reason = validate(expr, set(panel.columns), panel=panel)

    assert not ok
    assert "does not cite field sources" in reason
