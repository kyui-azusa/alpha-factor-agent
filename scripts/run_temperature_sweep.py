from __future__ import annotations

import argparse
from dataclasses import replace

from src.agents.knowledge import generation_context
from src.agents.temperature import TemperatureSweepConfig, sweep_temperatures, write_temperature_report
from src.config import CONFIG
from src.factors.baseline import BASELINE_FACTORS
from src.llm.client import LLMClient
from src.utils.data_loader import build_panel


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a controlled LLM temperature novelty-validity sweep.")
    parser.add_argument("--temperatures", nargs="+", type=float, default=[0.0, 0.2, 0.5, 0.8, 1.0])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--per-repeat", type=int, default=5)
    parser.add_argument("--output-dir", default=str(CONFIG.report_dir / "temperature_sweep"))
    args = parser.parse_args()

    panel = build_panel(CONFIG, save=False)
    config = TemperatureSweepConfig(tuple(args.temperatures), args.repeats, args.per_repeat)

    def client_factory(temperature: float, repeat: int) -> LLMClient:
        del repeat
        return LLMClient(replace(CONFIG, llm_temperature=temperature))

    report = sweep_temperatures(
        existing_factors=list(BASELINE_FACTORS),
        generation_context=generation_context(panel),
        field_dict={column: str(dtype) for column, dtype in panel.dtypes.items()},
        panel=panel,
        client_factory=client_factory,
        config=config,
    )
    output = write_temperature_report(report, args.output_dir)
    print(output)


if __name__ == "__main__":
    main()
