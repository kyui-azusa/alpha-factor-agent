import json
from pathlib import Path

import pytest

from src.agents.feedback import (
    FeedbackBoundaryError,
    FeedbackRecord,
    FeedbackSource,
    development_feedback,
    feedback_summary,
    sealed_oos_evidence,
)
from src.agents.generate import propose_factors
from src.agents.json_utils import factor_from_json
from src.agents.knowledge import generation_context, seed_factor_lineage
from src.agents.loop import run_loop
from src.agents.validate import validate
from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.factors.engine import MAX_TIME_WINDOW
from src.factors.engine import FactorExpr
from src.llm.client import LLMClient
from src.research.contract import ResearchRequest, confirm_request
from src.research.preflight import CapabilityEvidence, create_execution_permit, run_preflight
from src.utils.field_availability import get_field_availability
from src.utils.data_loader import build_panel


class NonDuplicateClient:
    def generate(self, prompt: str, system: str | None = None) -> str:
        return '{"duplicate": false, "reason": "unit test semantic pass"}'


def _small_cfg(**overrides):
    values = {
        "data_dir": Path("/tmp/alpha_factor_agent_pytest_synthetic"),
        "start_date": "2020-01-01",
        "end_date": "2020-09-30",
        "train_end": "2020-06-30",
    }
    values.update(overrides)
    return Config(**values)


def _small_panel():
    return build_panel(_small_cfg(), save=False)


def _execution_permit(cfg: Config):
    panel = build_panel(cfg, save=False)
    request = confirm_request(
        ResearchRequest(
            raw_question="Generate a daily price factor.",
            hypothesis="Daily close contains cross-sectional signal.",
            universe=cfg.universe,
            start_date=cfg.start_date,
            end_date=cfg.end_date,
            target_horizon_days=20,
            baseline="registered baseline factors",
            allowed_fields=("operating_cash_flow", "total_assets", "total_equity"),
            allowed_operators=("rank", "safe_div", "delta"),
            candidate_count=1,
            rounds=1,
            hold_period_days=20,
            success_criteria=("report OOS rank IC",),
            data_mode="synthetic",
        ),
        known_fields=set(panel.columns),
    )
    dates = panel.index.get_level_values("date")
    evidence = CapabilityEvidence(
        data_mode="synthetic",
        available_start_date=str(dates.min().date()),
        available_end_date=str(dates.max().date()),
        available_fields=frozenset(panel.columns),
        forward_return_fields=frozenset({"fwd_ret_1", "fwd_ret_5", "fwd_ret_20"}),
        supported_universes=frozenset({cfg.universe}),
        field_availability=get_field_availability(panel),
        historical_universe_verified=True,
        adjustment_verified=True,
        coverage_verified=True,
        freshness_verified=True,
    )
    report = run_preflight(request, evidence)
    return create_execution_permit(request, report, run_id="run_agent_test")


def test_factor_from_json_preserves_metadata_and_extra_keys():
    expr = factor_from_json(
        {
            "name": "cashflow_yield",
            "expression": "rank(safe_div(operating_cash_flow, mktcap))",
            "formula": "OCF / market cap",
            "economic_rationale": "cash flow yield",
            "fields_used": ["operating_cash_flow", "mktcap"],
            "metadata": {"category": "cashflow_value"},
            "alpha_target": "explainable value alpha",
        }
    )

    assert expr.formula == "OCF / market cap"
    assert expr.metadata["category"] == "cashflow_value"
    assert expr.metadata["alpha_target"] == "explainable value alpha"


def test_generation_context_contains_seed_catalog_and_no_raw_arrays():
    panel = _small_panel()
    context = generation_context(panel)

    assert context["seed_factors"]
    assert context["seed_factor_lineage"] == seed_factor_lineage()
    assert {item["name"] for item in context["synthesis_methods"]} >= {"complementary_blend", "risk_adjustment"}
    assert {item["field"] for item in context["field_catalog"]} >= {"close", "eps", "operating_cash_flow"}
    assert any(item["missing_policy"] for item in context["field_catalog"])
    assert context["knowledge_version"]
    assert context["knowledge_sources"]
    assert context["institution_rules"]
    assert "raw_values" not in context
    assert "rows" not in context


def test_propose_factors_records_generation_params(tmp_path):
    cfg = Config(
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
        llm_backend="mock",
        llm_temperature=0.7,
    )
    cfg.ensure_dirs()
    client = LLMClient(cfg)

    factors = propose_factors([factor.to_dict() for factor in BASELINE_FACTORS], {"field_catalog": []}, n=1, client=client)

    params = factors[0].metadata["generation"]["params"]
    assert params["temperature"] == 0.7
    assert params["max_tokens"] == cfg.llm_max_tokens
    assert factors[0].metadata["generation"]["proposal_rank"] == 1
    assert factors[0].metadata["generation"]["generated_at_utc"]
    assert "source_seed_factors" in factors[0].metadata
    assert "synthesis_method" in factors[0].metadata
    assert "lineage" in factors[0].metadata
    generation = factors[0].metadata["generation"]
    assert generation["generation_record_id"].startswith("gen_")
    assert generation["candidate_id"].startswith("cand_")
    assert generation["record"]["output_hash"]


def test_propose_factors_reuses_stable_generation_and_candidate_ids(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()

    first = propose_factors([], {"field_catalog": []}, n=1, client=LLMClient(cfg))[0]
    second = propose_factors([], {"field_catalog": []}, n=1, client=LLMClient(cfg))[0]

    first_generation = first.metadata["generation"]
    second_generation = second.metadata["generation"]
    assert first_generation["generation_record_id"] == second_generation["generation_record_id"]
    assert first_generation["candidate_id"] == second_generation["candidate_id"]
    assert second_generation["record"]["cache_hit"] is True


def _feedback_result(oos_ic: float = -0.2, oos_net: float = -0.01):
    return {
        "train_summary": {
            "segment": "train",
            "ic_mean": 0.03,
            "long_short_mean": 0.001,
            "net_long_short_mean": 0.0004,
            "turnover_mean": 0.9,
            "observations": 120,
        },
        "summary": {
            "segment": "oos",
            "ic_mean": oos_ic,
            "net_long_short_mean": oos_net,
            "observations": 60,
        },
        "walk_forward": {"status": "mixed_regime_ic"},
        "tradability": {"dropped_observations": 10},
        "robustness": {"overfit_risk": "high", "cost_sensitivity": "medium"},
        "data": {"data_mode": "synthetic"},
    }


def test_development_feedback_only_exposes_categorical_diagnostics():
    expr = FactorExpr(
        "candidate",
        "rank(eps)",
        "earnings signal",
        ["eps"],
        metadata={"risk_exposures": ["industry"], "validation_notes": ["check coverage"]},
    )
    feedback = development_feedback(expr, _feedback_result())

    summary = feedback_summary(feedback)

    assert summary["source"] == "dev_backtest"
    assert summary["diagnostics"]["turnover_diagnostic"] == "medium_turnover_review_cost_sensitivity"
    assert summary["diagnostics"]["cost_diagnostic"] == "high_cost_decay_review_turnover_and_capacity"
    assert summary["oos_values_exposed"] is False
    serialized = json.dumps(summary, sort_keys=True)
    for raw_metric in ("ic_mean", "long_short_mean", "net_long_short_mean", "walk_forward", "tradability"):
        assert raw_metric not in serialized


def test_oos_changes_do_not_change_development_feedback():
    expr = FactorExpr("candidate", "rank(eps)", "earnings signal", ["eps"])

    failed = development_feedback(expr, _feedback_result(oos_ic=-0.8, oos_net=-0.4))
    successful = development_feedback(expr, _feedback_result(oos_ic=0.8, oos_net=0.4))

    assert failed == successful


def test_sealed_oos_evidence_is_terminal_and_has_failure_reasons():
    expr = FactorExpr("candidate", "rank(eps)", "earnings signal", ["eps"])
    evidence = sealed_oos_evidence(expr, _feedback_result())

    assert evidence.source is FeedbackSource.OOS_BACKTEST
    assert evidence.next_generation_allowed is False
    assert evidence.payload["status"] == "oos_failed"
    assert evidence.payload["failure_reasons"] == ["non_positive_oos_ic", "non_positive_oos_net_long_short"]
    assert evidence.payload["clean_oos_test"] is True
    assert evidence.payload["allowed_next_action"] == "record_evidence_only"

    with pytest.raises(FeedbackBoundaryError, match="sealed"):
        feedback_summary(evidence)


@pytest.mark.parametrize(
    "source",
    [FeedbackSource.PRE_GENERATION, FeedbackSource.VALIDATION, FeedbackSource.DEV_BACKTEST],
)
def test_generation_feedback_sources_reject_non_allowlisted_metrics(source):
    feedback = FeedbackRecord(
        source=source,
        factor_name="candidate",
        payload={"factor_name": "candidate", "ic_mean": 0.03},
        next_generation_allowed=True,
        disposition="bounded_diagnostic_input",
    )

    with pytest.raises(FeedbackBoundaryError, match="non-allowlisted"):
        feedback_summary(feedback)


def test_feedback_summary_requires_explicit_source_provenance():
    payload = {
        "train_summary": {"segment": "train", "ic_mean": 0.03, "net_long_short_mean": 0.001, "observations": 120},
        "summary": {"segment": "oos", "ic_mean": -0.2, "net_long_short_mean": -0.01},
        "walk_forward": {"status": "mixed_regime_ic"},
        "tradability": {"dropped_observations": 10},
        "data": {"data_mode": "synthetic"},
    }

    with pytest.raises(TypeError, match="explicit FeedbackRecord"):
        feedback_summary(payload)


def test_validate_blocks_future_return_field():
    panel = _small_panel()
    expr = FactorExpr("leaky", "rank(fwd_ret_5)", "uses label", ["fwd_ret_5"])
    ok, reason = validate(expr, set(panel.columns) | {"fwd_ret_5"}, panel=None)
    assert not ok
    assert "forbidden" in reason


def test_validate_blocks_negative_delay():
    panel = _small_panel()
    expr = FactorExpr("leaky_delay", "rank(delay(close, -1))", "uses tomorrow close", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "future" in reason


def test_validate_reports_syntax_errors_without_panel():
    panel = _small_panel()
    expr = FactorExpr("bad_syntax", "rank(close", "broken expression", ["close"])
    ok, reason = validate(expr, set(panel.columns), panel=None)
    assert not ok
    assert "syntax" in reason


def test_validate_rejects_oversized_time_window():
    panel = _small_panel()
    expr = FactorExpr("too_long", f"rank(ts_mean(close, {MAX_TIME_WINDOW + 1}))", "too long", ["close"])

    ok, reason = validate(expr, set(panel.columns), panel=None)

    assert not ok
    assert "exceeds max" in reason


def test_validate_rejects_non_constant_time_window():
    panel = _small_panel()
    expr = FactorExpr("dynamic", "rank(ts_mean(close, amount))", "dynamic window", ["close", "amount"])

    ok, reason = validate(expr, set(panel.columns), panel=None)

    assert not ok
    assert "numeric constant" in reason


def test_validate_rejects_duplicate_expression_by_fingerprint():
    panel = _small_panel()
    expr = FactorExpr("copy", BASELINE_FACTORS[0].expression, "copy", BASELINE_FACTORS[0].fields_used)

    ok, reason = validate(expr, set(panel.columns), panel=panel, existing_factors=[BASELINE_FACTORS[0]])

    assert not ok
    assert "deterministic duplicate" in reason
    novelty = expr.metadata["validation"]["novelty"]
    evidence = novelty["evidence"][0]
    assert novelty["status"] == "reject"
    assert evidence["candidate_name"] == "copy"
    assert evidence["nearest_factor"] == BASELINE_FACTORS[0].name
    assert evidence["similarity_type"] == "deterministic_duplicate"
    assert evidence["shared_fields"] == sorted(BASELINE_FACTORS[0].fields_used)
    assert evidence["candidate_fingerprint"] == evidence["nearest_fingerprint"]
    assert evidence["abs_corr"] == 1.0
    assert evidence["threshold"] == 1.0
    assert evidence["decision"] == "reject"
    assert "deterministic duplicate" in evidence["reason"]


def test_validate_rejects_high_correlation_with_evidence():
    panel = _small_panel()
    baseline = BASELINE_FACTORS[1]
    expr = FactorExpr(
        "rescaled_quality_roe",
        "2 * rank(safe_div(net_income, total_equity))",
        "same quality signal after rescaling",
        ["net_income", "total_equity"],
    )

    ok, reason = validate(expr, set(panel.columns), panel=panel, existing_factors=[baseline], client=NonDuplicateClient())

    assert not ok
    assert "too correlated" in reason
    novelty = expr.metadata["validation"]["novelty"]
    evidence = novelty["evidence"][0]
    assert novelty["status"] == "reject"
    assert evidence["nearest_factor"] == baseline.name
    assert evidence["similarity_type"] == "high_correlation_reject"
    assert evidence["shared_fields"] == ["net_income", "total_equity"]
    assert evidence["abs_corr"] >= evidence["threshold"]
    assert evidence["threshold"] == novelty["corr_reject_threshold"]
    assert evidence["decision"] == "reject"
    assert evidence["candidate_fingerprint"] != evidence["nearest_fingerprint"]
    assert "too correlated" in evidence["reason"]


def test_validate_warns_high_correlation_with_evidence():
    panel = _small_panel()
    baseline = BASELINE_FACTORS[1]
    expr = FactorExpr(
        "quality_value_near_neighbor",
        "0.6 * rank(safe_div(net_income, total_equity)) + 0.4 * rank(safe_div(eps, close))",
        "quality with a value overlay",
        ["net_income", "total_equity", "eps", "close"],
    )

    ok, reason = validate(expr, set(panel.columns), panel=panel, existing_factors=[baseline], client=NonDuplicateClient())

    assert ok
    assert reason == "ok"
    novelty = expr.metadata["validation"]["novelty"]
    evidence = novelty["evidence"][0]
    assert "novelty warning" in expr.metadata["validation"]["warning"]
    assert novelty["status"] == "warn"
    assert evidence["nearest_factor"] == baseline.name
    assert evidence["similarity_type"] == "high_correlation_warn"
    assert evidence["shared_fields"] == ["net_income", "total_equity"]
    assert evidence["threshold"] == novelty["corr_warn_threshold"]
    assert evidence["threshold"] <= evidence["abs_corr"] < novelty["corr_reject_threshold"]
    assert evidence["decision"] == "warn"
    assert "novelty warning" in evidence["reason"]


def test_agent_loop_runs_one_round_and_writes_factors(tmp_path):
    cfg = _small_cfg(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()
    client = LLMClient(cfg)
    permit = _execution_permit(cfg)
    results = run_loop(rounds=1, per_round=1, cfg=cfg, client=client, execution_permit=permit)
    assert len(results) == 1
    assert results[0]["expr"]["metadata"]["research_execution"]["request_id"] == permit.request_id
    funnel = results[0]["candidate_funnel"]
    assert funnel["generated"] == 1
    assert funnel["validated"] == 1
    assert funnel["backtested"] == 1
    assert funnel["promoted"] == 1
    assert funnel["multiple_testing_disclosure_required"] is False
    assert results[0]["candidate_audit"]["reason_code"] == "promoted"
    factor_files = list(cfg.factor_dir.glob("*.json"))
    assert factor_files
    factor_payload = json.loads(factor_files[0].read_text(encoding="utf-8"))
    audit = factor_payload["feedback_audit"]
    assert audit["oos_values_exposed_to_generation"] is False
    assert audit["next_generation_allowed_from_oos"] is False
    assert audit["clean_oos_test"] is True

    factor_name = results[0]["expr"]["name"]
    evidence_path = cfg.results_dir / "feedback" / "oos" / f"{factor_name}.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["source"] == "oos_backtest"
    assert evidence["next_generation_allowed"] is False
    assert evidence["payload"]["allowed_next_action"] == "record_evidence_only"

    report_dir = cfg.report_dir / factor_name
    report = json.loads((report_dir / "report.json").read_text(encoding="utf-8"))
    assert report["feedback_audit"] == audit
    assert report["oos_evidence"]["source"] == "oos_backtest"
    factor_card = (report_dir / "factor_card.md").read_text(encoding="utf-8")
    assert "## Feedback Boundary" in factor_card
    assert "Next generation allowed from OOS: `False`" in factor_card


def test_agent_loop_rejects_generation_without_execution_permit(tmp_path):
    cfg = _small_cfg(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")

    with pytest.raises(PermissionError, match="passing preflight"):
        run_loop(rounds=1, per_round=1, cfg=cfg, client=LLMClient(cfg))


def test_agent_loop_rejects_work_beyond_confirmed_limits(tmp_path):
    cfg = _small_cfg(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    permit = _execution_permit(cfg)

    with pytest.raises(PermissionError, match="exceeds"):
        run_loop(rounds=2, per_round=1, cfg=cfg, client=LLMClient(cfg), execution_permit=permit)
