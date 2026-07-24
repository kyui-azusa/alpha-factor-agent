import pytest

from src.experiments.evidence import CONTRACT_VERSION, EXPERIMENT_SPECS, build_evidence_contract


REMAINING_EXPERIMENT_ISSUES = {71, 73, 74, 75, 77}


def test_remaining_experiments_share_contract_version_and_status_meaning():
    assert set(EXPERIMENT_SPECS) == REMAINING_EXPERIMENT_ISSUES

    contracts = [build_evidence_contract(issue) for issue in sorted(REMAINING_EXPERIMENT_ISSUES)]

    assert {contract["contract_version"] for contract in contracts} == {CONTRACT_VERSION}
    assert {contract["status"] for contract in contracts} == {"ready"}
    assert all("not a research conclusion" in contract["status_meaning"] for contract in contracts)
    assert {contract["evidence"]["status"] for contract in contracts} == {"insufficient_evidence"}


def test_semantic_dup_experiment_lists_missing_manual_llm_and_catalog_evidence():
    contract = build_evidence_contract(71, available_evidence=set())

    missing = {item["key"]: item["label"] for item in contract["evidence"]["missing"]}

    assert contract["status"] == "ready"
    assert contract["evidence"]["status"] == "insufficient_evidence"
    assert missing == {
        "human_labels": "人工标签",
        "real_llm_calls": "真实 LLM 调用",
        "factor_catalog_100": "100 因子目录",
    }
    assert contract["research_conclusion"]["status"] == "not_computed"


def test_pit_experiment_can_be_evidence_ready_without_claiming_conclusion():
    contract = build_evidence_contract(75, available_evidence={"real_jydb_data"})

    assert contract["status"] == "ready"
    assert contract["evidence"]["status"] == "ready"
    assert contract["evidence"]["missing"] == []
    assert contract["research_conclusion"]["status"] == "not_computed"


def test_research_conclusion_is_separate_from_readiness_and_evidence():
    conclusion = {
        "status": "computed",
        "metric": "max_delta_ic",
        "value": 0.031,
    }

    contract = build_evidence_contract(75, available_evidence={"real_jydb_data"}, research_conclusion=conclusion)

    assert contract["status"] == "ready"
    assert contract["evidence"]["status"] == "ready"
    assert contract["research_conclusion"] == conclusion


def test_unknown_evidence_key_is_rejected():
    with pytest.raises(ValueError, match="unknown evidence keys"):
        build_evidence_contract(74, available_evidence={"spreadsheet_screenshot"})
