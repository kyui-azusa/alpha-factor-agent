from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Config:
    freq: str = "D"
    universe: str = "a_share_all"
    start_date: str = "2015-01-01"
    end_date: str = "2021-12-31"
    train_end: str = "2019-12-31"
    signal_time: str = "15:00:00"
    fundamental_availability_time_col: str | None = None
    cost_bps: float = 10.0
    data_dir: Path = PROJECT_ROOT / "data"
    results_dir: Path = PROJECT_ROOT / "results"
    llm_backend: str = os.getenv("ALPHA_AGENT_LLM_BACKEND", "mock")
    llm_model: str = os.getenv("ALPHA_AGENT_LLM_MODEL", "gpt-4.1-mini")
    llm_max_tokens: int = int(os.getenv("ALPHA_AGENT_LLM_MAX_TOKENS", "800"))
    llm_temperature: float = float(os.getenv("ALPHA_AGENT_LLM_TEMPERATURE", "0.2"))

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def report_dir(self) -> Path:
        return self.results_dir / "reports"

    @property
    def factor_dir(self) -> Path:
        return self.results_dir / "factors"

    def ensure_dirs(self) -> None:
        for path in (
            self.raw_dir,
            self.processed_dir,
            self.cache_dir,
            self.cache_dir / "llm",
            self.report_dir,
            self.factor_dir,
            self.results_dir / "logs",
        ):
            path.mkdir(parents=True, exist_ok=True)


CONFIG = Config()
CONFIG.ensure_dirs()
