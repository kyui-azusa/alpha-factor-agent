from src.config import Config
from src.pipeline import run_project
from src.report_factors import SUMMARY_COLUMNS, export_summary


def test_pipeline_runs_baselines_only(tmp_path):
    cfg = Config(data_dir=tmp_path / "data", results_dir=tmp_path / "results", llm_backend="mock")
    manifest = run_project(cfg=cfg, include_agent=False, n_quantiles=3)
    assert manifest["baseline_count"] == 5
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
