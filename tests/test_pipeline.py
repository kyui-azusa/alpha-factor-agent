import pytest

from src.config import Config
from src.factors.baseline import BASELINE_FACTORS
from src.pipeline import run_project
from src.report_factors import SUMMARY_COLUMNS, export_summary


def test_pipeline_runs_baselines_only(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    manifest = run_project(cfg=cfg, include_agent=False, n_quantiles=3)
    assert manifest["baseline_count"] == len(BASELINE_FACTORS)
    assert manifest["agent_factor_count"] == 0
    assert (cfg.report_dir / "baseline_summary.csv").exists()
    assert (cfg.results_dir / "run_manifest.json").exists()


def test_export_summary_has_headers_when_no_candidate_factors(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    cfg.ensure_dirs()

    frame, path = export_summary(cfg=cfg)

    assert list(frame.columns) == SUMMARY_COLUMNS
    assert frame.empty
    assert path.endswith("factor_summary.csv")


def test_pipeline_agent_mode_requires_preflight_permit(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")

    with pytest.raises(PermissionError, match="passing preflight"):
        run_project(cfg=cfg, include_agent=True)

    assert not cfg.results_dir.exists()
